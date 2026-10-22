<!-- dark-factory:solo-kit -->
## Operating contract (dark-factory solo kit)

Fences are enforced by the dark-factory plugin's hooks, not only by this text. Level: `.claude/fences.env`.

1. **Code goes through a feature branch** (`feat/<slug>`, `fix/<slug>`) cut from a fresh main branch. Never commit code to the main branch; the guard denies pushing to it.
2. **Merge only through `scripts/merge-feature.sh <branch> [PR title] --accepted-by "<name>"`**, after a person said "accepted", under their name. If nobody has said it, nothing gets merged. The script pushes, finds or opens the PR, checks its description, waits for CI (with no CI in the repository it runs the local gate instead), records the acceptance and merges with the description as the merge commit message. If CI exists but cannot run, add `--skip-ci "<reason>"`, and only on the owner's word.
3. **No force push, no `--no-verify`, no rewriting the main branch.** If a git hook fails, fix what it reports; if the hook is wrong, tell the human.
4. **The record of work is the PR.** Open a draft PR when work on a branch starts (`gh pr create --draft`); keep its description current with three sections — `## Done`, `## Decisions`, `## Open questions` — before `/clear` and before the session ends (`merge-feature.sh` refuses without them). Read the branch's PR before work. Anything that is not in git or the PR goes to memory.
5. **A finding along the way is a proposal, not an authorization.** Scope comes from the request.
6. **Quota:** near the subscription limit the quota guard stops new work; save the state, and if you work autonomously, schedule a continuation for the time it names.

Bypass is for a human only: restart the session with `GUARD=off claude` (quota: `QUOTA_GUARD=off`).
<!-- /dark-factory:solo-kit -->
