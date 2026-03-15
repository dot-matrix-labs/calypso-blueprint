# GitHub as AI Control Plane

<!-- last-edited: 2026-03-14 -->

CONTEXT MAP
this ──extends──────────▶ development/development-state-machine.md (feature work phase)
this ──references───────▶ development/git-standards.md (commit metadata schema)
this ──references───────▶ blueprints/calypso-blueprint.md (branch protection, CI gates)
this ◀──referenced by──── init/scaffold-task.md (Step 10: repo setup)

> **Scope:** This document defines the GitHub-based engineering process as a set of state machines — one for classifying and routing incoming prompts, one for the lifecycle of a single feature from issue to merge. It also specifies the mandatory repository configuration (branch protection, merge queues, CI gates) and an API bootstrap script to apply that configuration to a new repository.

---

## Philosophy

Every unit of work in this system is a **feature**. A feature is defined precisely:

```
feature = 1 GitHub Issue = 1 Pull Request = 1 branch = 1 worktree
```

This 1:1:1:1 constraint is non-negotiable. A PR that contains two features cannot be reviewed, rolled back, or reasoned about cleanly. The discipline of keeping this invariant enforces small, reviewable PRs and a legible git history.

GitHub plays two distinct roles in this system:

| GitHub's role | Term |
|---------------|------|
| Issues are the canonical record of work | **system of record** |
| Branch protection + CI enforce merge policy | **merge gate** |
| The whole system, as a platform concept | **AI control plane** |

The **GitHub Issue is the source of truth** for a feature. Not a wiki page, not a project board, not a doc. The issue accumulates motivation, technical context, feature checklist, test plan, and dependency graph. The PR inherits that checklist directly — it adds no new detail.

---

## Deterministic Gate Architecture

A project's workflow has two tiers of deterministic gates, both rooted in the git/GitHub control plane:

| Tier | Mechanism | Scope | When enforced |
|------|-----------|-------|---------------|
| **Local dev gates** | Git hooks (`scripts/hooks/`) | Individual developer commits | Pre-commit, commit-msg, pre-push |
| **Project gates** | GitHub Actions workflows (`.github/workflows/`) | Branch-level CI | On push, on PR, merge queue |

Both tiers are **deterministic** — they produce a binary pass/fail result with no human judgement involved. Agent tasks are similarly deterministic: every task completes with exactly one of three outcomes: **OK**, **NOK**, or **ABORTED**.

### Fused gate model

The calypso-cli program maintains a **fused view** of all state machines and gates in memory at runtime. The project workflow definition (`.calypso/state-machine.yml`) declares gate groups and their expected tasks. The actual enforcement, however, lives in the git hook scripts and GitHub Actions workflow files — these are the ground truth that runs at commit time and CI time respectively.

The relationship between these layers:

```
state-machine.yml          declares gates and their expected outcomes
    │
    ├── scripts/hooks/*    local gate implementations (ground truth for dev gates)
    │
    └── .github/workflows/* project gate implementations (ground truth for CI gates)
```

The workflow definition is the program's model of what gates exist. The hook scripts and workflow files are the actual implementations that enforce those gates. **When the implementations diverge from the workflow definition, calypso-cli must warn** — the doctor check `required-git-hooks-installed` covers the local tier, and `required-workflows-present` covers the project tier. This ensures the program's fused view stays consistent with the enforcement reality.

### Why this matters

Without this fused view, the program could believe a gate is passing (because the workflow definition says a task succeeded) while the actual enforcement mechanism (a hook or workflow) has drifted or is missing entirely. The doctor checks close this gap by treating hook and workflow file presence and correctness as first-class environment health signals, on par with tool installation and authentication.

---

## State Machine 1: Prompt Classification

When an agent receives a prompt, it must classify it before taking any action. The wrong classification produces wrong output: a planning prompt handled as an implementation request creates code no one asked for; an implementation request treated as planning creates docs instead of a fix.

### Entry Condition

Agent receives a natural-language prompt from the operator.

### Exit Condition

Prompt is routed to the appropriate sub-machine and the relevant artifact is updated.

### States and Transitions

```
RECEIVED → CLASSIFIED → [PLANNING | R&D | FEATURE_WORK]
```

---

### State: RECEIVED

**Meaning:** A new prompt has arrived; no action has been taken yet.

**Entry:** Operator sends a message.

**Available Actions:**
- Analyze prompt intent → CLASSIFIED

**Invariants:**
- No file edits, no API calls, no git operations until classification is complete.

