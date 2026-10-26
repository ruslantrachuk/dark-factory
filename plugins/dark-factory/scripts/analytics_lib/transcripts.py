"""Claude Code transcripts → turns: who drove each one, where its tokens went, the owner's friction.

A turn is a prompt and the assistant records up to the next prompt of the same session. Its kind comes from the
prompt: `owner` (typed by the owner, directly or relayed by the claude.ai bridge), `on_call` (a client-chat message
from anyone else), `monitor` (the production monitor's SDK runs), `unattended` (scheduled fires, task notifications,
messages from other sessions). A subagent's records go to the turn of its parent session that was running when they
were written. Messages are deduplicated by their API id: one response is written as several lines.
Seam: transcripts = Claude Code's local JSONL (~/.claude/projects). To use another agent runtime, rewrite this module.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from . import store

KINDS = ("owner", "on_call", "monitor", "unattended")
SPLITS = ("direct", "helpers", "pipeline")
TOKEN_FIELDS = (("input", "input_tokens"), ("cache_write", "cache_creation_input_tokens"),
                ("cache_read", "cache_read_input_tokens"), ("output", "output_tokens"))
PIPELINE_AGENTS = ("workflow-subagent",)  # plus every `dark-factory:*` role the pipeline fans out
# Swear roots matched at a word start, case-insensitively. Data, not prose: the owner's languages (Russian, English).
SWEAR_ROOTS = ("хуй", "хуе", "хуё", "хуя", "пизд", "ебан", "ебат", "ебал", "ёб", "бля", "сука", "суки", "нахер",
               "нахуй", "херн", "долбо", "мудак", "мудил", "говн", "fuck", "shit", "bullshit", "damn", "wtf")
TEST_CMD_RE = r"\b(pytest|npm (run )?test|vitest|playwright|go test|cargo test|jest)\b"
INTERRUPT = "[Request interrupted by user"
REJECTED = "doesn't want to proceed with this tool use"
CHANNEL_USER = re.compile(r'<channel\b[^>]*\buser="([^"]*)"')
# a work branch named in a command (`git checkout -b`, `git push`, `merge-feature.sh`): the contract's branch types
BRANCH_RE = re.compile(r"(?<![\w/])(?:feat|fix|ui|refactor|chore|docs)/[A-Za-z0-9][A-Za-z0-9._-]*")
BRIDGE = re.compile(r'<cross-session-message\b[^>]*\bfrom="bridge:')


def zero() -> dict[str, int]:
    return {k: 0 for k, _ in TOKEN_FIELDS}


def add(a: dict[str, int], b: dict[str, int]) -> None:
    for k in a:
        a[k] += b.get(k, 0)


@dataclass
class Turn:
    session: str
    start: str
    kind: str
    typed: bool = False
    swear: bool = False
    interrupts: int = 0
    rejected: int = 0
    test_calls: int = 0
    tokens: dict[str, dict[str, int]] = field(default_factory=lambda: {s: zero() for s in SPLITS})
    test_tokens: dict[str, int] = field(default_factory=zero)
    branches: Counter = field(default_factory=Counter)
    mentions: set = field(default_factory=set)  # work branches named in the turn's commands

    @property
    def branch(self) -> str | None:
        return self.branches.most_common(1)[0][0] if self.branches else None

    def total(self) -> dict[str, int]:
        t = zero()
        for s in SPLITS:
            add(t, self.tokens[s])
        return t


@dataclass
class PrLink:
    session: str
    ts: str
    repo: str
    number: int


def records(path: Path):
    """The JSON records of a transcript file; a line that does not parse is skipped."""
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if isinstance(r, dict):
                    yield r
    except OSError:
        return


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    return ""


def is_tool_result(content) -> bool:
    return isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content)


def tool_result_text(content) -> str:
    out = []
    for b in content if isinstance(content, list) else []:
        if isinstance(b, dict) and b.get("type") == "tool_result":
            c = b.get("content")
            out.append(c if isinstance(c, str) else text_of(c))
    return "\n".join(out)


def prompt_kind(r: dict, text: str, settings: store.Settings) -> str | None:
    """The kind of turn this user record starts, or None when it starts none."""
    origin = r.get("origin") if isinstance(r.get("origin"), dict) else {}
    kind = origin.get("kind")
    # a channel or peer message is written as a meta record with an origin; a meta record without one is an insert
    if (r.get("isMeta") and kind is None) or not text.strip() or text.startswith(INTERRUPT):
        return None
    if r.get("entrypoint") == "sdk-py":
        return "monitor"
    m = CHANNEL_USER.search(text)
    if kind == "channel" or (kind is None and m):
        return "owner" if m and m.group(1) in settings.owner else "on_call"
    if kind == "peer" or (kind is None and "<cross-session-message" in text):
        return "owner" if str(origin.get("from", "")).startswith("bridge:") or BRIDGE.search(text) else "unattended"
    if kind == "human":
        return "owner"
    if kind is not None:
        return "unattended"
    stripped = text.lstrip()
    if stripped.startswith(("<task-notification", "<scheduled")):
        return "unattended"
    if stripped.startswith(("<local-command", "<system-reminder", "<bash-")):
        return None
    if r.get("entrypoint") == "sdk-cli":
        return "unattended"  # a `claude -p` run (queue review, delivery): typed prompts there carry an origin
    return "owner"  # a terminal session, or an older transcript without `origin`: a plain prompt is typed


def usage_of(r: dict) -> dict[str, int] | None:
    m = r.get("message")
    u = m.get("usage") if isinstance(m, dict) else None
    if not isinstance(u, dict):
        return None
    try:
        return {k: int(u.get(src) or 0) for k, src in TOKEN_FIELDS}
    except (TypeError, ValueError):
        return None


def valid_ts(ts) -> bool:
    if not isinstance(ts, str):
        return False
    try:
        store.parse_ts(ts)
    except ValueError:
        return False
    return True


def swear_re(settings: store.Settings) -> re.Pattern:
    roots = [re.escape(r) for r in (*SWEAR_ROOTS, *settings.swear)]
    return re.compile(r"(?<![\w])(" + "|".join(roots) + r")", re.I)


def test_re(settings: store.Settings) -> re.Pattern:
    return re.compile("|".join([TEST_CMD_RE, *settings.test_cmds]))


def commands(r: dict) -> list[str]:
    m = r.get("message")
    blocks = m.get("content", []) if isinstance(m, dict) and isinstance(m.get("content"), list) else []
    return [str((b.get("input") or {}).get("command", "")) for b in blocks
            if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Bash"]


def runs_tests(r: dict, pattern: re.Pattern) -> int:
    return sum(1 for c in commands(r) if pattern.search(c))


def split_of(agent_type: str | None) -> str:
    if not agent_type:
        return "helpers"
    if agent_type in PIPELINE_AGENTS or agent_type.startswith("dark-factory:"):
        return "pipeline"
    return "helpers"


def unique_files(dirs: list[Path]) -> list[Path]:
    seen, out = set(), []
    for d in dirs:
        for p in sorted(d.rglob("*.jsonl")):
            real = p.resolve()
            if real not in seen:
                seen.add(real)
                out.append(p)
    return out


def subagent_type(path: Path, recs: list[dict]) -> str | None:
    meta = path.with_name(path.name[:-len(".jsonl")] + ".meta.json")
    try:
        t = json.loads(meta.read_text()).get("agentType")
        if t:
            return t
    except (OSError, ValueError, AttributeError):
        pass
    for r in recs:
        if r.get("attributionAgent"):
            return str(r["attributionAgent"])
    return None


def read_project(dirs: list[Path], settings: store.Settings) -> tuple[list[Turn], list[PrLink]]:
    swear, tests = swear_re(settings), test_re(settings)
    turns_by_session: dict[str, list[Turn]] = {}
    links: list[PrLink] = []
    subagents: list[tuple[str, str, list[dict]]] = []
    seen_prompts: set[str] = set()  # a forked or resumed session copies its history into a new file

    # message id → (turn, split, usage so far, test calls): one response is written as several lines whose usage
    # grows while it streams, so the largest value of each field is the response's
    messages: dict[str, list] = {}

    def count(turn: Turn, r: dict, split: str) -> None:
        u = usage_of(r)
        if u is None:
            return
        mid = (r.get("message") or {}).get("id") or r.get("uuid")
        entry = messages.setdefault(mid, [turn, split, zero(), 0])
        entry[2] = {k: max(entry[2][k], u[k]) for k in entry[2]}
        entry[3] = max(entry[3], runs_tests(r, tests))
        for c in commands(r):
            turn.mentions.update(BRANCH_RE.findall(c))

    for path in unique_files(dirs):
        if "subagents" in path.parts:
            # <session>/subagents/agent-*.jsonl, or <session>/subagents/workflows/<run>/agent-*.jsonl for a workflow
            i = len(path.parts) - 1 - path.parts[::-1].index("subagents")
            recs = list(records(path))
            split = "pipeline" if "workflows" in path.parts[i:] else split_of(subagent_type(path, recs))
            subagents.append((path.parts[i - 1], split, recs))
            continue
        sid = path.stem
        turns = turns_by_session.setdefault(sid, [])
        copied = False  # inside a stretch of history copied from another file: its friction is counted there
        for r in records(path):
            ts = r.get("timestamp")
            if r.get("type") == "pr-link":
                if r.get("prRepository") and str(r.get("prNumber", "")).isdigit() and valid_ts(ts):
                    links.append(PrLink(r.get("sessionId") or sid, ts, str(r["prRepository"]), int(r["prNumber"])))
                continue
            if not valid_ts(ts):
                continue
            msg = r.get("message") if isinstance(r.get("message"), dict) else {}
            content = msg.get("content")
            if r.get("type") == "user":
                if is_tool_result(content):
                    if turns and not copied and REJECTED in tool_result_text(content):
                        turns[-1].rejected += 1
                    continue
                text = text_of(content)
                if text.startswith(INTERRUPT):
                    if turns and not copied:
                        turns[-1].interrupts += 1
                    continue
                kind = prompt_kind(r, text, settings)
                if kind and r.get("uuid"):
                    copied = r["uuid"] in seen_prompts
                    seen_prompts.add(r["uuid"])
                if kind and not copied:
                    turns.append(Turn(sid, ts, kind, typed=kind == "owner",
                                      swear=kind == "owner" and bool(swear.search(text))))
            elif r.get("type") == "assistant" and turns and not copied:
                count(turns[-1], r, "direct")
                if r.get("gitBranch"):
                    turns[-1].branches[r["gitBranch"]] += 1

    for sid, split, recs in subagents:
        turns = turns_by_session.get(sid) or []
        for r in recs:
            ts = r.get("timestamp")
            if r.get("type") != "assistant" or not valid_ts(ts) or not turns:
                continue
            turn = next((t for t in reversed(turns) if t.start <= ts), turns[0])
            count(turn, r, split)

    for turn, split, u, n in messages.values():
        add(turn.tokens[split], u)
        if n:
            turn.test_calls += n
            add(turn.test_tokens, u)
    links = list({(l.repo, l.number): l for l in sorted(links, key=lambda l: l.ts, reverse=True)}.values())
    links.sort(key=lambda l: l.ts)
    all_turns = [t for ts in turns_by_session.values() for t in ts]
    all_turns.sort(key=lambda t: (t.start, t.session))
    return all_turns, links


@dataclass
class PrCost:
    tokens: dict[str, int] = field(default_factory=zero)
    pipeline: bool = False
    by_kind: Counter = field(default_factory=Counter)

    @property
    def kind(self) -> str:
        return self.by_kind.most_common(1)[0][0] if self.by_kind else "owner"


def assign(turns: list[Turn], links: list[PrLink], branches: dict[tuple[str, int], str]
           ) -> list[tuple[str, int] | None]:
    """The PR each turn led up to: the first PR its session linked at or after the turn started (a `pr-link` record
    is written when the session opens the PR); else a PR whose head branch the turn's commands name; else the PR
    whose head is the turn's `gitBranch`; None when none."""
    by_session: dict[str, list[PrLink]] = {}
    for link in sorted(links, key=lambda l: l.ts):
        by_session.setdefault(link.session, []).append(link)
    head_to_pr = {head: pr for pr, head in branches.items() if head}
    out: list[tuple[str, int] | None] = []
    for t in turns:
        session_links = by_session.get(t.session)
        link = next((l for l in session_links or [] if l.ts >= t.start), None)
        if link:
            out.append((link.repo, link.number))
            continue
        named = sorted(head_to_pr[m] for m in t.mentions if m in head_to_pr)
        out.append(named[0] if named else head_to_pr.get(t.branch) if t.branch else None)
    return out


def attribute(turns: list[Turn], links: list[PrLink], branches: dict[tuple[str, int], str]
              ) -> tuple[dict[tuple[str, int], PrCost], dict[str, int]]:
    """Tokens per PR (see assign) and the unattributed rest."""
    costs: dict[tuple[str, int], PrCost] = {}
    rest = zero()
    for t, pr in zip(turns, assign(turns, links, branches)):
        total = t.total()
        if pr is None:
            add(rest, total)
            continue
        cost = costs.setdefault(pr, PrCost())
        add(cost.tokens, total)
        cost.pipeline |= any(t.tokens["pipeline"].values())
        cost.by_kind[t.kind] += sum(total.values())
    return costs, rest
