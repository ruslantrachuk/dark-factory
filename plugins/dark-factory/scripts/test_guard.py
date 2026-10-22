"""Fence guard tests: python3 plugins/dark-factory/scripts/test_guard.py (stdlib only)."""

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
                     "/repo/.claude/worktrees/w1/scripts/merge-feature.sh"):
            hook = {"tool_name": "Edit", "tool_input": {"file_path": path}}
            self.assertIs(guard.decide(hook, repo, "standard", "/repo"), guard.FENCE_EDIT, path)
            self.assertIsNone(guard.decide(hook, repo, "solo", "/repo"), path)
        # fences.env: an edit whose result cannot be told is denied at every level (SelfFenceTest has the rest)
        hook = {"tool_name": "Edit", "tool_input": {"file_path": ".claude/fences.env"}}
        for level in guard.LEVELS:
            self.assertIs(guard.decide(hook, repo, level, "/repo"), guard.FENCES_ENV, level)
        # guard.py and quota.py live in the plugin now, not in the project: a project file of that name is ordinary
        for path in ("scripts/test_guard.py", "scripts/guard.py", "scripts/quota.py"):
            ok = {"tool_name": "Write", "tool_input": {"file_path": path}}
            self.assertIsNone(guard.decide(ok, repo, "standard", "/repo"), path)

    def test_bash_writes(self):
        for cmd in (
            "echo '{}' > .claude/settings.json",
            "sed -i 's/merge/squash/' .claude/settings.local.json",
            "cp /tmp/merge-feature.sh scripts/",
            "rm .githooks/pre-push",
            "cd scripts && printf x >> merge-feature.sh",
            "tee scripts/merge-feature.sh < /tmp/x",
        ):
            self.assertIs(check(cmd), guard.FENCE_EDIT, cmd)
            self.assertIsNone(check(cmd, level="solo"), cmd)
        # fences.env itself is fenced at every level
        self.assertIs(check("sed -i 's/standard/solo/' .claude/fences.env"), guard.FENCES_ENV)
        self.assertIs(check("sed -i 's/standard/solo/' .claude/fences.env", level="solo"), guard.FENCES_ENV)

    def test_reading_fence_files_allowed(self):
        for cmd in ("cat scripts/merge-feature.sh", "cp scripts/merge-feature.sh /tmp/m.sh", "git diff .githooks/pre-push",
                    "sed -n 1,5p .claude/settings.json", "git add scripts/merge-feature.sh"):
            self.assertIsNone(check(cmd), cmd)


