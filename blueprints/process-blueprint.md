# Process Blueprint

<!-- last-edited: 2026-03-13 -->

CONTEXT MAP
this ◀──implemented by── implementation-ts/process-implementation.md
this ◀──referenced by──── development/development-standards.md
this ◀──referenced by──── index.md

> [!IMPORTANT]
> This blueprint defines the development process for AI-agent-built software: how work is planned, how progress is tracked, and how an agent advances through a product lifecycle without continuous human prompting.

---

## Vision

Software development is a state machine. Each unit of work transforms the project from one known state to a known next state. In human-driven development, the state machine runs on tribal knowledge, standup meetings, and ticket boards — none of which an AI agent can attend. When an agent starts a session, it has no memory of what happened yesterday, no sense of what is blocked, and no intuition about what matters most. Without an explicit, machine-readable process, the agent either waits for a human to tell it what to do next (defeating the purpose of autonomous development) or guesses (producing work that may be irrelevant, redundant, or out of order).

A correct process for agent-driven development makes the state machine explicit. Product requirements and implementation plans live in GitHub Issues, not in repository files. The product owner maintains an Implementation Plan issue that links to feature issues. Each feature issue tracks motivation, acceptance criteria, test scenarios, and completion stage. Every commit moves work forward through the issue tracker, and the issue descriptions encode the instructions for the next action. In Calypso, that loop is governed by Calypso itself: a YAML workflow definition declares states, transitions, roles, and gates, and the Calypso CLI orchestrates agents against that machine. The agent becomes self-advancing under policy control — a human can walk away for hours and return to find meaningful, ordered progress.

Calypso CLI is not the coding agent. It is the process authority. It owns state transitions, validates gates, schedules narrow role-specific agents, and records structured outcomes. Git and GitHub are part of the control surface, not incidental integrations. The primary interactive operator surface is the local CLI and TUI; a browser operator surface may exist, but the process model does not depend on one.

**Scope Note:** This blueprint applies exclusively to the agent's _engineering and development roles_ (e.g., writing code, planning features, scaffolding projects). It does not govern any administrative, operational, or in-app roles the agent may hold on behalf of end-users within the deployed software. Those roles are governed by the respective functional blueprints including Auth, Data, and UX.

The cost of ignoring this blueprint is an agent that produces impressive-looking code in random order, skipping foundational work to build visible features, leaving gaps that compound until the project requires a human to manually re-plan and re-prioritize. The process is not overhead — it is the mechanism that converts an agent from a sophisticated autocomplete into a reliable development partner.

---

## Threat Model

| Scenario                                                         | What must be protected                                                                                       |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Agent starts a session with no context about prior work          | Continuity — the agent must resume exactly where the last session left off                                   |
| Agent builds features before foundational infrastructure exists  | Build order — scaffolding, CI, and test stubs must precede feature work                                      |
| Product requirements change mid-development                      | Adaptability — the plan must accommodate changes without losing track of completed work                      |
| Agent works on low-priority tasks while critical work is blocked | Prioritization — the implementation plan must encode priority and ordering                                   |
| Multiple agents work on the same project with conflicting plans  | State authority — one Calypso state machine governs advancement; agents do not invent parallel plans         |
| Agent completes work but does not update the plan                | Plan accuracy — the plan must reflect reality at every commit                                                |
| Human overrides the agent's next task                            | Human authority — the next-prompt file is human-editable and the agent respects overrides                    |
| Agent session crashes mid-task                                   | Recoverability — git commits are the unit of durable progress; uncommitted work is forfeit                   |
| Requirements are ambiguous or incomplete                         | Requirement quality — the PRD interview must extract concrete, testable requirements                         |
| A producing agent marks its own work complete without review     | Transition integrity — state advancement requires the configured validation transition, not self-attestation |
| Gates are skipped because an agent "knows" the work is correct   | Determinism — the CLI must evaluate declared gates before entering the next state                            |

---

## Core Principles

### The commit is the unit of progress

Every meaningful state change is captured in a git commit. Between commits, work is speculative and lossy. The agent's goal is to reach the next committable state as quickly as possible — not to accumulate a large batch of changes. Small, frequent commits create a fine-grained history that is easy to review, easy to revert, and easy to resume from.

### Plans are living documents, not initial artifacts

