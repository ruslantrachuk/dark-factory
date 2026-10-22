<!-- dark-factory:solo-kit -->
## Operating contract (dark-factory solo kit)

Fences are enforced by the dark-factory plugin's hooks, not only by this text. Level: `.claude/fences.env`.

1. **Code goes through a feature branch** (`feat/<slug>`, `fix/<slug>`) cut from a fresh main branch. Never commit code to the main branch; the guard denies pushing to it.
2. **Merge only through `scripts/merge-feature.sh <branch> [PR title] --accepted-by "<name>"`**, after a person said "accepted"; the name is theirs. Nobody said it, nothing is merged. It pushes, opens the PR, waits for CI, records the acceptance and merges. CI cannot run: add `--skip-ci "<reason>"` only on the owner's word.
3. **No force push, no `--no-verify`, no rewriting the main branch.** If a git hook fails, fix what it reports; if the hook is wrong, tell the human.
4. **Session log:** read the latest entry of `devlog.md` before work (create the file if it is missing); before the session ends, add an entry on top: what was done, what is open, where to continue.
5. **A finding along the way is a proposal, not an authorization.** Scope comes from the request.
6. **Quota:** near the subscription limit the quota guard stops new work; save the state, and if you work autonomously, schedule a continuation for the time it names.

Bypass is for a human only: restart the session with `GUARD=off claude` (quota: `QUOTA_GUARD=off`).
<!-- /dark-factory:solo-kit -->