---

### State: CLASSIFIED

**Meaning:** The agent has determined what kind of work the prompt requests.

**Classification rules:**

| Signal in prompt | Classification |
|-----------------|----------------|
| "plan", "roadmap", "phases", "create issue", "update issue", "prioritize", "add to", "track", "milestone" | **PLANNING** |
| "design", "research", "evaluate", "how should we", "architecture for", "tradeoffs", "spike", "proposal" | **R&D** |
| "implement", "fix", "add feature", "build", "update `<file>`", references an existing issue # | **FEATURE_WORK** |

When the signal is ambiguous, the agent asks one clarifying question before proceeding.

**Available Actions:**
- Prompt is PLANNING → PLANNING
- Prompt is R&D → R&D
- Prompt is FEATURE_WORK → FEATURE_WORK

---

### State: PLANNING

**Meaning:** The prompt asks for work-tracking changes: creating or updating the plan issue, creating sub-issues, reordering phases, or updating dependency links.

**What the agent does:**
1. Identify the **plan tracking issue** (the "mother issue") — pinned, one per project.
2. Determine whether the request adds a new phase, a new sub-issue bullet, or reorders existing items.
3. Create or update GitHub Issues accordingly using `gh issue create` / `gh issue edit`.
4. Update the plan tracking issue body so the new issue appears as a bullet under its phase.
5. Assess merge queue order implications (see Merge Queue section below) and note any sequencing constraints in the issue body.

**Invariant:** Only the PLANNING agent writes to the plan tracking issue. Subagents executing feature work never touch it. This prevents concurrent write collisions on the mother issue body.

**Output artifact:** Updated GitHub Issue(s). No code touched.

---

### State: R&D

**Meaning:** The prompt asks the agent to research, evaluate, or design — producing a document or recommendation, not production code.

**What the agent does:**
1. Conduct research (read codebase, read blueprints, search docs).
2. Draft the output in `calypso-blueprint/development/` or `calypso-blueprint/blueprints/` as appropriate.
3. Open a PR for the doc if it should become canonical. Otherwise return findings inline.

**Output artifact:** A document or inline analysis. May or may not produce a PR.

---

### State: FEATURE_WORK

**Meaning:** The prompt requests a concrete implementation — code, config, or infrastructure change — tied to a GitHub Issue.

**Transition:** Enters the **Feature Lifecycle State Machine** (State Machine 2).

---

## State Machine 2: Feature Lifecycle

### Entry Condition

- A GitHub Issue exists (or is created) with the mandatory template filled in.
- The agent running the development state machine has verified the issue is feature-complete: all five template sections present, dependency issues merged or explicitly waived.

### Exit Conditions

- **ISSUE_CLOSED** — PR merged to `main` via merge queue; issue auto-closed.
- **ABANDONED** — work is cancelled at any point before merge; worktree and branch cleaned up, issue closed with reason recorded.

### Issue Template (mandatory)

Every issue must contain the following sections before implementation begins:

```markdown
## Motivation
Why does this feature exist? What user need or system requirement does it address?

## Technical Considerations
Constraints, architectural context, known risks, approach options considered.

## Features
- [ ] Specific, testable capability A
- [ ] Specific, testable capability B

## Test Plan
- [ ] Unit test for X
- [ ] Integration test for Y
- [ ] Manual verification step Z

## Dependencies
Blocked by: #<issue>
Blocks: #<issue>
```

An issue missing any of these sections is **not ready to implement**. The agent must refuse to open a branch until the template is complete.

---

### States and Transitions

```
ISSUE_READY ──────────────────────────────────────────────┐
  └─→ BRANCH_OPEN (worktree created) ────────────────────┤
        └─→ IN_PROGRESS (commits landing) ───────────────┤
              └─→ PR_OPEN (push + gh pr create) ─────────┤
                    └─→ CI_RUNNING (all checks executing) ┤
                          ├─→ CI_FAILED ─→ IN_PROGRESS    ┤
                          └─→ CI_PASSED                   ┤  → ABANDONED
                                └─→ MERGE_QUEUE ──────────┤
                                      ├─→ QUEUE_FAILED ─→ IN_PROGRESS
                                      └─→ MERGED
                                            └─→ ISSUE_CLOSED
```

ABANDONED is reachable from any state before MERGED.

---

### State: ISSUE_READY

**Meaning:** The issue template is complete and the feature has been approved for implementation.