An implementation plan written once and never updated is a fiction within days. The plan is updated at every commit — new tasks are discovered and added, completed tasks are checked off, ordering is adjusted based on what the agent learned during implementation. The plan is the agent's working memory across sessions.

### The state machine, not the agent, authorizes progression

Agents do not decide unilaterally that work is complete, reviewed, or ready for the next phase. Calypso provides a YAML state machine that defines states, allowed transitions, assigned agent roles, validation roles, and deterministic gates. The Calypso CLI evaluates that machine and advances work only when the declared transition conditions pass. This keeps process authority in machine-readable policy rather than in whichever agent last touched the repository.

### The next action is always explicit

An agent should never need to decide "what should I do now?" by analyzing the entire codebase and plan from scratch. The next-prompt file contains a single, self-contained instruction for the very next action. It is written by the agent at the end of each commit, creating a self-advancing loop. A human can override it at any time by editing the file.

### Agents are narrow specialists, not general project managers

The concurrent model assumes agents operate with narrow context and perform small tasks. A producing agent solves one constrained step. A checking agent with similarly narrow context validates that output against explicit criteria. The state machine then decides whether the work advances, loops for correction, or escalates. Broad, free-form agent autonomy is replaced by specialized roles and explicit transitions.

### Requirements are extracted, not assumed

The agent does not guess what the product should do. It generates structured interview questions for the Product Owner, collects answers, and writes a canonical Product Requirements Document. The PRD is owned by the human; the implementation plan is derived from it by the agent. This separation ensures the human controls _what_ and the agent controls _how_.

### Infrastructure enforces sequencing

An agent cannot begin feature work while foundational infrastructure is incomplete. Repository, CI, test stubs, and deployment must be operational before the first feature commit. A checklist of concrete, verifiable conditions governs this — the conditions are not bureaucracy; they prevent the agent from building a beautiful facade on a foundation that does not exist.

### Deterministic gates are first-class process controls

Every important transition in the workflow has explicit gates: tests pass, required documents exist, review step completed, environment prepared, policy checks satisfied. These gates are deterministic checks controlled by the Calypso state machine and executed by the Calypso CLI. If a gate is not machine-checkable, it is not yet a reliable transition condition and should not be treated as one.

---

## Design Patterns

### Pattern 1: Issue-Based Planning Loop

**Problem:** An agent needs to know what the product should do, what work remains, and what to do right now. These are three different questions with different owners and different update frequencies. Maintaining them as files in the repository creates merge conflicts, state drift, and requires manual synchronization.

**Solution:** Maintain planning state in GitHub Issues instead of repository files:

- **Implementation Plan Issue** — a unique global tracking issue containing phase headings with checklists linking to feature issues. Owned by the agent, never closes. Created during requirements gathering, updated at every commit as phases complete.
- **Feature Issues** — one per feature, with structured sections: Motivation (what problem this solves), Features (checkboxes for acceptance criteria), Test Plan (test scenarios), and Stage (documented | tests | stubs | implemented | testing). Owned by the agent. Created during requirements gathering, updated as implementation progresses, closed when fully implemented and tested.
- **Issue Descriptions** — contain the next action for the agent. As the agent updates issue state and stage, the description field encodes what to do next. This replaces the file-based next-prompt concept.

The issues form a hierarchy: requirements produce feature issues, feature issues are linked in the Implementation Plan issue. Information flows through the issue tracker; the agent reads issue state as the source of truth for what comes next.

**Trade-offs:** Moving planning to GitHub Issues eliminates repository file synchronization overhead and eliminates pre-commit hook gates. The agent must use `gh` to create and update issues instead of editing files. In return, planning state lives where pull requests live, integrating naturally with code review and team visibility.

### Pattern 2: Self-Advancing State Machine

**Problem:** Agent sessions are discontinuous. Each session starts cold, with no memory of the previous session. Without explicit continuation, the agent must re-derive the project state from scratch — which is slow, error-prone, and may produce different conclusions each time.

**Solution:** Each commit writes the next-prompt file as its final action. The next session reads this file as its first action. The result is a chain: commit N writes the instructions for commit N+1, which writes the instructions for commit N+2. The agent can execute multiple commits in a single session without waiting for human input between them. A human can break the chain at any time by editing the next-prompt file.

**Trade-offs:** If the agent writes a poor next-prompt (too vague, wrong priority), the next session starts on the wrong foot. Mitigated by the implementation plan, which provides broader context. If both are wrong, the human intervenes by editing one or both.

