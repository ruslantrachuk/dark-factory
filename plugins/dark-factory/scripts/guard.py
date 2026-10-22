#!/usr/bin/env python3
"""Fence guard (PreToolUse hook): the agent cannot do what only a human may decide.

Instructions in CLAUDE.md ("do not push without asking", "merge only after a human's yes")
are advice; this hook is the fence. It reads the hook JSON on stdin and answers `deny` with
what to do instead. stdlib only, Python 3.11+.

Bash — denied at every level (`solo` and up):
  * `git push` with -f/--force/--force-with-lease/--mirror or a `+refspec`;
  * a push to the main branch (`git push origin main`, `HEAD:main`, `git push` while on main,
    `--all`), including deleting it;
  * `--no-verify` on `git commit`/`git push`, `-n` on `git commit`, `git -c core.hooksPath=…`,
    re-pointing `core.hooksPath` away from `.githooks` — the hooks are the gate;
  * pushing release tags (`v*`, `r*`, also `--tags`/`--follow-tags`) — that is scripts/release.sh;
  * `git branch -d/-D` of the main branch, `git reset --hard` while on the main branch.
Added at `standard` (the default) and `team`:
  * `gh pr merge` (and the merge API) — merging goes through scripts/merge-feature.sh, which
    requires `--accepted-by "<name>"`; `gh pr review --approve` — approvals are given by people;
  * editing the fence files (.claude/settings*.json, .claude/fences.env, .githooks/,
    scripts/merge-feature.sh) with Edit/Write or a Bash write — the human edits them.

Part of the dark-factory plugin (hooks/hooks.json); the project is $CLAUDE_PROJECT_DIR (else the
git top level of the hook's cwd). A project opts in with `.claude/fences.env`: without that file
the guard stays silent, so a plugin installed for the user does not fence unrelated projects.
The fence level comes from `.claude/fences.env` (FENCE_LEVEL=solo|standard|team, default standard).
Main branch: MAIN_BRANCH in the project's scripts/merge-feature.sh, else origin/HEAD, else `main`.

How a command is read: quoted strings and heredoc bodies are data, not commands (a commit
message may say "--force" or "gh pr merge"); the line is split on && || ; | & newlines and
parentheses; `$(…)`/backticks — also inside double quotes and unquoted heredocs — and
`bash -c '…'`/`eval` are checked as commands of their own; `env`/`VAR=` prefixes, wrappers
(`command`, `nohup`, `xargs`, `timeout`…), `cd`, `env -C` and `git -C dir` are followed.
A static reading has limits (a flag hidden in a variable is not seen); permissions.deny in
settings.json and GitHub branch protection are the further layers.

Bypass is for a human only: restart the session with GUARD=off (the same idea as QUOTA_GUARD).
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path

LEVELS = ("solo", "standard", "team")
DEFAULT_LEVEL = "standard"
FENCES_FILE = ".claude/fences.env"
EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
RELEASE_TAGS = ("v*", "r*")
# A bare push name that looks like a release tag even when no such local tag exists.
RELEASE_TAG_SHAPE = re.compile(r"v\d[\w.\-]*|r\d+")
# The fences themselves: the human edits them (at standard and team).
FENCE_FILE_RE = re.compile(
    r"(?:^|/)(?:\.claude/(?:settings(?:\.local)?\.json|fences\.env)"
    r"|\.githooks/[^/]+"
    r"|scripts/merge-feature\.sh)$"
)
GH_MERGE_API_RE = re.compile(r"mergePullRequest|enablePullRequestAutoMerge")
GH_MERGE_REST_RE = re.compile(r"pulls/[^/\s]+/merge\b")
ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*\+?=")
REDIR_RE = re.compile(r"(\d*)(&>>|&>|>>|>\||>&|<<<|<<-|<<|<&|<>|>|<)")
OPERATORS = ("&&", "||", "|&", ";;", ";", "|", "&", "(", ")")
SHELLS = {"bash", "sh", "zsh", "dash", "ksh"}
KEYWORDS = {"!", "{", "}", "if", "then", "else", "elif", "do", "while", "until", "fi", "done", "esac", "time"}
# Wrappers that run the command after them: options that take a value, and positional
# arguments before the command (timeout DURATION).
WRAPPERS = {
    "command": set(), "builtin": set(), "nohup": set(), "exec": {"-a"},
    "sudo": {"-u", "-g", "-C", "-p", "-h", "-U", "-r", "-t"}, "doas": {"-u", "-C"},
    "nice": {"-n"}, "ionice": {"-c", "-n", "-p"}, "stdbuf": {"-i", "-o", "-e"},
    "xargs": {"-I", "-n", "-P", "-L", "-d", "-E", "-s", "-a"},
    "timeout": {"-s", "-k", "--signal", "--kill-after"},
}
WRAPPER_POSITIONAL = {"timeout": 1}
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--super-prefix", "--config-env"}

BYPASS = "Only a human can bypass this: restart the session with GUARD=off."

# (what is denied, what to do instead)
MERGE = (
    "merging a PR directly is denied",
    "Merging goes through scripts/merge-feature.sh <branch> [title] --accepted-by \"<name>\" "
    "after a person's explicit \"accepted\" — ask the human; do not merge without their yes.",
)
APPROVE = (
    "approving a PR from the agent is denied",
    "An approval is a person's decision in their own name; ask a reviewer.",
)
FORCE = (
    "force push is denied (it rewrites shared history)",
    "Push without force: merge the main branch into your branch, or push to a new branch. "
    "If history really must be rewritten, ask the human to do it.",
)
MAIN = (
    "pushing to the main branch '{main}' directly is denied",
    "Code reaches '{main}' through a PR: push the feature branch, and after the human's "
    "\"accepted\" run scripts/merge-feature.sh <branch> --accepted-by \"<name>\". A docs-only "
    "change — a docs/* branch through the same script, or ask the human to push it.",
)
NO_VERIFY = (
    "bypassing the git hooks is denied (--no-verify, commit -n, core.hooksPath)",
    "The hooks are the gate (devlog, tests): fix what the hook reports; if the hook itself is wrong, tell the human.",
)
TAG = (
    "pushing release tags (v*, r*) is denied",
    "Release tags are cut by scripts/release.sh (release-tag module) or by the human; "
    "push other tags by name.",
)
MAIN_BRANCH_DELETE = (
    "deleting the main branch '{main}' is denied",
    "Ask the human. To leave '{main}', switch away from it: git switch --detach origin/{main}.",
)
RESET_MAIN = (
    "git reset --hard on the main branch '{main}' is denied",
    "Work on a feature branch; to look at origin's state use git switch --detach origin/{main}. "
    "If local '{main}' really must be reset, ask the human.",
)
FENCE_EDIT = (
    "editing the fence files is denied (.claude/settings*.json, .claude/fences.env, .githooks/, "
    "scripts/merge-feature.sh)",
    "The human edits the fences: describe the change you propose and ask them to make it.",
)


# --- reading a shell command -------------------------------------------------


class Word(str):
    """A shell word after quote removal. dynamic — it depends on an expansion ($x, $(…)),
    quoted — part of it was quoted (matters for a heredoc delimiter)."""

    dynamic = False
    quoted = False


def _word(text: str, dynamic: bool = False, quoted: bool = False) -> Word:
    w = Word(text)
    w.dynamic, w.quoted = dynamic, quoted
    return w


class Segment:
    def __init__(self) -> None:
        self.words: list[Word] = []
        self.redirects: list[tuple[str, Word]] = []


class _Parser:
    """A small recursive reader of POSIX shell: words, operators, redirections, heredocs,
    substitutions. Every simple command (including those inside $(…), `…` and unquoted
    heredocs) ends up in self.segments."""

    def __init__(self, text: str) -> None:
        self.s, self.n, self.i = text, len(text), 0
        self.segments: list[Segment] = []

    def _end(self, seg: Segment) -> Segment:
        if seg.words or seg.redirects:
            self.segments.append(seg)
        return Segment()

    def parse(self, closer: str | None = None) -> None:
        seg, depth, heredocs = Segment(), 0, []
        while self.i < self.n:
            c = self.s[self.i]
            if c in " \t":
                self.i += 1
            elif self.s.startswith("\\\n", self.i):
                self.i += 2
            elif c == "\n":
                self.i += 1
                seg = self._end(seg)
                for doc in heredocs:
                    self._heredoc_body(*doc)
                heredocs = []
            elif c == "#":
                j = self.s.find("\n", self.i)
                self.i = self.n if j < 0 else j
            elif c == ")" and closer == ")" and depth == 0:
                self.i += 1
                break
            elif c in "<>" and self.s.startswith("(", self.i + 1):
                self.i += 2  # process substitution <(…) >(…)
                self.parse(")")
                seg.words.append(_word("<(…)", dynamic=True))
            elif m := REDIR_RE.match(self.s, self.i):
                self.i = m.end()
                op = m.group(2)
                while self.i < self.n and self.s[self.i] in " \t":
                    self.i += 1
                target = self._word() if self.i < self.n and self.s[self.i] not in "\n;&|()<>" else _word("")
                seg.redirects.append((op, target))
                if op in ("<<", "<<-"):
                    heredocs.append((str(target), target.quoted))
            elif op := next((o for o in OPERATORS if self.s.startswith(o, self.i)), None):
                if op == "(":
                    depth += 1
                elif op == ")":
                    depth = max(0, depth - 1)
                self.i += len(op)
                seg = self._end(seg)
            else:
                seg.words.append(self._word())
        self._end(seg)

    def _heredoc_body(self, delim: str, quoted: bool) -> None:
        body = []
        while self.i < self.n:
            j = self.s.find("\n", self.i)
            j = self.n if j < 0 else j
            line = self.s[self.i:j]
            self.i = min(j + 1, self.n)
            if line.strip() == delim:
                break
            body.append(line)
        if not quoted:  # an unquoted heredoc expands $(…) and `…`
            sub = _Parser("\n".join(body))
            sub._dq(None)
            self.segments.extend(sub.segments)

    def _word(self) -> Word:
        buf: list[str] = []
        dynamic = quoted = False
        while self.i < self.n:
            c = self.s[self.i]
            if c in " \t\n;&|()<>":
                break
            if c == "\\":
                if self.i + 1 < self.n and self.s[self.i + 1] != "\n":
                    buf.append(self.s[self.i + 1])
                self.i += 2
                quoted = True
            elif c == "'":
                j = self.s.find("'", self.i + 1)
                j = self.n if j < 0 else j
                buf.append(self.s[self.i + 1:j])
                self.i = j + 1
                quoted = True
            elif c == '"':
                self.i += 1
                text, dyn = self._dq('"')
                buf.append(text)
                dynamic |= dyn
                quoted = True
            elif self.s.startswith("$'", self.i):
                j, part = self.i + 2, []
                while j < self.n and self.s[j] != "'":
                    if self.s[j] == "\\" and j + 1 < self.n:
                        j += 1
                    part.append(self.s[j])
                    j += 1
                buf.append("".join(part))
                self.i = j + 1
                quoted = True
            elif c == "$":
                buf.append(self._dollar())
                dynamic = True
            elif c == "`":
                self._backtick()
                buf.append("`…`")
                dynamic = True
            else:
                buf.append(c)
                self.i += 1
        return _word("".join(buf), dynamic, quoted)

    def _dq(self, end: str | None) -> tuple[str, bool]:
        """Double-quoted text (end='"') or an unquoted heredoc body (end=None)."""
        buf: list[str] = []
        dynamic = False
        while self.i < self.n:
            c = self.s[self.i]
            if end and c == end:
                self.i += 1
                break
            if c == "\\" and self.i + 1 < self.n:
                nxt = self.s[self.i + 1]
                if nxt != "\n":
                    buf.append(nxt if nxt in '$`"\\' else c + nxt)
                self.i += 2
            elif c == "$":
                buf.append(self._dollar())
                dynamic = True
            elif c == "`":
                self._backtick()
                buf.append("`…`")
                dynamic = True
            else:
                buf.append(c)
                self.i += 1
        return "".join(buf), dynamic

    def _skip_balanced(self, start: int, open_: str, close: str) -> int:
        depth, j = 0, start
        while j < self.n:
            if self.s[j] == open_:
                depth += 1
            elif self.s[j] == close:
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        return self.n

    def _dollar(self) -> str:
        start = self.i
        if self.s.startswith("$((", self.i):
            self.i = self._skip_balanced(self.i + 1, "(", ")")
        elif self.s.startswith("$(", self.i):
            self.i += 2
            self.parse(")")
            return "$(…)"
        elif self.s.startswith("${", self.i):
            self.i = self._skip_balanced(self.i + 1, "{", "}")
        else:
            m = re.compile(r"\$(?:[A-Za-z_][A-Za-z0-9_]*|[0-9#?@*!$-])?").match(self.s, self.i)
            self.i = m.end()
        return self.s[start:self.i]

    def _backtick(self) -> None:
        j = self.i + 1
        while j < self.n and self.s[j] != "`":
            j += 2 if self.s[j] == "\\" else 1
        inner = self.s[self.i + 1:j].replace("\\`", "`")
        self.i = j + 1
        sub = _Parser(inner)
        sub.parse()
        self.segments.extend(sub.segments)


class Cmd:
    """A simple command: words from the command name on, its redirections, env -C dir."""

    def __init__(self, words: list[Word], redirects: list, chdir: str | None) -> None:
        self.words, self.redirects, self.chdir = words, redirects, chdir

    @property
    def name(self) -> str:
        return self.words[0].rsplit("/", 1)[-1] if self.words else ""


def _command_start(words: list[Word]) -> tuple[list[Word], str | None]:
    """Skip keywords, VAR=…, env and wrappers — to the command that actually runs."""
    i, chdir = 0, None
    words = list(words)
    while i < len(words):
        w = words[i]
        base = w.rsplit("/", 1)[-1]
        if w in KEYWORDS or ASSIGN_RE.match(w):
            i += 1
        elif base == "env":
            i += 1
            while i < len(words):
                a = words[i]
                if a in ("-C", "--chdir") and i + 1 < len(words):
                    chdir = words[i + 1]
                    i += 2
                elif a.startswith("--chdir="):
                    chdir = a.split("=", 1)[1]
                    i += 1
                elif a in ("-S", "--split-string") and i + 1 < len(words):
                    words[i:i + 2] = [_word(x) for x in words[i + 1].split()]
                elif a.startswith("--split-string="):
                    words[i:i + 1] = [_word(x) for x in a.split("=", 1)[1].split()]
                elif a in ("-u", "--unset"):
                    i += 2
                elif a.startswith("-") or ASSIGN_RE.match(a):
                    i += 1
                else:
                    break
        elif base in WRAPPERS:
            i += 1
            positional = WRAPPER_POSITIONAL.get(base, 0)
            while i < len(words):
                a = words[i]
                if a == "--":
                    i += 1
                    break
                if a in WRAPPERS[base]:
                    i += 2
                elif a.startswith("-") and len(a) > 1:
                    i += 1
                elif positional:
                    positional -= 1
                    i += 1
                else:
                    break
        else:
            break
    return words[i:], chdir


def _nested(words: list[Word]) -> str | None:
    """The command string of `bash -c '…'` / `eval …`."""
    name = words[0].rsplit("/", 1)[-1] if words else ""
    if name == "eval":
        return " ".join(words[1:])
    if name in SHELLS:
        for k, w in enumerate(words[1:], start=1):
            if w.startswith("-") and not w.startswith("--") and "c" in w[1:]:
                rest = [x for x in words[k + 1:] if not x.startswith("-")]
                return rest[0] if rest else None
            if not w.startswith("-"):
                return None
    return None


def commands(command: str, _depth: int = 0) -> list[Cmd]:
    """Every simple command the line would run, in reading order."""
    parser = _Parser(command)
    parser.parse()
    out = []
    for seg in parser.segments:
        words, chdir = _command_start(seg.words)
        out.append(Cmd(words, seg.redirects, chdir))
        inner = _nested(words)
        if inner is not None and _depth < 5:
            out.extend(commands(inner, _depth + 1))
    return out


def git_split(words: list[Word]) -> tuple[str, list[Word], list[str], list[str]]:
    """`git [global options] <sub> args…` → (sub, args, -C dirs, -c configs)."""
    i, dirs, configs = 1, [], []
    while i < len(words):
        w = words[i]
        if w in GIT_OPTS_WITH_VALUE:
            value = words[i + 1] if i + 1 < len(words) else ""
            if w == "-C":
                dirs.append(value)
            elif w in ("-c", "--config-env"):
                configs.append(value)
            i += 2
        elif w.startswith("-"):
            if w.startswith("--config-env="):
                configs.append(w.split("=", 1)[1])
            i += 1
        else:
            return w, words[i + 1:], dirs, configs
    return "", [], dirs, configs


def _short_flags(word: str, with_value: str = "") -> tuple[str, bool]:
    """Letters of a short-option cluster (-uf → "uf"); stops at a letter that takes a value.
    Returns (letters, whether the next word is that value)."""
    letters = word[1:]
    for k, ch in enumerate(letters):
        if ch in with_value:
            return letters[:k + 1], k == len(letters) - 1
    return letters, False


def _is_short(word: str) -> bool:
    return word.startswith("-") and not word.startswith("--") and len(word) > 1


# --- the repository ----------------------------------------------------------


def _git(args: list[str], cwd: str) -> str | None:
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


class GitRepo:
    """Answers about the real repository (tests use a fake with the same methods)."""

    def __init__(self, root: str) -> None:
        self.root = root
        self._main: str | None = None

    def main_branch(self) -> str:
        if self._main is None:
            self._main = main_branch(self.root)
        return self._main

    def current_branch(self, cwd: str) -> str | None:
        return _git(["symbolic-ref", "-q", "--short", "HEAD"], cwd) if os.path.isdir(cwd) else None

    def tag_exists(self, name: str, cwd: str) -> bool:
        return os.path.isdir(cwd) and _git(["show-ref", "--verify", "--quiet", f"refs/tags/{name}"], cwd) is not None


def main_branch(root: str) -> str:
    """MAIN_BRANCH from scripts/merge-feature.sh, else origin/HEAD, else main."""
    try:
        text = (Path(root) / "scripts" / "merge-feature.sh").read_text(encoding="utf-8")
        m = re.search(r"""^MAIN_BRANCH=(['"]?)([^'"\s]+)\1""", text, re.M)
        if m and "<" not in m.group(2):
            return m.group(2)
    except OSError:
        pass
    head = _git(["symbolic-ref", "--short", "refs/remotes/origin/HEAD"], root) if os.path.isdir(root) else None
    if head and "/" in head:
        return head.split("/", 1)[1]
    return "main"


def read_fences(root: str) -> dict[str, str]:
    """KEY=value lines of .claude/fences.env (# comments, optional quotes)."""
    values = {}
    try:
        lines = (Path(root) / FENCES_FILE).read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        m = re.match(r"""\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(['"]?)([^'"#\s]*)\2""", line)
        if m:
            values[m.group(1)] = m.group(3)
    return values


def fence_level(root: str) -> str:
    level = read_fences(root).get("FENCE_LEVEL", "") or DEFAULT_LEVEL
    if level not in LEVELS:
        print(f"guard: unknown FENCE_LEVEL={level!r} in {FENCES_FILE} — using '{DEFAULT_LEVEL}'", file=sys.stderr)
        return DEFAULT_LEVEL
    return level


def project_root(cwd: str) -> str:
    """The project: $CLAUDE_PROJECT_DIR (set for every hook), else the git top level of cwd."""
    return os.environ.get("CLAUDE_PROJECT_DIR") or _git(["rev-parse", "--show-toplevel"], cwd) or cwd


def opted_in(root: str) -> bool:
    """The project uses the fences: it has .claude/fences.env (base and /dark-factory:init create it)."""
    return (Path(root) / FENCES_FILE).is_file()


# --- decisions ---------------------------------------------------------------


def _join(base: str, path: str) -> str:
    return os.path.normpath(os.path.join(base, os.path.expanduser(path)))


def is_fence_path(path: str, cwd: str) -> bool:
    return bool(path) and bool(FENCE_FILE_RE.search(_join(cwd, path).replace(os.sep, "/")))


def _release_tag(name: str) -> bool:
    return any(fnmatch.fnmatchcase(name, p) for p in RELEASE_TAGS)


def check_push(args: list[Word], cwd: str, repo) -> tuple | None:
    force = no_verify = all_refs = all_tags = delete = False
    pos: list[Word] = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            pos.extend(args[i + 1:])
            break
        if a in ("-o", "--push-option", "--repo", "--receive-pack", "--exec"):
            i += 2
            continue
        name = a.split("=", 1)[0]
        if name in ("--force", "--force-with-lease", "--mirror"):
            force = True
        elif name == "--no-verify":
            no_verify = True
        elif name in ("--all", "--branches"):
            all_refs = True
        elif name in ("--tags", "--follow-tags"):
            all_tags = True
        elif name == "--delete":
            delete = True
        elif _is_short(a):
            letters, takes_next = _short_flags(a, "o")
            force |= "f" in letters
            delete |= "d" in letters
            i += takes_next
        elif not a.startswith("-"):
            pos.append(a)
        i += 1
    refspecs = pos[1:]
    if force or any(r.startswith("+") for r in refspecs):
        return FORCE
    if no_verify:
        return NO_VERIFY
    if all_tags:
        return TAG
    main = repo.main_branch()
    if all_refs:
        return MAIN
    if not refspecs:
        return MAIN if not delete and repo.current_branch(cwd) == main else None
    j = 0
    while j < len(refspecs):
        ref = refspecs[j]
        if ref == "tag" and j + 1 < len(refspecs):
            kind, name = "tag", str(refspecs[j + 1])
            j += 2
        else:
            kind, name = _classify_refspec(ref, delete, cwd, repo)
            j += 1
        if kind == "branch" and name == main:
            return MAIN
        if kind == "tag" and _release_tag(name):
            return TAG
    return None


def _classify_refspec(ref: Word, delete: bool, cwd: str, repo) -> tuple[str, str | None]:
    src, sep, dst = ref.lstrip("+").partition(":")
    if not sep or not dst:
        dst = src
    if "$" in dst or "`" in dst:  # computed at run time — assume the current branch
        return "branch", repo.current_branch(cwd)
    if dst in ("HEAD", "@"):
        return "branch", repo.current_branch(cwd)
    if dst.startswith("refs/heads/"):
        return "branch", dst[len("refs/heads/"):]
    if dst.startswith("refs/tags/"):
        return "tag", dst[len("refs/tags/"):]
    if dst.startswith("refs/"):
        return "other", dst
    if sep and src in ("HEAD", "@"):
        return "branch", dst
    lookup = src if (sep and src) else dst
    if repo.tag_exists(lookup, cwd) or (RELEASE_TAG_SHAPE.fullmatch(dst) and (delete or not sep or not src)):
        return "tag", dst
    return "branch", dst


def check_commit(args: list[Word]) -> tuple | None:
    value_long = {"--message", "--file", "--author", "--date", "--template", "--reuse-message",
                  "--reedit-message", "--fixup", "--squash", "--trailer", "--cleanup", "--pathspec-from-file"}
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            break
        if a == "--no-verify":
            return NO_VERIFY
        if a in value_long:
            i += 1
        elif _is_short(a):
            letters, takes_next = _short_flags(a, "mFCctuS")
            if "n" in letters:
                return NO_VERIFY
            i += takes_next and letters[-1] in "mFCct"
        i += 1
    return None


def check_git(words: list[Word], cwd: str, repo) -> tuple | None:
    sub, args, dirs, configs = git_split(words)
    for d in dirs:
        cwd = _join(cwd, d)
    if any(c.lower().startswith("core.hookspath") for c in configs):
        return NO_VERIFY
    main = repo.main_branch()
    if sub == "push":
        return check_push(args, cwd, repo)
    if sub == "commit":
        return check_commit(args)
    if sub == "branch":
        deleting = any(a == "--delete" or (_is_short(a) and set(a[1:]) & {"d", "D"}) for a in args)
        names = [a.removeprefix("refs/heads/") for a in args if not a.startswith("-")]
        if deleting and main in names:
            return MAIN_BRANCH_DELETE
    if sub == "reset" and "--hard" in args and repo.current_branch(cwd) == main:
        return RESET_MAIN
    if sub == "config":
        reading = {"--get", "--get-all", "--get-regexp", "-l", "--list", "get", "list"}
        lowered = [a.lower() for a in args]
        if "core.hookspath" in lowered and not reading & set(args):
            k = lowered.index("core.hookspath")
            value = args[k + 1] if k + 1 < len(args) else None
            if {"--unset", "--unset-all", "unset"} & set(args) or (value is not None and value != ".githooks"):
                return NO_VERIFY
    return None


def check_gh(words: list[Word]) -> tuple | None:
    pos, i = [], 1
    while i < len(words):
        w = words[i]
        if w in ("-R", "--repo"):
            i += 2
            continue
        if not w.startswith("-"):
            pos.append(w)
        i += 1
    if pos[:2] == ["pr", "merge"]:
        return MERGE
    if pos[:2] == ["pr", "review"] and any(
        w == "--approve" or (_is_short(w) and "a" in w[1:]) for w in words[3:]
    ):
        return APPROVE
    if pos[:1] == ["api"]:
        text = " ".join(words)
        put = re.search(r"(?:^|\s)(?:-X\s*|--method[=\s])PUT\b", text, re.I)
        if GH_MERGE_API_RE.search(text) or (put and GH_MERGE_REST_RE.search(text)):
            return MERGE
    return None


WRITE_ANY_ARG = {"mv", "rm", "tee", "truncate", "chmod", "chown", "unlink", "shred"}
WRITE_LAST_ARG = {"cp", "install", "ln", "rsync"}
WRITE_IN_PLACE = {"sed", "perl"}


def check_fence_write(cmd: Cmd, cwd: str) -> tuple | None:
    """A Bash write to a fence file: an output redirection, mv/rm/tee/cp…, sed -i."""
    for op, target in cmd.redirects:
        if ">" in op and not (op == ">&" and (target.isdigit() or target == "-")) and is_fence_path(target, cwd):
            return FENCE_EDIT
    args = [a for a in cmd.words[1:] if not a.startswith("-")]
    name = cmd.name
    if name in WRITE_ANY_ARG or (name in WRITE_IN_PLACE and any(
        a.startswith("-i") or a == "--in-place" or (name == "perl" and _is_short(a) and "i" in a) for a in cmd.words[1:]
    )):
        if any(is_fence_path(a, cwd) for a in args):
            return FENCE_EDIT
    if name in WRITE_LAST_ARG and len(args) >= 2:
        dest = args[-1]
        if is_fence_path(dest, cwd) or any(is_fence_path(os.path.join(dest, os.path.basename(a)), cwd) for a in args[:-1]):
            return FENCE_EDIT
    if name == "dd" and any(a.startswith("of=") and is_fence_path(a[3:], cwd) for a in cmd.words[1:]):
        return FENCE_EDIT
    return None


def check_command(command: str, cwd: str, repo, level: str) -> tuple | None:
    strict = level != "solo"
    for cmd in commands(command):
        if not cmd.words and not cmd.redirects:
            continue
        if cmd.name in ("cd", "pushd"):
            target = cmd.words[1] if len(cmd.words) > 1 else Word("~")
            if not target.dynamic and target != "-":
                cwd = _join(cwd, target)
            continue
        here = _join(cwd, cmd.chdir) if cmd.chdir else cwd
        reason = None
        if cmd.name == "git":
            reason = check_git(cmd.words, here, repo)
        elif cmd.name == "gh" and strict:
            reason = check_gh(cmd.words)
        if reason is None and strict:
            reason = check_fence_write(cmd, here)
        if reason:
            return reason
    return None


def decide(hook: dict, repo, level: str, cwd: str) -> tuple | None:
    tool = hook.get("tool_name")
    inp = hook.get("tool_input") or {}
    if tool == "Bash":
        return check_command(inp.get("command") or "", cwd, repo, level)
    if tool in EDIT_TOOLS and level != "solo":
        if is_fence_path(inp.get("file_path") or inp.get("notebook_path") or "", cwd):
            return FENCE_EDIT
    return None


def deny(reason: tuple, main: str = "main") -> dict:
    what, advice = (part.replace("{main}", main) for part in reason)
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": f"⛔ guard: {what}. {advice} {BYPASS}",
        }
    }


def main() -> int:
    if os.environ.get("GUARD") == "off":
        return 0
    try:
        hook = json.load(sys.stdin)
    except ValueError as exc:
        print(f"guard: unreadable hook input ({exc}) — not checked", file=sys.stderr)
        return 0
    cwd = hook.get("cwd") or os.getcwd()
    root = project_root(cwd)
    if not opted_in(root):
        return 0
    repo = GitRepo(root)
    try:
        reason = decide(hook, repo, fence_level(root), cwd)
    except Exception as exc:  # a fence that crashes must not open: deny and say why
        reason = (
            f"the guard could not read this command ({type(exc).__name__}: {exc})",
            "Rewrite it in a plainer form, or ask the human.",
        )
    if reason:
        print(json.dumps(deny(reason, repo.main_branch()), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