**Entry:** The development state machine agent verifies the issue is feature-complete and spawns a subagent in a dedicated worktree. Each open issue maps to exactly one subagent; multiple subagents run concurrently across their respective worktrees.

**Invariants:**
- Issue has all five template sections.
- Dependency issues (`Blocked by`) are either merged or explicitly waived.

**Available Actions:**
- Create worktree and branch → BRANCH_OPEN

**Branch and worktree naming:** To avoid collisions between similarly titled issues and across concurrent subagents, the identifier is a short hash derived from the issue title and the commit SHA being branched from:

```bash
BASE=$(git rev-parse --short HEAD)
SLUG=$(echo "<issue-title>" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9' '-' | sed 's/-*$//')
HASH=$(echo "${SLUG}-${BASE}" | sha1sum | cut -c1-6)
BRANCH="feat/${SLUG}-${HASH}"
WORKTREE="../<repo>-${SLUG}-${HASH}"
git worktree add "$WORKTREE" -b "$BRANCH"
```

Example: issue "Add rate limiting", branched from `a3f9c1` → `feat/add-rate-limiting-e7d2a1`, worktree `../<repo>-add-rate-limiting-e7d2a1`.

The hash component guarantees uniqueness even when two issues share a title prefix or when the same issue is retried from a different base commit.

---

### State: BRANCH_OPEN

**Meaning:** A dedicated worktree exists for this feature. No commits have landed yet.

**Entry:** `git worktree add` completes successfully.

**Invariants:**
- Only work related to this issue's feature checklist is committed on this branch.
- No commits for a different issue appear here. If unrelated work is discovered, it becomes a new issue.

**Available Actions:**
- Begin implementation → IN_PROGRESS

---

### State: IN_PROGRESS

**Meaning:** The agent is actively committing work on the branch.

**Entry:** First commit on the branch.

**Commit discipline:**
- Every commit passes the pre-commit and commit-msg hooks (see `git-standards.md`).
- Every commit includes `GIT_BRAIN_METADATA` with a `retroactive_prompt` specific enough for another agent to reproduce the change.
- Commits are small and logically atomic. The pre-commit hook warns if > 10 files are staged.

**Available Actions:**
- Open PR at any point — CI runs immediately on push; there is no minimum completeness threshold for opening a PR → PR_OPEN
- Requirements cancelled or approach invalidated → ABANDONED

---

### State: PR_OPEN

**Meaning:** The branch has been pushed and a pull request has been created.

**Entry:** `git push && gh pr create`

PRs are never opened as drafts. CI runs immediately on every open PR — this is intentional. Testing early, granularly, and often means the first push triggers the full check suite. There is no "ready for review" gate between pushing and CI.

**PR body format (mandatory):**

```markdown
## Summary
Closes #<issue-number>

## Test plan
- [ ] <copied verbatim from issue test plan>
- [ ] <each checkbox must be checked before merge>
```

**Rules:**
- The PR body does not repeat or add to the issue. All detail lives in the issue.
- The PR body inherits the issue's test plan checkboxes verbatim.
- The `pr-checklist.yml` CI job blocks merge if any `- [ ]` item remains unchecked.
- No "Generated with Claude Code" or co-author attribution lines.

**Available Actions:**
- PR opened, subagent stops → CI_RUNNING

The subagent's job ends here. It does not wait for CI. The orchestrator (development state machine) takes ownership and polls or listens for CI status events.

---

### State: CI_RUNNING

**Meaning:** GitHub Actions workflows are executing against the PR. No subagent is active; the orchestrator is waiting for CI to complete.

**Required checks (all must pass):**

| Check | What it verifies |
|-------|-----------------|
| `build` | Project compiles without errors |
| `clippy` | No Clippy lints (deny warnings) |
| `format` | `cargo fmt --check` passes |
| `unit` | All unit tests pass |
| `integration` | Integration tests pass against real Postgres |
| `e2e` | End-to-end tests pass |
| `coverage` | Line coverage ≥ `<COVERAGE_THRESHOLD>`% (configured per repo) |
| `checklist` | All `- [ ]` items in PR body are checked |

These checks are deterministic. A failing check means the code is wrong; fix the root cause before re-pushing.

**Available Actions (orchestrator decides):**
- Any check fails → orchestrator spawns a fix agent → CI_FAILED
- All checks pass → orchestrator enqueues the PR → CI_PASSED

---

### State: CI_FAILED

**Meaning:** One or more required checks have failed. The orchestrator spawns a new subagent in the existing worktree, passing it the CI failure log as context.

