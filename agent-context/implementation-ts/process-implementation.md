# Process — Calypso TypeScript Implementation

<!-- last-edited: 2026-03-13 -->

CONTEXT MAP
this ──implements──▶ blueprints/process-blueprint.md
this ◀──referenced by── index.md

> Implements: Process Blueprint (`agent-context/blueprints/process-blueprint.md`)

The principles, threat model, and patterns in that document apply equally to other stacks. This document covers the concrete realization in the Calypso monorepo and assumes the stricter autonomous-enterprise operating model rather than a lightweight documentation workflow.

Calypso CLI itself is the orchestrator, not the coding agent. The CLI owns workflow state, task dispatch, gate evaluation, and operator interaction. Repository-authored workflow templates are YAML; machine-written runtime state is expected to be JSON.

---

## Planning Documents

| File                                | Scope                                     | Owner                      |
| ----------------------------------- | ----------------------------------------- | -------------------------- |
| `docs/prd.md`                       | What the product must do                  | Human (Product Owner)      |
| `docs/plans/implementation-plan.md` | All tasks, ordered, with completion state | Agent, updated each commit |
| `docs/plans/next-prompt.md`         | The single next action                    | Agent, updated each commit |

## Workflow State Machine

Calypso's process state is declared in a YAML workflow file managed by the CLI. The first default workflow lives at `agent-context/workflows/calypso-default-feature-workflow.yaml` and is the `calypso-default-feature-workflow` state machine with:

- initial state `new`
- feature lifecycle states including `prd-review`, `architecture-plan`, `scaffold-tdd`, `implementation`, `qa-validation`, `ready-for-review`, and `done`
- recovery states `waiting-for-human`, `blocked`, and `aborted`
- a feature-unit invariant: feature equals branch equals worktree equals pull request

The workflow file is a tracked repository artifact, not an ephemeral CLI cache.

The product-level CLI specification also requires:

- one orchestrator per repository context
- feature equals pull request equals branch equals worktree as the default unit model
- early pull request creation
- structured `OK | NOK | ABORTED` agent outcomes
- `gh` as the required GitHub control surface
- CLI and TUI as the primary operator surfaces

## Gate Model

The default workflow groups gates into four concerns:

- `specification`
- `implementation`
- `validation`
- `merge-readiness`

Each gate records a task, owner role, status source, blocking behavior, and checklist label. In the initial workflow this includes built-in checks like doctor, feature-unit binding, workflow presence, Rust quality, test matrix health, and merge compatibility, plus agent and human tasks such as PR canonicalization, blueprint review, and clarification handling.

## Task Catalog

The initial workflow uses this task inventory:

| Task                     | Kind    | Backing implementation / role              |
| ------------------------ | ------- | ------------------------------------------ |
| `doctor-clean`           | builtin | `builtin.doctor.all_checks_passing`        |
| `feature-unit-bound`     | builtin | `builtin.feature.branch_worktree_pr_bound` |
| `workflow-files-present` | builtin | `builtin.github.workflow_files_present`    |
| `pr-editor`              | agent   | `pr-editor`                                |
| `documentation-merge`    | agent   | `documentation-merge`                      |
| `blueprint-review`       | agent   | `blueprint`                                |
| `human-clarification`    | human   | human operator                             |
| `rust-quality`           | builtin | `builtin.ci.rust_quality_green`            |
| `test-matrix`            | builtin | `builtin.ci.test_matrix_green`             |
| `main-compatibility`     | builtin | `builtin.git.is_main_compatible`           |
| `human-review-approval`  | human   | human reviewer                             |

The remaining implementation question is not which tasks exist, but how the CLI discovers them, invokes them, and writes their status back into the workflow state.

## Agent Prompt Catalog

Agent-backed tasks also need stable prompt contracts. The initial workflow defines these prompt seeds:

| Role / task           | Prompt intent                                                                                                         |
| --------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `pr-editor`           | Keep the pull request description aligned with the current feature state and gate checklist.                          |
| `documentation-merge` | Reconcile product and implementation documents semantically so the current scope, plan, and constraints stay aligned. |
| `blueprint-review`    | Review current transcripts and planned work for drift from the documented blueprint and process rules.                |

These prompts are intentionally short and role-specific. The CLI should treat them as canonical task intents that may be wrapped with repository context, current state, gate failures, and required evidence before dispatching the agent.

## Requirements Interview

The agent generates a structured interview using the template in the process standards. The output is written to `docs/prd.md`. See `product-owner-interview.md` in the process prompts for the interview template.

## Implementation Plan Format

```markdown
## Phase: Scaffold

- [x] Initialize git repository
- [x] Create GitHub remote
- [x] Set up CI workflows
- [ ] Stub all test suites

## Phase: Prototype

- [ ] Create landing page with mock data
- [ ] Implement basic navigation
```

Tasks are markdown checkboxes grouped by phase. Updated at every commit with both discovery (new tasks) and completion (checked boxes).

## Next Prompt Format

```markdown
## Next Action

Read `docs/plans/implementation-plan.md` and locate the first unchecked
task under "Phase: Scaffold". The previous commit completed CI workflow
setup. The next task is stubbing the test suites.

Create empty test files for: server unit, server integration, browser
unit, browser component, browser e2e. Use Vitest for unit tests and
Playwright for browser tests. Reference the testing-blueprint for test
categories and naming conventions.

After completing, update the implementation plan and write the next
prompt for the following task.
```

Written in second person. Self-contained. Includes context about what was just completed and what comes next.

## Pre-Commit Hook Enforcement

The git pre-commit hook (defined in `git-standards.md`) verifies that both `docs/plans/implementation-plan.md` and `docs/plans/next-prompt.md` are included in the commit's staged files. If either is missing, the commit is rejected.

## Documentation Merge Enforcement

Documentation files are merge-protected and require explicit agent resolution.

Implementation details:

1. `.gitattributes` marks documentation-like files (`*.md`, `*.rst`, `*.txt`) with `merge=binary`, preventing automatic line-level merges.
2. `.githooks/pre-commit` scans staged documentation files and blocks commits containing merge conflict markers.
3. Merge protocol: read older and newer docs, produce one coherent result, and prefer the newer document when uncertain.

This combination is intended to prevent unintentional document corruption and accidental conflict-marker commits. In Calypso's process model, this discipline is mandatory for agent-maintained documentation, not a situational hardening toggle.

## Scaffold Checklist (Stage 0)

1. `git init` + `gh repo create`
2. Create `.github/workflows/` with CI jobs
3. Stub all test suites (server unit, integration, browser unit, component, e2e)
4. Verify all tests run (and fail, since no implementation exists)
5. Write initial implementation plan and next-prompt

## Dependency Justification

| Package       | Reason                                                   | Buy or DIY |
| ------------- | -------------------------------------------------------- | ---------- |
| None required | The process blueprint introduces no runtime dependencies | N/A        |