### Pattern 2A: Calypso YAML Workflow Definition

**Problem:** A prose description of workflow order is too weak for multi-agent orchestration. Different agents will interpret the same written process differently and invent incompatible branching behavior.

**Solution:** Calypso provides a YAML file that declares the workflow state machine. Each state defines the responsible agent role, accepted inputs, required outputs, allowed next states, validation requirements, and deterministic gates. The YAML is the process authority. Agents read it; the Calypso CLI enforces it.

The first default workflow shape is feature-centric:

- `version: 1`
- `name: calypso-default-feature-workflow`
- `initial_state: new`
- ordered states: `new`, `prd-review`, `architecture-plan`, `scaffold-tdd`, `architecture-review`, `implementation`, `waiting-for-human`, `qa-validation`, `ready-for-review`, `release-ready`, `done`, `blocked`, `aborted`

It also defines the core feature-unit invariant:

- feature equals branch
- feature equals worktree
- feature equals pull request

In other words, one feature unit maps to one branch, one worktree, and one PR. Calypso does not treat those as loose conventions; the state machine treats them as required evidence before work can advance.

**Trade-offs:** Authoring a correct state machine is more upfront work than writing a loose checklist. That cost is acceptable because ambiguous workflow logic is what creates hidden coordination failures in autonomous systems.

### Pattern 2B: Producer-Validator Handoff

**Problem:** If the same agent that produces work is also trusted to decide that the work is correct, multi-agent execution collapses into self-attestation.

**Solution:** Separate production transitions from validation transitions. A producer agent completes a narrow task and emits the required artifact. A validator agent with similarly narrow scope checks that artifact against explicit criteria. Only then may the state machine move to the next state. The validator does not rewrite the whole project; it verifies one bounded output.

The first default workflow uses this handoff structure repeatedly through explicit actors such as:

- `orchestrator`
- `architect`
- `engineer`
- `merge-queue`
- `human-or-product`
- `human-or-architect`
- `human`
- `github`

This is deliberate. A state transition is attached to a role, not to whichever agent happens to be available.

**Trade-offs:** This adds another step to many tasks. The cost is intentional because review is part of the state machine, not an optional courtesy.

### Pattern 2E: Merge Queue Ownership

**Problem:** A feature can be individually merge-ready while still being the wrong next PR to land. Shared dependencies, `main` drift risk, rollout sequencing, and review ordering all create cases where multiple acceptable PRs still need a deterministic landing order.

**Solution:** Calypso assigns merge ordering and merge execution to a dedicated merge-queue role. The merge-queue agent does not re-review the whole implementation; it determines which merge-ready features should land first, records the rationale, marks only one queue-head feature as eligible to merge, and executes that merge when the queue conditions hold. Other features remain merge-ready but blocked on queue position rather than on implementation quality.

**Trade-offs:** This introduces another explicit stage between "ready for review" and "merged." That overhead is justified because merge order is part of repository safety, not a social afterthought.

### Pattern 2C: Gate Groups and Evidence

**Problem:** Workflow states are not enough on their own. A transition also needs explicit proof that the required conditions are satisfied.

**Solution:** The Calypso YAML groups deterministic gates by concern. The first default workflow defines at least these gate groups:

- `specification`
- `implementation`
- `validation`
- `merge-readiness`

Each gate declares its owner, evidence source, blocking behavior, and PR checklist label. This lets Calypso unify local checks, CI checks, agent review tasks, and human approvals into one transition model instead of scattering them across shell scripts and tribal process.

**Trade-offs:** Gate modeling increases workflow authoring complexity. The benefit is that process state and proof of compliance live in the same machine-readable artifact.

### Pattern 2D: Task Catalog Backing the Workflow

**Problem:** A workflow state machine can name transitions and gates without defining which executable tasks actually satisfy them. That leaves enforcement ambiguous.

**Solution:** The Calypso workflow also declares a task catalog. The first default task set includes:

- builtins: `doctor-clean`, `feature-unit-bound`, `workflow-files-present`, `rust-quality`, `test-matrix`, `main-compatibility`
- agent tasks: `pr-editor`, `documentation-merge`, `blueprint-review`
- human tasks: `human-clarification`, `human-review-approval`

Each task has a kind and, where relevant, a builtin implementation or an assigned agent role. This lets the state machine refer to stable task identifiers instead of embedding execution details in every transition.

