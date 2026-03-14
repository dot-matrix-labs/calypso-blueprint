# Agent Context Index

<!-- last-edited: 2026-03-13 -->

CONTEXT MAP
this ◀──referenced by── agent-communication.md §Document Discovery
this ──indexes──────────▶ blueprints/_, implementation-ts/_, development/_, init/_

> [!IMPORTANT]
> `agent-context/` is the canonical Calypso agent documentation set. Read this file first to determine which documents to load for your task.

> [!NOTE]
> `agent-context/` is the only retained agent documentation tree in this repository.
>
> - Versioned predecessor copies were removed after consolidation.
> - Active work MUST follow `agent-context/` only.

---

## Document Graph

```
                          agent-communication.md (root — authoring standard)
                                     │
            ┌────────────────────────┼────────────────────────┐
            ▼                        ▼                        ▼
      blueprints/              implementation-ts/        development/
            │                        │                        │
            │  ┌─────────────────────┤                        │
            ▼  ▼                     ▼                        ▼
   [each blueprint] ◀─all── [each impl doc]         development-standards
            │                        │                        │
   ┌────────┼────────┐               │               ┌───────┼───────┐
   ▼        ▼        ▼               ▼               ▼       ▼       ▼
 arch    data    auth  ...     [mirrors blueprint    git   hardening  docs
 blueprint  blueprint          hierarchy 1:1]       standards       standard
   │        │        │
   ▼        ▼        ▼
 deploy  environment  ux
 blueprint blueprint  blueprint
            │
            ▼
        worker-blueprint
        process-blueprint
        testing-blueprint
```

### Blueprint → Implementation Pairs

```
blueprints/architecture-blueprint.md  ──▶  implementation-ts/architecture-implementation.md
blueprints/auth-blueprint.md          ──▶  implementation-ts/auth-implementation.md
blueprints/data-blueprint.md          ──▶  implementation-ts/data-implementation.md
blueprints/deployment-blueprint.md    ──▶  implementation-ts/deployment-implementation.md
blueprints/environment-blueprint.md   ──▶  implementation-ts/environment-implementation.md
blueprints/process-blueprint.md       ──▶  implementation-ts/process-implementation.md
blueprints/testing-blueprint.md       ──▶  implementation-ts/testing-implementation.md
blueprints/ux-blueprint.md            ──▶  implementation-ts/ux-implementation.md
blueprints/worker-blueprint.md        ──   (no implementation doc yet)
```

### Development Workflows

```
development/development-standards.md   ── new feature workflow
development/hardening.md               ── hardening workflow
development/git-standards.md           ── commit message format
development/documentation-standard.md  ── doc writing rules
development/product-owner-interview.md ── requirements collection
init/scaffold-task.md                  ── project bootstrap entrypoint
```

---

## Keyword Index