**What the spawned agent does:**
1. Read the failing check's log output.
2. Determine root cause — do not re-push without understanding the failure.
3. Fix the issue on the branch.
4. Push — CI re-runs and the agent stops. The orchestrator re-enters CI_RUNNING.

**Invariants:**
- Never push `--no-verify` to bypass hooks.
- Never skip or comment out a failing test to make CI pass.
- If the test itself is wrong (testing incorrect behavior), rewrite the test with a clear commit message explaining the correction.

**Available Actions:**
- Fix pushed, agent stops → CI_RUNNING

---

### State: CI_PASSED

**Meaning:** All required checks have passed. The orchestrator enqueues the PR — no subagent required for this transition.

**Orchestrator action:**
```bash
gh pr merge <PR-number> --merge --auto
```

The `--auto` flag enqueues the PR rather than merging immediately. GitHub merges it when the queue processes it and all checks pass in the queue context.

**Available Actions:**
- PR enqueued → MERGE_QUEUE

---

### State: MERGE_QUEUE

**Meaning:** The PR is in the merge queue. The orchestrator is waiting for the queue outcome — no subagent is active.

**Why merge queues:**
The merge queue prevents a class of bug where two PRs both pass CI independently but fail when combined. Each PR in the queue is re-tested against the accumulated state of all PRs ahead of it. This makes `main` a stable branch by construction — no individual PR can regress it.

**Orchestrator ordering discipline:**
When multiple PRs are open simultaneously, the orchestrator enqueues them in dependency order:
1. Check the `Dependencies` section of each issue.
2. Enqueue blocked-by issues first.
3. Dependent issues must not be enqueued until their blockers are merged or explicitly waived.

This sequencing should also be reflected in the plan tracking issue (phases and bullet order).

**Available Actions (orchestrator decides):**
- Queue check fails (conflict or regression) → orchestrator spawns a rebase agent → QUEUE_FAILED
- Queue processes successfully → MERGED

---

### State: QUEUE_FAILED

**Meaning:** The merge queue rejected the PR. The orchestrator spawns a new subagent in the existing worktree, passing it the conflict or regression details as context.

**What the spawned agent does:**
1. Pull the latest `main` (or queue base).
2. Rebase the branch: `git rebase origin/main`.
3. Resolve conflicts — do not blindly accept either side.
4. Push the rebased branch and stop. The orchestrator re-enters CI_RUNNING.

**Available Actions:**
- Rebase pushed, agent stops → CI_RUNNING

---

### State: MERGED

**Meaning:** The PR has landed on `main`. The branch and worktree are now stale.

**Cleanup:**
```bash
git worktree remove ../<repo>-<issue-slug>
git branch -d feat/<issue-slug>
```

**Available Actions:**
- Issue auto-closed (by `Closes #<n>` in PR body) → ISSUE_CLOSED

---

### State: ISSUE_CLOSED

**Meaning:** The feature is complete. The issue is closed; the plan tracking issue's bullet for this issue shows a closed-issue icon (no manual checkbox update needed — GitHub renders the icon by issue state).

**Terminal state.** No further transitions.

---

### State: ABANDONED

**Meaning:** The feature has been cancelled — requirements changed, the approach was invalidated, or a dependency was dropped. Reachable from any state before MERGED.

**What the agent does:**
1. If a PR is open: close it with a comment explaining why the work is being abandoned.
2. Remove the worktree: `git worktree remove "$WORKTREE"`.
3. Delete the branch: `git push origin --delete "$BRANCH" && git branch -d "$BRANCH"`.
4. Close the issue with a comment recording the reason and any work that should be preserved or re-examined in a future issue.
5. Notify the PLANNING agent so it can update the phase in the plan tracking issue (remove the bullet or replace it with a successor issue).

**Invariant:** The subagent records the reason before any cleanup. An abandoned issue with no explanation is indistinguishable from an accidental closure.

**Terminal state.** No further transitions.

---

## The Plan Tracking Issue

Every project has exactly one **plan tracking issue** — the "mother issue." It is pinned and never closed until the project ships.

### Structure

```markdown
## Phase 1: Foundation
- #12 Scaffold repository and CI gates
- #13 Database schema and migrations
- #14 Auth token issuance

## Phase 2: Core Features
- #20 User onboarding flow
- #21 Ledger entry creation

## Phase 3: Hardening
- #30 Coverage to 99%
- #31 Rate limiting
```

### Rules