**Trade-offs:** The workflow now has two coordinated artifacts inside one schema: state logic and task inventory. That is more structure, but it prevents drift between "what must happen" and "what can actually execute."

### Pattern 3: Structured Requirements Interview

**Problem:** Product requirements communicated informally (chat messages, verbal descriptions, vague feature requests) produce vague, incomplete, and contradictory specifications. The agent builds what it thinks was meant, not what was actually needed.

**Solution:** The agent generates a structured interview document with concrete questions organized by domain: user roles, data model, workflows, integrations, constraints. The Product Owner answers in writing. The agent synthesizes the answers into a canonical PRD with testable acceptance criteria. The PRD is the contract — if it is not in the PRD, the agent does not build it.

**Trade-offs:** The interview process takes time upfront. Product Owners may resist the formality. But the alternative — building from informal requirements and iterating on misunderstandings — costs far more in rework.

### Pattern 4: Infrastructure Before Features

**Problem:** Agents optimize for visible output. Given a feature list, an agent will build the most impressive-looking features first, leaving infrastructure, testing, and error handling for "later." Later arrives and the codebase is a demo with no foundation.

**Solution:** Before implementing any feature, the repository, CI pipeline, test stubs, and deployment infrastructure must be operational. The rule is simple: if the scaffold is not complete, no feature work begins. The scaffold is not a phase — it is a prerequisite that must be satisfied immediately and maintained throughout development.

**Trade-offs:** This discipline requires resisting the pull toward visible progress. An agent that has not shipped a feature may appear unproductive. The alternative — building features on a broken foundation — produces work that cannot be tested, deployed, or extended.

---

## Plausible Architectures

### Architecture A: Solo Agent Loop (one agent, one project)

```
┌──────────────────────────────────────────────────┐
│                                                  │
│  Human writes/updates PRD                        │
│       │                                          │
│       ▼                                          │
│  Agent reads PRD + plan + next-prompt            │
│       │                                          │
│       ▼                                          │
│  Agent executes next task                        │
│       │                                          │
│       ▼                                          │
│  Agent commits:                                  │
│    1. Code changes                               │
│    2. Updated implementation plan                │
│    3. New next-prompt                            │
│       │                                          │
│       ▼                                          │
│  Loop back to "read" (same session)              │
│  ── or ──                                        │
│  Session ends; next session reads next-prompt    │
│                                                  │
└──────────────────────────────────────────────────┘
```

**When appropriate:** Single agent working on a project. Most common case for early-stage development. Human checks in periodically to review commits and adjust the PRD or next-prompt.

**Trade-offs:** No parallelism. One agent, one task at a time. Simple and predictable.

### Architecture B: Calypso-Orchestrated Multi-Agent Flow

```
┌────────────────────────────────────────────────────────┐
│                                                        │
│  Calypso YAML state machine                            │
│       │                                                │
│       ▼                                                │
│  Calypso CLI assigns current state                     │
│  to a narrow producer agent                            │
│       │                                                │
│       ▼                                                │
│  ┌─────────────┐    artifact    ┌───────────────┐     │
│  │ Producer     │──────────────▶│ Validator      │     │
│  │ agent        │               │ agent          │     │
│  │ narrow task  │               │ narrow check   │     │
│  └──────┬──────┘                └───────┬───────┘     │
│         │                               │             │
│         └──────────────┬────────────────┘             │
│                        ▼                              │
│          Calypso CLI evaluates deterministic gates    │
│                        │                              │
│               pass ───▶│◀── fail                      │
│                        ▼                              │
│               Advance / loop / escalate               │
│                                                        │
└────────────────────────────────────────────────────────┘
```

**When appropriate:** Projects that need concurrent agent execution without surrendering sequencing authority to whichever agent happens to run next. Each task is small, role-bound, and transition-controlled.

**Trade-offs:** More orchestration machinery and more validation steps. The benefit is that concurrency becomes explicit and auditable instead of emergent and fragile.

### Architecture C: Human-in-the-Loop Gated (regulated or high-stakes)

```
┌────────────────────────────────────────────────────────┐
│                                                        │
│  Agent executes one task → commits → writes next-prompt│
│       │                                                │
│       ▼                                                │
│  GATE: Human reviews commit                            │
│       │                                                │
│       ├── Approved → Agent reads next-prompt, continues│
│       │                                                │
│       └── Rejected → Human edits next-prompt with      │
│                      corrections, agent re-executes    │
│                                                        │
└────────────────────────────────────────────────────────┘
```