| Keyword             | Primary Document                                  | Also Referenced In                               |
| ------------------- | ------------------------------------------------- | ------------------------------------------------ |
| authentication      | blueprints/auth-blueprint.md                      | implementation-ts/auth-implementation.md         |
| authorization       | blueprints/auth-blueprint.md                      | implementation-ts/auth-implementation.md         |
| agent scopes        | blueprints/auth-blueprint.md                      | implementation-ts/auth-implementation.md         |
| API                 | blueprints/architecture-blueprint.md              | implementation-ts/architecture-implementation.md |
| architecture        | blueprints/architecture-blueprint.md              | implementation-ts/architecture-implementation.md |
| bootstrap           | init/scaffold-task.md                             | blueprints/environment-blueprint.md              |
| commit              | development/git-standards.md                      | agent-communication.md §Part 4                   |
| containers          | blueprints/environment-blueprint.md               | implementation-ts/environment-implementation.md  |
| data model          | blueprints/data-blueprint.md                      | implementation-ts/data-implementation.md         |
| database            | blueprints/data-blueprint.md                      | implementation-ts/data-implementation.md         |
| dependencies        | blueprints/architecture-blueprint.md §Buy vs. DIY | implementation-ts/\* (Buy/DIY tables)            |
| deploy              | blueprints/deployment-blueprint.md                | implementation-ts/deployment-implementation.md   |
| encryption          | blueprints/data-blueprint.md                      | blueprints/auth-blueprint.md                     |
| environment         | blueprints/environment-blueprint.md               | implementation-ts/environment-implementation.md  |
| feature development | development/development-standards.md              | agent-communication.md §Part 4                   |
| git                 | development/git-standards.md                      | agent-communication.md §Part 4                   |
| hardening           | development/hardening.md                          | agent-communication.md §Part 4                   |
| Kubernetes          | blueprints/environment-blueprint.md               | blueprints/deployment-blueprint.md               |
| monorepo            | blueprints/architecture-blueprint.md              | implementation-ts/architecture-implementation.md |
| process             | blueprints/process-blueprint.md                   | implementation-ts/process-implementation.md      |
| requirements        | development/product-owner-interview.md            | agent-communication.md §Part 4                   |
| scaffold            | init/scaffold-task.md                             | blueprints/environment-blueprint.md              |
| security            | blueprints/auth-blueprint.md                      | blueprints/data-blueprint.md                     |
| testing             | blueprints/testing-blueprint.md                   | implementation-ts/testing-implementation.md      |
| UI                  | blueprints/ux-blueprint.md                        | implementation-ts/ux-implementation.md           |
| UX                  | blueprints/ux-blueprint.md                        | implementation-ts/ux-implementation.md           |
| worker              | blueprints/worker-blueprint.md                    | blueprints/process-blueprint.md                  |

---

## Task Routing

| If your task involves...         | Load these documents                                                                    |
| -------------------------------- | --------------------------------------------------------------------------------------- |
| New feature development          | development/development-standards.md → relevant blueprint → relevant implementation doc |
| Hardening existing code          | development/hardening.md → relevant blueprint → relevant implementation doc             |
| Writing a commit                 | development/git-standards.md                                                            |
| Writing or editing documentation | agent-communication.md → development/documentation-standard.md                          |
| Scaffolding a new project        | init/scaffold-task.md → blueprints/environment-blueprint.md                             |
| Database / data model work       | blueprints/data-blueprint.md → implementation-ts/data-implementation.md                 |
| Auth / permissions               | blueprints/auth-blueprint.md → implementation-ts/auth-implementation.md                 |
| API / service architecture       | blueprints/architecture-blueprint.md → implementation-ts/architecture-implementation.md |
| UI / frontend                    | blueprints/ux-blueprint.md → implementation-ts/ux-implementation.md                     |
| Deployment                       | blueprints/deployment-blueprint.md → implementation-ts/deployment-implementation.md     |
| Environment / infra              | blueprints/environment-blueprint.md → implementation-ts/environment-implementation.md   |
| Background jobs / workers        | blueprints/worker-blueprint.md → blueprints/process-blueprint.md                        |
| Testing                          | blueprints/testing-blueprint.md → implementation-ts/testing-implementation.md           |

---

## YAML Rule System

The canonical rule corpus lives in `rules/`. Start with the graph index, then load specific rule files on demand:

```
rules/graph.yaml          ── compact graph index (load first, ~757 rules)
rules/changelog.yaml      ── version history
rules/blueprints/*.yaml   ── 9 blueprint rule files (ARCH, AUTH, DATA, DEPLOY, ENV, PROCESS, TEST, UX, WORKER)
rules/implementations/*.yaml ── 8 implementation rule files (IMPL-ARCH, IMPL-AUTH, etc.)
```

Each rule has a stable hash identity (`sha256("NUMBER:name")[:12]`), typed links to other rules, and a category (principle, threat, design_pattern, architecture, checklist, antipattern, implementation).

The markdown files in `blueprints/` and `implementation-ts/` are retained for reference but `rules/` is canonical.

---

## Precedence

When documents conflict, see `agent-communication.md` §Document Precedence Rules. Summary:

```
rules/ (YAML)  >  development docs  >  implementation docs (markdown)  >  blueprints (markdown)
Within a tier: most recent last-edited date wins.
```