- Bullets are issues, not checkboxes. The icon next to each linked issue changes color automatically when the issue is closed — there is no status divergence.
- **Phases are strict gates, not loose groupings.** All issues in a phase must be merged before any issue in the next phase may enter ISSUE_READY. This is intentional: it enforces a QA and stabilization boundary between phases, prevents half-finished foundations from being built on, and gives the codebase time to settle before the next wave of changes compounds on top of it.
- Phase boundaries are planned by the human and PLANNING agent together. The cost of strict sequencing is lower throughput; the benefit is a stable, fully-verified base at every phase transition. This trade-off is accepted by design.
- When a new issue is created (PLANNING state), the agent adds it to the appropriate phase in the plan tracking issue body. Phase assignment is a planning decision — it encodes both dependency order and the stabilization intent.
- The plan tracking issue is the **only** planning artifact. No project boards, no wikis, no separate roadmap docs.

---

## Human Touchpoints

Agents run the full development loop autonomously. Humans do not review PRs as part of normal feature work — automated CI gates are the quality bar for merging to `main`.

The two points where humans intervene are:

| Touchpoint | Who | What |
|------------|-----|-------|
| **Instruct new work** | Operator | Sends a prompt to the agent: create a feature, revert a feature, plan a phase, or conduct R&D. |
| **Tag a release** | Operator | Decides when `main` is ready to ship. Creates the release tag manually or instructs the agent to do so. No agent tags a release autonomously. |

### Instructing Agents

Operators interact with the system by sending natural-language prompts. The prompt classification machine (State Machine 1) routes the prompt to the correct sub-machine.

Common operator prompts and their classifications:

| Prompt example | Classification |
|----------------|----------------|
| "Implement rate limiting on the `/api/v1/ingest` endpoint (issue #31)" | FEATURE_WORK |
| "Revert the rate limiting feature — it's causing false positives" | FEATURE_WORK |
| "Add a phase 4 to the plan: observability" | PLANNING |
| "Research the tradeoffs between JWT and opaque tokens for our auth layer" | R&D |

### Rolling Back a Feature

A rollback is treated as a new feature, not a special operation. The operator prompts the agent: "Revert feature X." The agent:

1. Creates a new GitHub Issue with the mandatory template — motivation is the regression or decision to remove, technical considerations include which commits to revert.
2. Enters the normal Feature Lifecycle: branch, worktree, commits (`git revert <sha>` or equivalent), PR, CI, merge queue.
3. The original issue is referenced in the new revert issue for traceability.

There is no fast-path or bypass for rollbacks. Running the revert through CI is what confirms the system is stable after removal.

---

## Repository Configuration

The following configuration must be applied to every repository before the first PR is opened. Apply it once, during `calypso init` (see `init/scaffold-task.md`).

### Branch Protection Ruleset

- Target: `~DEFAULT_BRANCH` (`main`)
- No bypass actors — not even repo admins
- Required status checks (all eight listed in CI_RUNNING state above)
- Require pull request before merging
- Require merge queue

### Bootstrap API Script

Run this script once after creating the repository. It requires a GitHub PAT with `repo` and `administration:write` scopes.

```bash
#!/usr/bin/env bash
# setup-repo-protection.sh
# Applies branch protection ruleset and merge queue to a new GitHub repository.
# Usage: GITHUB_TOKEN=<pat> REPO=<owner/repo> bash setup-repo-protection.sh

set -euo pipefail

OWNER="${REPO%%/*}"
REPO_NAME="${REPO##*/}"
API="https://api.github.com"

echo "Configuring repository: $REPO"

# 1. Enable merge queue on the repository
gh api --method PATCH \
  "repos/$REPO" \
  --field allow_merge_commit=false \
  --field allow_squash_merge=false \
  --field allow_rebase_merge=false \
  --field allow_auto_merge=true

echo "✓ Merge strategy: merge queue only (squash and rebase disabled)"

# 2. Create a branch protection ruleset via the Rulesets API
# Note: Classic branch protection cannot enforce merge queues — rulesets are required.
gh api --method POST \
  "repos/$REPO/rulesets" \
  --header "Accept: application/vnd.github+json" \
  --input - <<'JSON'
{
  "name": "main-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "bypass_actors": [],
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    { "type": "pull_request" },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          { "context": "build" },
          { "context": "clippy" },
          { "context": "format" },
          { "context": "unit" },
          { "context": "integration" },
          { "context": "e2e" },
          { "context": "coverage" },
          { "context": "checklist" }
        ]
      }
    },
    {
      "type": "merge_queue",
      "parameters": {
        "check_response_timeout_minutes": 60,
        "grouping_strategy": "ALLGREEN",
        "max_entries_to_build": 5,
        "max_entries_to_merge": 1,
        "merge_method": "MERGE",
        "min_entries_to_merge": 1,
        "min_entries_to_merge_wait_minutes": 0
      }
    }
  ]
}
JSON

echo "✓ Branch protection ruleset applied to main"

# 3. Pre-register CI check names by triggering workflows via workflow_dispatch.
# GitHub only recognizes a required check name after the workflow has run once.
# Each workflow must have an on: workflow_dispatch trigger for this to work.
for WORKFLOW in rust-quality.yml rust-unit.yml rust-integration.yml rust-e2e.yml rust-coverage.yml pr-checklist.yml; do
  gh workflow run "$WORKFLOW" --repo "$REPO" --ref main 2>/dev/null && \
    echo "✓ Triggered $WORKFLOW" || \
    echo "  ⚠ Could not trigger $WORKFLOW (may not exist yet or no workflow_dispatch trigger)"
done

echo ""
echo "Repository protection configured. Verify at:"
echo "  https://github.com/$REPO/settings/rules"
```