**When appropriate:** High-stakes domains (finance, healthcare, compliance) where every commit must be reviewed before the agent proceeds. Slower but safer. The human is a gate, not a driver — the agent still proposes the work and the plan.

**Trade-offs:** Throughput is limited by human review speed. The agent may idle waiting for approval. Acceptable when correctness matters more than velocity.

---

## Reference Implementation — Calypso TypeScript

> The following is the Calypso TypeScript reference implementation. The principles and patterns above apply equally to other stacks; this section illustrates one concrete realization in the Calypso monorepo.

See [`agent-context/implementation-ts/process-implementation.md`](../implementation-ts/process-implementation.md) for the full stack specification: planning document locations, implementation plan format, next-prompt format, pre-commit hook enforcement, and scaffold checklist.

---

## Implementation Checklist

- [ ] Implementation Plan GitHub Issue exists with title "Implementation Plan" (unique, global per project)
- [ ] Implementation Plan issue contains phases with feature issue links using `- [ ] #<issue-number> Feature Name` format
- [ ] At least one Feature Issue exists with title, Motivation section, Features (checkboxes), Test Plan (checkboxes), and Stage field
- [ ] Feature issues have appropriate Stage value: documented | tests | stubs | implemented | testing
- [ ] Human has reviewed and approved the PRD via the Implementation Plan issue content
- [ ] Calypso workflow YAML exists and defines states, transitions, roles, and gates
- [ ] All scaffold tasks completed: repo, CI, test stubs verified before any feature work
- [ ] Agent has not built any features ahead of scaffold completion
- [ ] Implementation Plan issue accurately reflects all completed and remaining work (audited by human)
- [ ] Feature issues are updated as implementation progresses (checkboxes checked, stage field updated)
- [ ] Multiple sessions demonstrated: agent reads issue state and resumes work from the last recorded stage
- [ ] Feature issues include discovered tasks (tasks added during implementation, not just initial planning)
- [ ] Issue descriptions contain clear next-action guidance for the agent (replacing next-prompt concept)
- [ ] Process documentation in `docs/` reflects the actual process used (not aspirational)
- [ ] Recovery procedure tested: agent resumes correctly after a crashed session by reading issue state
- [ ] Human can onboard a new agent to the project using only the GitHub Issues and repository code
- [ ] At least one producer-to-validator transition exercised through the Calypso CLI
- [ ] At least one deterministic gate failure observed and handled without manual workflow improvisation
- [ ] Commits reference issue numbers using `#<issue-number>` in commit messages for traceability

---

## Antipatterns

- **The phantom plan.** Writing an implementation plan at the start of the project and never updating it. Within days the plan diverges from reality. The agent ignores it and makes its own decisions. The plan becomes a historical artifact that misleads anyone who reads it.

- **Feature-first development.** Jumping to visible features (UI, integrations) before scaffold infrastructure is complete. The result is a demo that cannot be tested, deployed, or extended. Fixing the foundation after building the house is always more expensive than building it first.

- **Session amnesia.** Starting each agent session by asking "what should I work on?" instead of reading the next-prompt file. The agent re-derives the project state from the codebase, arrives at a different conclusion than the previous session, and produces work that conflicts with or duplicates prior efforts.
- **Parallel agents without a governing machine.** Spawning multiple agents and hoping they coordinate through intuition, branch names, or chat logs. Without a governing state machine and deterministic gates, concurrency becomes nondeterministic drift.

- **Monolithic commits.** Accumulating hours of work into a single massive commit. If the session crashes before the commit, all work is lost. If the commit introduces a bug, the revert is catastrophic. Small commits are cheaper in every dimension.

- **Verbal requirements.** Accepting feature requests from chat messages, verbal conversations, or vague tickets without formalizing them into the PRD. The agent builds what it understood, which is never exactly what was meant. The PRD is the contract — if it is not written there, it does not get built.

- **Plan as wishlist.** Writing implementation plan tasks as vague goals ("improve performance", "make it look better") instead of concrete, verifiable actions ("add database index on users.email", "reduce landing page bundle to under 200KB"). Vague tasks produce vague work.

- **Skipping the interview.** Assuming the agent already knows what the product should do based on its training data or a brief description. Every product has domain-specific requirements that cannot be inferred. The structured interview exists to surface them before development begins, not after.
