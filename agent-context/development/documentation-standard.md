# Documentation Standard (Business Application)

<!-- last-edited: 2026-03-12 -->

CONTEXT MAP
this ──governs─────────▶ docs/ and README.md files within the PROJECT BEING BUILT
this ──does NOT govern─▶ agent-context/ (governed by agent-communication.md)

> **Scope:** This document governs documentation structure within the **business application project** that Calypso agents build — the `docs/` directory, per-directory `README.md` files, and source code inline documentation. It does NOT govern `agent-context/` documents (those are governed by `agent-communication.md`).

This document defines the Documentation Fractal methodology for Calypso projects.

## Core Principle

**"The codebase is the map."**

Every directory is a node in a tree. Every node must describe itself. Autonomous agents should be able to navigate the codebase without vector databases, RAG, or external search tools.

## Rules

### 1. The Root Anchor

The project root must contain a `README.md` that serves as the "High Orbit" view. It points to the main entry points (e.g., `./docs/README.md`, `./src/README.md`).

### 2. No Stranded Docs

There should be **no documentation files** (other than `README.md`) outside of the canonical `./docs/` directory.

- **Why?** Scatter-gun documentation gets lost. By centralizing "substantive" documentation in `./docs/`, agents know exactly where to look for knowledge.
- **Exception**: `README.md` files are allowed (and required) in every sub-directory to explain _what that directory contains_.

### 3. The Fractal Structure

Every subdirectory (node) should contain a `README.md` that:

1. **Summarizes** the directory's purpose.
2. **Lists** key files or subdirectories.
3. **Links** back to the "parent" knowledge base if deeper context is needed (usually in `./docs/`).

```
root/
├── README.md              # High Orbit: "What is this project?" -> Links to docs/README.md
├── src/
│   ├── README.md          # "This is the source code." -> Links to architecture docs in docs/technical/
│   ├── modules/
│   │   ├── auth/
│   │   │   ├── README.md  # "This handles auth." -> Links to auth specs in docs/features/
```

### 4. Canonical Naming

All documentation files inside `./docs/` must use **kebab-case** (`my-doc.md`) to ensure consistent URL routing and OS compatibility.

### 5. README.md in Every Directory

Every directory in the project should contain a `README.md` that explains:

- What the directory contains
- Key files and their purposes
- How it relates to other parts of the project

### 6. Documentation Merge Protocol (No Auto-Merge)

Automated line-level merges for documentation files are not allowed.

When a documentation merge conflict occurs:

1. Read both versions completely (older and newer).
2. Propose a single coherent merged document version.
3. If uncertain, defer to the newest source document.
4. Resolve the conflict by staging one final document, not a line-spliced mash of both sides.

The outcome must be one intentional document chosen by an agent, with clear narrative continuity.

## Benefits for Agents

1. **O(1) Navigation**: An agent entering any directory can read `README.md` to understand the context immediately.
2. **Deterministic Search**: Agents don't need to guess "where are the docs?". They are always in `./docs/` or in the local `README.md`.
3. **Self-healing**: If an agent adds a new directory, the documentation standard reminds them to add a `README.md`.

## Enforcement

This repository enforces documentation safety with both merge strategy and hooks:

1. `.gitattributes` sets docs-like extensions (`.md`, `.rst`, `.txt`) to `merge=binary`, which disables automatic line-level merge for these files and forces explicit human/agent resolution.
2. `.githooks/pre-commit` blocks commits when staged documentation files still contain merge conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`, `|||||||`).
3. Existing hook checks continue to enforce planning-document staging and repository standards.

Operational note:

- If the repository uses `core.hooksPath=.githooks`, hooks are versioned at `.githooks/*` and do not use `.git/hooks/*` directly.