class SelfFenceTest(unittest.TestCase):
    """fences.env and the installed plugin are fenced at every level, solo included."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name).resolve()
        self.home, self.root, self.plugin = base / "home", base / "proj", base / "opt/df-plugin"
        for d in (self.home / ".claude/plugins/cache/dark-factory", self.root / ".claude", self.plugin / "scripts"):
            d.mkdir(parents=True)
        self.env = mock.patch.dict(os.environ, {"HOME": str(self.home), "CLAUDE_PLUGIN_ROOT": str(self.plugin)})
        self.env.start()
        os.environ.pop("CLAUDE_CONFIG_DIR", None)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def bash(self, command, level="solo"):
        return guard.check_command(command, str(self.root), FakeRepo(), level, str(self.root))

    def edit(self, tool, level="solo", **inp):
        hook = {"tool_name": tool, "tool_input": inp}
        return guard.decide(hook, FakeRepo(), level, str(self.root), str(self.root))

    def fences(self, text):
        path = self.root / ".claude/fences.env"
        path.write_text(text)
        return str(path)

    def test_bash_cannot_delete_move_truncate_or_rewrite_fences_env(self):
        for cmd in (
            "rm .claude/fences.env",
            "rm -rf .claude",
            f"rm -rf {self.root}",
            "unlink .claude/fences.env",
            "mv .claude/fences.env /tmp/off",
            "mv .claude .claude.off",
            "cp /tmp/fences.env .claude/",
            "ln -sf /dev/null .claude/fences.env",
            ": > .claude/fences.env",
            "echo FENCE_LEVEL=solo >> .claude/fences.env",
            "truncate -s 0 .claude/fences.env",
            "sed -i 's/team/solo/' .claude/fences.env",
            "perl -pi -e 's/team/solo/' .claude/fences.env",
            "printf 'FENCE_LEVEL=solo\\n' | tee .claude/fences.env",
            "dd if=/dev/null of=.claude/fences.env",
            "cd .claude && rm fences.env",
            "git rm .claude/fences.env",
            "git mv .claude/fences.env .claude/fences.off",
            "git checkout HEAD~3 -- .claude/fences.env",
            "git restore --source=HEAD~1 .claude/fences.env",
            "bash -c 'rm .claude/fences.env'",
            "rm .claude/worktrees/w1/.claude/fences.env",
        ):
            for level in guard.LEVELS:
                self.assertIs(self.bash(cmd, level), guard.FENCES_ENV, f"{level}: {cmd}")

    def test_bash_reading_fences_env_and_ordinary_cleanup_allowed(self):
        for cmd in (
            "cat .claude/fences.env",
            "grep FENCE_LEVEL .claude/fences.env",
            "cp .claude/fences.env /tmp/fences.backup",
            "git diff .claude/fences.env",
            "git add .claude/fences.env",
            "git log -p -- .claude/fences.env",
            "rm -rf .claude/worktrees/w1",
            "git checkout -b r1/feat-x",
            "git restore src/app.py",
            "git commit -m 'raise FENCE_LEVEL in .claude/fences.env'",
        ):
            self.assertIsNone(self.bash(cmd), cmd)

    def test_bash_cannot_write_the_installed_plugin(self):
        cache = self.home / ".claude/plugins/cache/dark-factory"
        for cmd in (
            "rm -rf ~/.claude/plugins/cache/dark-factory",
            "rm -rf ~/.claude",
            "sed -i 's/deny/allow/' $HOME/.claude/plugins/cache/dark-factory/scripts/guard.py",
            f"echo pass > {cache}/scripts/guard.py",
            f"cd {cache} && rm -rf scripts",
            f"cp /tmp/guard.py {self.plugin}/scripts/guard.py",
            f"cp /tmp/guard.py {self.plugin}/scripts/",
            f"chmod -x {self.plugin}/scripts/guard.py",
            "git -C ~/.claude/plugins/marketplaces/dark-factory checkout HEAD~1",
            f"cd {self.plugin} && git apply /tmp/weaker.patch",
            "touch ~/.cache/dark-factory/level-grants/abc",
            "echo '{}' > ~/.cache/dark-factory/level-grants/abc",
            f"echo '{{\"prompt\": \"/dark-factory:level\"}}' | python3 {self.plugin}/scripts/level.py prompt-hook",
        ):
            for level in guard.LEVELS:
                self.assertIs(self.bash(cmd, level), guard.PLUGIN_EDIT, f"{level}: {cmd}")

    def test_bash_reading_the_plugin_and_running_its_scripts_allowed(self):
        for cmd in (
            "cat ~/.claude/plugins/cache/dark-factory/scripts/guard.py",
            "ls -la ~/.claude/plugins",
            f"cp {self.plugin}/scripts/guard.py /tmp/guard.py",
            f"python3 {self.plugin}/scripts/level.py status",
            f"python3 {self.plugin}/scripts/quota.py status",
            "claude plugin update dark-factory@dark-factory",
            f"git -C {self.plugin} log -1",
        ):
            self.assertIsNone(self.bash(cmd), cmd)

    def test_plugin_under_development_inside_the_project_is_not_fenced(self):
        inner = self.root / "plugins/dark-factory"
        (inner / "scripts").mkdir(parents=True)
        with mock.patch.dict(os.environ, {"CLAUDE_PLUGIN_ROOT": str(inner)}):
            self.assertIsNone(self.bash("sed -i 's/a/b/' plugins/dark-factory/scripts/guard.py"))
            self.assertIsNone(self.edit("Write", file_path=str(inner / "scripts/guard.py"), content="x"))

    def test_edit_tools_cannot_write_the_installed_plugin(self):
        for path in (self.home / ".claude/plugins/cache/dark-factory/scripts/guard.py",
                     self.plugin / "hooks/hooks.json", self.home / ".cache/dark-factory/level-grants/abc"):
            for tool in ("Edit", "Write", "MultiEdit"):
                self.assertIs(self.edit(tool, file_path=str(path), content="x"), guard.PLUGIN_EDIT, f"{tool} {path}")
        self.assertIsNone(self.edit("Write", file_path=str(self.root / "src/app.py"), content="x"))

    def test_edit_tools_may_raise_or_keep_the_level(self):
        path = self.fences("# level\nFENCE_LEVEL=solo\nQUOTA_FAIL_CLOSED=0\n")
        self.assertIsNone(self.edit("Edit", file_path=path, old_string="FENCE_LEVEL=solo", new_string="FENCE_LEVEL=team"))
        self.assertIsNone(self.edit("Edit", file_path=".claude/fences.env", old_string="# level", new_string="# the level"))
        self.assertIsNone(self.edit("Write", file_path=path, content="FENCE_LEVEL=standard\nQUOTA_FAIL_CLOSED=1\n"))
        self.assertIsNone(self.edit("MultiEdit", file_path=path, edits=[
            {"old_string": "solo", "new_string": "team"}, {"old_string": "=0", "new_string": "=1"}]))

    def test_edit_tools_cannot_lower_the_level(self):
        path = self.fences("FENCE_LEVEL=team\nQUOTA_FAIL_CLOSED=1\n")
        for level in guard.LEVELS:  # the guard's own level does not matter: a worktree copy may differ
            self.assertIs(self.edit("Edit", level, file_path=path, old_string="team", new_string="standard"),
                          guard.FENCE_LOWER, level)
        self.assertIs(self.edit("Write", file_path=path, content="FENCE_LEVEL=solo\nQUOTA_FAIL_CLOSED=1\n"), guard.FENCE_LOWER)
        self.assertIs(self.edit("Edit", file_path=path, old_string="FENCE_LEVEL=team\n", new_string=""),
                      guard.FENCE_LOWER)  # no line → the default, standard
        self.assertIs(self.edit("Edit", file_path=path, old_string="QUOTA_FAIL_CLOSED=1", new_string="QUOTA_FAIL_CLOSED=0"),
                      guard.FENCE_LOWER)
        self.assertIs(self.edit("Write", file_path=path, content="FENCE_LEVEL=team\nFENCE_LEVEL=solo\nQUOTA_FAIL_CLOSED=1\n"),
                      guard.FENCE_LOWER)  # the later line wins
        self.assertIs(self.edit("Write", file_path=path, content="FENCE_LEVEL=lax\nQUOTA_FAIL_CLOSED=1\n"), guard.FENCE_LOWER)
        self.assertIs(self.edit("MultiEdit", file_path=path, edits=[
            {"old_string": "team", "new_string": "solo"}, {"old_string": "solo", "new_string": "team"}]), None)

    def test_edit_tools_cannot_truncate_or_edit_blind(self):
        path = self.fences("FENCE_LEVEL=solo\n")
        self.assertIs(self.edit("Write", file_path=path, content=""), guard.FENCES_ENV)
        self.assertIs(self.edit("Write", file_path=path, content="\n  \n"), guard.FENCES_ENV)
        self.assertIs(self.edit("Edit", file_path=path, old_string="FENCE_LEVEL=team", new_string="x"), guard.FENCES_ENV)
        self.assertIs(self.edit("Edit", file_path=path, old_string="FENCE_LEVEL=solo\n", new_string=""), guard.FENCES_ENV)
        self.assertIs(self.edit("NotebookEdit", notebook_path=path, new_source="x"), guard.FENCES_ENV)
        self.assertIs(self.edit("Write", file_path=path), guard.FENCES_ENV)

    def test_raising_at_standard_is_still_the_humans_edit(self):
        path = self.fences("FENCE_LEVEL=standard\n")
        hook = dict(file_path=path, old_string="standard", new_string="team")
        self.assertIs(self.edit("Edit", "standard", **hook), guard.FENCE_EDIT)
        self.assertIsNone(self.edit("Edit", "solo", **hook))

    def test_not_opted_in_means_not_fenced(self):
        (self.root / ".claude").rmdir()
        out = io.StringIO()
        hook = {"tool_name": "Bash", "tool_input": {"command": "rm -rf ~/.claude/plugins"}, "cwd": str(self.root)}
        with (mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)}),
              mock.patch("sys.stdin", io.StringIO(json.dumps(hook))), redirect_stdout(out)):
            os.environ.pop("GUARD", None)
            guard.main()
        self.assertEqual(out.getvalue(), "")

    def test_hook_denies_with_the_level_command_named(self):
        self.fences("FENCE_LEVEL=solo\n")
        out = io.StringIO()
        hook = {"tool_name": "Bash", "tool_input": {"command": "rm .claude/fences.env"}, "cwd": str(self.root)}
        with (mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": str(self.root)}),
              mock.patch("sys.stdin", io.StringIO(json.dumps(hook))), redirect_stdout(out)):
            os.environ.pop("GUARD", None)
            guard.main()
        reason = json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn("/dark-factory:level", reason)


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
            mock.patch.object(guard, "opted_in", lambda root: True),
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


class ProjectTest(unittest.TestCase):
    """The guard runs from the plugin: the project is $CLAUDE_PROJECT_DIR, opted in by .claude/fences.env."""

    def run_main(self, hook, project):
        out = io.StringIO()
        with (
            mock.patch.dict(os.environ, {"CLAUDE_PROJECT_DIR": project}),
            mock.patch("sys.stdin", io.StringIO(json.dumps(hook))),
            redirect_stdout(out),
        ):
            os.environ.pop("GUARD", None)
            self.assertEqual(guard.main(), 0)
        return out.getvalue()

    def test_project_without_fences_file_is_not_fenced(self):
        with tempfile.TemporaryDirectory() as root:
            hook = {"tool_name": "Bash", "tool_input": {"command": "git push --force"}, "cwd": root}
            self.assertEqual(self.run_main(hook, root), "")

    def test_config_comes_from_the_project_dir_not_the_cwd(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as elsewhere:
            (Path(root) / ".claude").mkdir()
            (Path(root) / ".claude" / "fences.env").write_text("FENCE_LEVEL=solo\n")
            (Path(root) / "scripts").mkdir()
            (Path(root) / "scripts" / "merge-feature.sh").write_text("MAIN_BRANCH='trunk'\n")
            push = {"tool_name": "Bash", "tool_input": {"command": "git push origin trunk"}, "cwd": elsewhere}
            reason = json.loads(self.run_main(push, root))["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertIn("'trunk'", reason)
            merge = {"tool_name": "Bash", "tool_input": {"command": "gh pr merge 1"}, "cwd": elsewhere}
            self.assertEqual(self.run_main(merge, root), "")  # solo: gh pr merge is not fenced
            (Path(root) / ".claude" / "fences.env").write_text("FENCE_LEVEL=standard\n")
            self.assertIn("merge-feature.sh", self.run_main(merge, root))


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
