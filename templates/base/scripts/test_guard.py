"""Fence guard tests: python3 scripts/test_guard.py (stdlib only)."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))

import guard  # noqa: E402

HEREDOC_COMMIT = (
    'git commit -m "$(cat <<\'EOF\'\n'
    "docs: never use git push --force or gh pr merge (see why)\n"
    "\n"
    "Don't pass --no-verify; tag v1.2 is pushed by release.sh; git push origin main is denied.\n"
    "EOF\n"
    ')"'
)


class FakeRepo:
    def __init__(self, main="main", current="r1/feat-x-proj-a1b2", tags=()):
        self.main, self.current, self.tags = main, current, set(tags)

    def main_branch(self):
        return self.main

    def current_branch(self, cwd):
        return self.current

    def tag_exists(self, name, cwd):
        return name in self.tags


def check(command, level="standard", **repo):
    return guard.check_command(command, "/repo", FakeRepo(**repo), level)


class ParseTest(unittest.TestCase):
    def names(self, command):
        return [c.words[:2] for c in guard.commands(command) if c.words]

    def test_split_on_operators_and_newlines(self):
        cmds = self.names("git status && git diff || ls; pwd | wc -l & date\ngit log")
        self.assertEqual([w[0] for w in cmds], ["git", "git", "ls", "pwd", "wc", "date", "git"])

    def test_quoted_text_is_one_word_not_a_command(self):
        (cmd,) = guard.commands("git commit -m 'wip; git push -f && gh pr merge'")
        self.assertEqual(cmd.words[3], "wip; git push -f && gh pr merge")

    def test_heredoc_body_is_not_a_command_but_rest_of_line_is(self):
        cmds = guard.commands("cat <<'EOF' > out.txt && git push -f\ngh pr merge 1\nEOF\ngit status")
        self.assertEqual([c.words[0] for c in cmds], ["cat", "git", "git"])
        self.assertEqual(cmds[0].redirects[-1], (">", "out.txt"))

    def test_substitutions_are_commands(self):
        names = [c.name for c in guard.commands('echo "$(gh pr list)" `git log` $(date)')]
        self.assertEqual(sorted(names), ["date", "echo", "gh", "git"])

    def test_unquoted_heredoc_expands_substitutions(self):
        names = [c.name for c in guard.commands("cat <<EOF\n$(gh pr merge 1)\nEOF")]
        self.assertIn("gh", names)

    def test_prefixes_and_wrappers(self):
        (cmd,) = guard.commands("FOO=1 env -C /x BAR=2 nohup timeout 5 /usr/bin/git -C y push")
        self.assertEqual(cmd.name, "git")
        self.assertEqual(cmd.chdir, "/x")

    def test_nested_shell(self):
        names = [c.name for c in guard.commands("bash -lc 'git push --force' && eval git status")]
        self.assertEqual(names, ["bash", "git", "eval", "git"])

    def test_escapes_and_ansi_c(self):
        (cmd,) = guard.commands(r"git push \-\-force $'--no-verify'")
        self.assertEqual(cmd.words[2:], ["--force", "--no-verify"])


class MergeTest(unittest.TestCase):
    def test_gh_pr_merge_denied(self):
        self.assertIs(check("gh pr merge 12 --squash"), guard.MERGE)
        self.assertIs(check("gh pr merge --auto --merge feat"), guard.MERGE)
        self.assertIs(check("cd /repo && GH_HOST=github.com gh pr merge 3"), guard.MERGE)
        self.assertIs(check("bash -c 'gh pr merge 3'"), guard.MERGE)
        self.assertIs(check('echo "$(gh pr merge 3)"'), guard.MERGE)

    def test_merge_api_denied(self):
        self.assertIs(check("gh api -X PUT repos/o/r/pulls/12/merge"), guard.MERGE)
        self.assertIs(check("gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'"), guard.MERGE)
        self.assertIsNone(check("gh api repos/o/r/pulls/12/merge"))  # GET: "is it merged?"

    def test_merge_feature_script_allowed(self):
        self.assertIsNone(check('scripts/merge-feature.sh r1/feat-x-proj-a1b2 "Title" --accepted-by "Ann"'))
        self.assertIsNone(check("bash scripts/merge-feature.sh r1/feat-x --accepted-by Ann --skip-ci 'Actions billing'"))

    def test_other_gh_allowed(self):
        for cmd in ("gh pr view 12", "gh pr create --fill", "gh pr checks feat --watch", "gh pr list --search merge"):
            self.assertIsNone(check(cmd), cmd)

    def test_approve_denied(self):
        self.assertIs(check("gh pr review 12 --approve"), guard.APPROVE)
        self.assertIsNone(check("gh pr review 12 --comment -b 'looks fine'"))

    def test_solo_allows_direct_merge(self):
        self.assertIsNone(check("gh pr merge 12", level="solo"))
        self.assertIsNone(check("gh pr review 12 --approve", level="solo"))


class ForcePushTest(unittest.TestCase):
    def test_force_flags(self):
        for cmd in (
            "git push -f",
            "git push --force origin feat",
            "git push origin feat --force-with-lease",
            "git push --force-with-lease=feat:abc origin feat",
            "git push -uf origin feat",
            "git push --mirror backup",
            "git -C ../other push -f origin feat",
        ):
            self.assertIs(check(cmd, level="solo"), guard.FORCE, cmd)

    def test_plus_refspec(self):
        self.assertIs(check("git push origin +feat"), guard.FORCE)
        self.assertIs(check("git push origin +HEAD:refs/heads/feat"), guard.FORCE)

    def test_normal_push_allowed(self):
        for cmd in ("git push", "git push -u origin r1/feat-x-proj-a1b2", "git push origin HEAD", "git push origin feat:feat"):
            self.assertIsNone(check(cmd), cmd)


class MainBranchTest(unittest.TestCase):
    def test_direct_push_to_main(self):
        for cmd in (
            "git push origin main",
            "git push origin HEAD:main",
            "git push origin feat:refs/heads/main",
            "git push origin :main",
            "git push origin --delete main",
            "git push --all origin",
        ):
            self.assertIs(check(cmd, level="solo"), guard.MAIN, cmd)

    def test_push_while_on_main(self):
        for cmd in ("git push", "git push origin", "git push origin HEAD", "git push -u origin $(git branch --show-current)"):
            self.assertIs(check(cmd, current="main"), guard.MAIN, cmd)

    def test_feature_push_while_on_main_allowed(self):
        self.assertIsNone(check("git push origin r1/feat-x-proj-a1b2", current="main"))

    def test_configured_main_branch(self):
        self.assertIs(check("git push origin master", main="master"), guard.MAIN)
        self.assertIsNone(check("git push origin main", main="master"))

    def test_branch_delete_and_reset_on_main(self):
        self.assertIs(check("git branch -D main", level="solo"), guard.MAIN_BRANCH_DELETE)
        self.assertIs(check("git branch --delete --force main"), guard.MAIN_BRANCH_DELETE)
        self.assertIsNone(check("git branch -D r1/old-branch"))
        self.assertIs(check("git reset --hard origin/main", current="main", level="solo"), guard.RESET_MAIN)
        self.assertIsNone(check("git reset --hard HEAD~1"))
        self.assertIsNone(check("git reset --soft HEAD~1", current="main"))


class NoVerifyTest(unittest.TestCase):
    def test_hooks_bypass_denied(self):
        for cmd in (
            "git commit --no-verify -m wip",
            "git commit -nm wip",
            "git commit -a -n",
            "git push --no-verify",
            "git -c core.hooksPath=/dev/null commit -m x",
            "git config core.hooksPath /tmp/none",
            "git config --unset core.hooksPath",
        ):
            self.assertIs(check(cmd, level="solo"), guard.NO_VERIFY, cmd)

    def test_lookalikes_allowed(self):
        for cmd in (
            "git commit -m -n",  # -n is the message
            "git commit -mn",  # message "n"
            "git config core.hooksPath .githooks",
            "git config --get core.hooksPath",
            "git push -n origin feat",  # push -n is a dry run
        ):
            self.assertIsNone(check(cmd), cmd)


class TagTest(unittest.TestCase):
    def test_release_tags_denied(self):
        for cmd in (
            "git push origin v2026.10.22.1",
            "git push origin refs/tags/r12",
            "git push origin tag v1.0",
            "git push --tags",
            "git push origin --follow-tags",
            "git push origin :refs/tags/v1.0",
        ):
            self.assertIs(check(cmd, level="solo"), guard.TAG, cmd)

    def test_existing_local_tag_by_bare_name(self):
        self.assertIs(check("git push origin docs-snapshot", tags={"docs-snapshot"}), None)
        self.assertIs(check("git push origin rc5", tags={"rc5"}), guard.TAG)

    def test_release_script_and_other_tags_allowed(self):
        self.assertIsNone(check("scripts/release.sh"))
        self.assertIsNone(check("git push origin refs/tags/docs-snapshot"))
        self.assertIsNone(check("git tag -a v1.0 -m 'release v1.0'"))
        self.assertIsNone(check("git push origin r12/feat-x-proj-a1b2"))


class FenceFilesTest(unittest.TestCase):
    def test_edit_tools(self):
        repo = FakeRepo()
        for path in (".claude/settings.json", "/repo/.claude/settings.local.json", ".githooks/pre-push",
                     "scripts/guard.py", "/repo/.claude/worktrees/w1/scripts/merge-feature.sh", ".claude/fences.env"):
            hook = {"tool_name": "Edit", "tool_input": {"file_path": path}}
            self.assertIs(guard.decide(hook, repo, "standard", "/repo"), guard.FENCE_EDIT, path)
            self.assertIsNone(guard.decide(hook, repo, "solo", "/repo"), path)
        ok = {"tool_name": "Write", "tool_input": {"file_path": "scripts/test_guard.py"}}
        self.assertIsNone(guard.decide(ok, repo, "standard", "/repo"))

    def test_bash_writes(self):
        for cmd in (
            "echo '{}' > .claude/settings.json",
            "sed -i 's/standard/solo/' .claude/fences.env",
            "cp /tmp/guard.py scripts/",
            "rm .githooks/pre-push",
            "cd scripts && printf x >> quota.py",
            "tee scripts/merge-feature.sh < /tmp/x",
        ):
            self.assertIs(check(cmd), guard.FENCE_EDIT, cmd)
            self.assertIsNone(check(cmd, level="solo"), cmd)

    def test_reading_fence_files_allowed(self):
        for cmd in ("cat scripts/guard.py", "cp scripts/guard.py /tmp/g.py", "git diff .githooks/pre-push",
                    "sed -n 1,5p .claude/settings.json", "git add scripts/guard.py"):
            self.assertIsNone(check(cmd), cmd)


class QuotedTextIsNotACommandTest(unittest.TestCase):
    def test_messages_mentioning_fenced_commands(self):
        for cmd in (
            HEREDOC_COMMIT,
            "git commit -m 'never git push --force; gh pr merge is for merge-feature.sh'",
            'git commit -m "docs: explain --no-verify and git push origin main"',
            "git commit -F - <<'EOF'\nchore: gh pr merge && git push -f origin main\nEOF",
            'bd update proj-a1b2 --notes "next: gh pr merge after git push --force-with-lease"',
            "echo 'git push --force' | wc -c",
            "gh pr create --title 'Drop --force from deploy' --body 'gh pr merge stays with the script'",
            "grep -rn 'git push --force' docs/",
        ):
            self.assertIsNone(check(cmd), cmd)


class LevelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text):
        (Path(self.root) / ".claude").mkdir(exist_ok=True)
        (Path(self.root) / ".claude" / "fences.env").write_text(text)

    def test_default_is_standard(self):
        self.assertEqual(guard.fence_level(self.root), "standard")

    def test_level_from_file(self):
        self.write("# fence level\nFENCE_LEVEL=solo\n")
        self.assertEqual(guard.fence_level(self.root), "solo")
        self.write('FENCE_LEVEL="team"  # with review\n')
        self.assertEqual(guard.fence_level(self.root), "team")

    def test_unknown_level_falls_back_to_standard(self):
        self.write("FENCE_LEVEL=lax\n")
        with mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(guard.fence_level(self.root), "standard")

    def test_destructive_denied_at_every_level(self):
        for level in guard.LEVELS:
            self.assertIs(check("git push -f", level=level), guard.FORCE)
            self.assertIs(check("git push origin main", level=level), guard.MAIN)
            self.assertIs(check("git commit -n -m x", level=level), guard.NO_VERIFY)
            self.assertIs(check("git push origin v1.0", level=level), guard.TAG)
        self.assertIs(check("gh pr merge 1", level="team"), guard.MERGE)


class MainBranchConfigTest(unittest.TestCase):
    def test_from_merge_feature_config(self):
        with tempfile.TemporaryDirectory() as root:
            (Path(root) / "scripts").mkdir()
            script = Path(root) / "scripts" / "merge-feature.sh"
            script.write_text("set -e\nMAIN_BRANCH='trunk'\n")
            self.assertEqual(guard.main_branch(root), "trunk")
            script.write_text("MAIN_BRANCH='<main>'\n")  # placeholder not filled in → fallback
            self.assertEqual(guard.main_branch(root), "main")


class HookTest(unittest.TestCase):
    def run_main(self, hook, **env):
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, env),
            mock.patch("sys.stdin", io.StringIO(json.dumps(hook))),
            mock.patch.object(guard, "GitRepo", lambda root: FakeRepo()),
            mock.patch.object(guard, "fence_level", lambda root: "standard"),
            redirect_stdout(out),
        ):
            self.assertEqual(guard.main(), 0)
        return out.getvalue()

    def test_deny_payload_says_what_instead(self):
        out = json.loads(self.run_main({"tool_name": "Bash", "tool_input": {"command": "gh pr merge 1"}, "cwd": "/repo"}))
        spec = out["hookSpecificOutput"]
        self.assertEqual(spec["hookEventName"], "PreToolUse")
        self.assertEqual(spec["permissionDecision"], "deny")
        self.assertIn("merge-feature.sh", spec["permissionDecisionReason"])
        self.assertIn("--accepted-by", spec["permissionDecisionReason"])
        self.assertIn("GUARD=off", spec["permissionDecisionReason"])

    def test_main_branch_named_in_message(self):
        out = json.loads(self.run_main({"tool_name": "Bash", "tool_input": {"command": "git push origin main"}, "cwd": "/repo"}))
        self.assertIn("'main'", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_allowed_is_silent(self):
        self.assertEqual(self.run_main({"tool_name": "Bash", "tool_input": {"command": "git status"}, "cwd": "/repo"}), "")
        self.assertEqual(self.run_main({"tool_name": "Read", "tool_input": {"file_path": "a"}, "cwd": "/repo"}), "")

    def test_guard_off_lets_everything_through(self):
        hook = {"tool_name": "Bash", "tool_input": {"command": "git push -f origin main"}, "cwd": "/repo"}
        self.assertEqual(self.run_main(hook, GUARD="off"), "")

    def test_crash_fails_closed(self):
        hook = {"tool_name": "Bash", "tool_input": {"command": "git push"}, "cwd": "/repo"}
        with mock.patch.object(guard, "check_command", side_effect=RuntimeError("boom {main}")):
            out = json.loads(self.run_main(hook))
        self.assertIn("could not read", out["hookSpecificOutput"]["permissionDecisionReason"])


class RealRepoTest(unittest.TestCase):
    """GitRepo against a real temporary repository: current branch, tags, origin/HEAD."""

    def test_git_answers(self):
        with tempfile.TemporaryDirectory() as root:
            env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
            run = lambda *a: subprocess.run(["git", *a], cwd=root, env=env, check=True, capture_output=True)  # noqa: E731
            run("init", "-q", "-b", "main")
            run("-c", "user.email=a@b", "-c", "user.name=a", "commit", "-q", "--allow-empty", "-m", "init")
            run("tag", "v1.0")
            with mock.patch.dict(os.environ, env, clear=True):
                repo = guard.GitRepo(root)
                self.assertEqual(repo.current_branch(root), "main")
                self.assertTrue(repo.tag_exists("v1.0", root))
                self.assertFalse(repo.tag_exists("v2.0", root))
                self.assertIs(guard.check_command("git push origin", root, repo, "standard"), guard.MAIN)
                run("switch", "-q", "-c", "r1/feat-x")
                self.assertIsNone(guard.check_command("git push -u origin HEAD", root, repo, "standard"))


if __name__ == "__main__":
    unittest.main()