**Important:** GitHub only registers a required status check name after the workflow has run at least once. The final loop above triggers each workflow via `workflow_dispatch` to pre-register the check names before the ruleset is enabled. If a workflow doesn't have `workflow_dispatch` in its triggers, add it temporarily for this step.

---

## Full Flow Diagram

```
Operator prompt
      │
      ▼
┌─────────────────────────────────────────────────────────────┐
│                   PROMPT CLASSIFICATION                      │
│                                                             │
│  PLANNING ──→ update plan tracking issue / create issues   │
│  R&D      ──→ research → document → optional PR            │
│  FEATURE  ──→ Feature Lifecycle (below)                    │
└─────────────────────────────────────────────────────────────┘

Feature Lifecycle:

ISSUE_READY
  │  git worktree add
  ▼
BRANCH_OPEN
  │  first commit
  ▼
IN_PROGRESS ◀─────────────────────────────────────────┐
  │  feature complete, tests pass                     │
  ▼                                                   │
PR_OPEN                                               │
  │  gh pr create                                     │
  ▼                                                   │
CI_RUNNING                                            │
  ├── fail ──→ CI_FAILED ─── fix & push ─────────────┘
  │
  └── pass ──→ CI_PASSED
                  │  gh pr merge --auto
                  ▼
              MERGE_QUEUE
                  ├── fail ──→ QUEUE_FAILED ─── rebase & re-push ─→ CI_RUNNING
                  │
                  └── pass ──→ MERGED
                                  │  auto-close
                                  ▼
                              ISSUE_CLOSED
```

---

## Edge Cases

| Scenario | Current State | Trigger | Resolution |
|----------|---------------|---------|------------|
| Operator requests a rollback | N/A | Operator prompt "revert feature X" | Create a new issue + branch + revert commits; run the full lifecycle. No bypass. |
| Two features accidentally on one branch | IN_PROGRESS | Discovered at PR review | Split branch: cherry-pick one feature to a new branch, reset the original |
| Dependency merged out of order | MERGE_QUEUE | Queue failure due to missing dep | Remove from queue, wait for blocker to merge, re-enqueue |
| Issue template incomplete | ISSUE_READY | Agent begins work without full template | Stop. Complete the template first. No exceptions |
| PR body has undecided `- [ ]` items | PR_OPEN | Checklist CI job fails | Check the boxes or remove the item with a comment in the PR thread |
| Main has diverged significantly | QUEUE_FAILED | Many conflicts on rebase | Rebase interactively, resolve each conflict deliberately |

---

## Antipatterns

- **Multi-feature PRs.** Two issues in one PR means two rollbacks to revert one bug. Keep the 1:1:1:1 invariant.
- **PRs with details not in the issue.** The issue is the source of truth. If detail belongs in the PR, move it to the issue first.
- **Checkboxes in the plan tracking issue.** Linked issue icons show status automatically. Checkboxes diverge. Use bullets.
- **Bypassing CI.** `--no-verify`, skipping tests, or adding `.skip()` to pass CI are all equivalent to shipping broken code. Fix the root cause.
- **Enqueuing out of dependency order.** A dependent PR that merges before its blocker will fail or produce incorrect behavior. Respect the dependency graph.
- **Using project boards or wikis as source of truth.** The issue tracker is the only planning artifact. Other tools create state that diverges and is never reconciled.
