# Research: what a ruleset can enforce on a free public repo

Part of a learning experiment (tech-debt-miner, ticket #2). Sources are GitHub Docs pages fetched on 2026-11-18. Where a page did not state something, this note says so rather than guessing.

## Sources

- [Available rules for rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets)
- [About rulesets](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
- [Creating rulesets for a repository](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)
- [Managing rulesets for a repository](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/managing-rulesets-for-a-repository)
- [About protected branches](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Configuring commit squashing for pull requests](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/configuring-commit-squashing-for-pull-requests)
- Live check: `gh api repos/robkeim/tech-debt-miner/rulesets` returned `[]` (HTTP success) on this public, user-owned repo, so the rulesets endpoint is reachable here.

## Availability (needs a manual check)

- "About rulesets" says rulesets are for "customers on GitHub Team and GitHub Enterprise plans". The fetched pages did not mention GitHub Free or public repositories, so **free-plan availability on a public repo is not confirmed by the pages read**. The GitHub plans page says Free gets "unlimited public repositories with a full feature set" but does not list rulesets.
- Before relying on this, create a test ruleset in Settings > Rules > Rulesets on the repo and confirm it saves and enforces.
- Limits: 75 rulesets per repository.

## What each rule enforces

| Need | Ruleset rule or setting | Behavior |
| --- | --- | --- |
| Required status checks | "Require status checks to pass" | Named checks must pass before merge. Optional strict mode requires the branch to be up to date with base. Can pin the expected source to a GitHub App. |
| Linear history | "Require linear history" | Blocks merge commits, so PRs must squash or rebase. Squash or rebase merging must be enabled in the repo first. |
| Squash-only merges | Ruleset: "Require a specific merge method" inside "Require a pull request before merging". Repo setting: Settings > General > Pull Requests, enable only "Allow squash merging". | Ruleset blocks the merge if the repo has that method disabled. Both can be used together. |
| Blocked force pushes | "Block force pushes" | On by default. Allowing them does not override other rules (for example linear history). |
| Block branch deletion | "Restrict deletions" | On by default. |
| Required PRs | "Require a pull request before merging" | Approvals are not required by default (count is configurable). Extra options: dismiss stale approvals, code owner review, approval from someone other than the last pusher, conversation resolution. |
| Signed commits | "Require signed commits" | Only signed and verified commits can be pushed. |

Other rules exist (restrict creations or updates, code scanning results, secret scanning alerts, file path, extension and size limits), listed on the "Available rules" page.

## Gotchas

- **Skipped checks pass.** Required checks may be "successful, skipped, or neutral". A skipped required job (for example via a path filter) satisfies the rule.
- **Unique check names.** Duplicate job names across workflows can cause ambiguous results and block merges.
- **Strict mode needs a check.** If "require branches to be up to date" is on, at least one status check must be defined or the rule has no effect. Each check name must be added with the plus icon in the UI.
- **Signed commits vs squash.** Unsigned commits on the PR head branch can block a squash merge even though GitHub signs the final squash commit. Fix by rewriting and force pushing. Signing every local commit avoids this.
- **Solo maintainer approvals.** The pages do not address a sole author directly. The "approval from someone other than the last pusher" option implies the author cannot satisfy it alone, so for a solo repo require a PR with zero required approvals and rely on required checks. Approvals count only from users with write access.
- **Bypass actors.** Ruleset bypass actors can be roles (such as repository admin), teams, or GitHub Apps. A bypass can be set to "For pull requests only", which forces the actor to open a PR but lets them merge past the rules. The pages did not say which actor types are offered on a personal (non-organization) repo; verify in the UI.
- **Classic branch protection differs.** Admins are not restricted by default unless "Do not allow bypassing the above settings" is on, and the page states bypass lists apply only to organization-owned repositories. Rulesets are the successor with explicit bypass lists.
- **Block force pushes lockout.** With it enabled, owners and admins cannot change the default branch without bypass permission.
- **Layering.** Rulesets and branch protection rules coexist, and all applicable rules are enforced. There is no ruleset priority; the most restrictive version of a duplicated rule applies.
- **Evaluate mode.** The "Managing rulesets" page describes an Evaluate status that records what would have passed or failed. The "About rulesets" page lists only Active and Disabled, and the Rule Insights dashboard is Team and Enterprise only. Treat Evaluate as possibly unavailable on Free.
- **Squash message default.** The default squash message depends on commit count (single commit uses its message, multiple use PR title plus list). Choose "Pull request title" as the default so the Conventional Commit PR title becomes the commit subject.

## Implications for this repo (for the follow-up ticket)

- Candidate ruleset on the default branch: require PR (0 approvals), require the CI check, require linear history, require squash merge method, block force pushes and deletions.
- Repo setting: allow squash merging only, default message "Pull request title".
- Signed commits: optional; adds friction with squash merges when branch commits are unsigned.
- Open questions to verify in the UI: Free-plan availability, bypass actor options on a user-owned repo, and Evaluate mode.
