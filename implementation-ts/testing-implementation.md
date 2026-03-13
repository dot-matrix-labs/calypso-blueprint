# Testing — Calypso TypeScript Implementation

<!-- last-edited: 2026-03-13 -->

CONTEXT MAP
this ──implements──▶ blueprints/testing-blueprint.md
this ◀──referenced by── index.md

> Implements: Testing Blueprint (`agent-context/blueprints/testing-blueprint.md`)

The principles, threat model, and patterns in that document apply equally to other stacks. This document defines the mandatory TypeScript reference implementation for Calypso: execution details, suite layout, and tooling constraints.

TypeScript rule of execution:

1. Vitest is the single test driver for all TS test categories.
2. Browser-required tests still run in a real browser engine.
3. Infrastructure setup and teardown (containers, servers, fixtures, env wiring) is always performed from the Bun runtime side of Vitest hooks or setup files.

---

## Test Categories

| Category                   | Test Driver | Browser Engine | Infra Runtime Owner | Location             |
| -------------------------- | ----------- | -------------- | ------------------- | -------------------- |
| Unit tests                 | Vitest      | N/A            | Bun runtime         | `/tests/unit`        |
| API integration tests      | Vitest      | N/A            | Bun runtime         | `/tests/integration` |
| React component tests      | Vitest      | Playwright     | Bun runtime         | `/tests/component`   |
| Full-page user story tests | Vitest      | Playwright     | Bun runtime         | `/tests/e2e`         |

Notes:

- `Playwright` is a browser provider, not the top-level TS test runner.
- For browser suites, Vitest owns lifecycle and reporting; Playwright provides the headless Chromium engine.
- Dynamic infrastructure values (for example DB URL with random port) are generated in Bun runtime and passed into app processes started by Vitest-controlled setup.

## CI Workflow Structure

```
.github/workflows/
  quality-gate.yml
  release.yml
  test-unit.yml
  test-api.yml
  test-component.yml
  test-e2e.yml
  test-pg-container.yml
```

`quality-gate.yml`:

1. Installs Bun and dependencies
2. Runs lint
3. Runs format check
4. Runs build verification

Current test workflows (`test-unit.yml`, `test-api.yml`, `test-component.yml`, `test-e2e.yml`, `test-pg-container.yml`):

1. Install runtime dependencies for the suite
2. Run the suite's canonical test command only
3. Report pass/fail independently

Release builds must also pass the release workflow gates before tagged publication.

Merge is blocked unless quality gate and all required test workflows pass.

Schema-upgrade compatibility remains a required release doctrine in the deployment blueprint, but this repository does not yet ship a canonical `test-schema-upgrade-compatibility` CI workflow. Do not claim that workflow exists until the suite and its entrypoint actually exist in the repo.

Local invocation must use the exact same per-suite commands as CI. CI cannot use alternate runners or alternate suite entrypoints.

## Golden Fixture Format

Fixtures are file artifacts under `/tests/fixtures/` (or suite-specific fixture folders). The fixture recorder is a Bun script that:

1. Reads runtime configuration from Bun-side test setup (hardcoded non-secret values in test code, or dynamic values produced by test infrastructure such as container URLs/ports)
2. Makes real HTTP requests to external services
3. Writes response bodies and headers to JSON files in `/tests/fixtures/`
4. Logs schema changes compared to existing fixtures

Environment variables are configuration only. They are not used as fixture storage.

## Environment Setup Contract

Vitest must set up and tear down test infrastructure. Setup logic is not delegated to ad hoc shell sessions or external manual orchestration.

Required pattern:

1. Use Vitest lifecycle (`beforeAll`, `afterAll`, setup files, or test projects) to create and destroy infrastructure.
2. Run setup code in Bun runtime (`bun --bun vitest ...`) so the same runtime owns subprocesses and environment values.
3. Start infrastructure from Bun runtime code (for example Dockerized Postgres, API server process, fixture server) and expose generated connection details to tests.
4. Never rely on a fixed `DATABASE_URL` for browser/integration suites when the container helper provides a random host port.
5. Keep per-suite command parity between local and CI: the command that runs a suite locally is the same command CI uses for that suite.

## Browser Test Configuration

All browser-required tests use real Playwright browsers in headless mode under Vitest control.

- Browser tests are launched through Vitest configuration, not a standalone Playwright TS test runner.
- Browser execution has no GUI, no display server, and no `DISPLAY` dependency.
- Browser tests may call into Bun-side helpers through Vitest-supported setup mechanisms to coordinate infrastructure.

## Dependency Justification

| Package    | Reason                                                                 | Buy or DIY |
| ---------- | ---------------------------------------------------------------------- | ---------- |
| Vitest     | Mandatory TS test driver; owns lifecycle, orchestration, and reporting | Buy        |
| Playwright | Browser provider used by Vitest for real headless browser execution    | Buy        |
| ESLint     | Linting with ecosystem plugins; infeasible to replicate                | Buy        |
| Prettier   | Deterministic formatting; agent-generated formatter would diverge      | Buy        |

---

## Antipatterns (TypeScript/Web-Specific)

- **Split test runners.** Running some TS suites in Vitest and others in standalone Playwright/Jest/Mocha. This fragments setup and lifecycle logic. TS suites must be driven by Vitest.
- **Infra setup outside Bun runtime.** Starting databases or servers manually and hoping tests discover them. Infra must be created and cleaned by Bun-side Vitest setup so each suite is self-contained.
- **Fixture data in env vars.** Putting replay payloads or expected responses in `.env` values. Fixtures must be committed file artifacts.
- **Local/CI command drift.** Running a suite with one command locally and a different command in CI.
- **JSDOM as a browser.** Running component tests in JSDOM or Happy DOM because they are faster than headless Chromium. These are DOM simulations, not browsers. They lack layout, rendering, real event dispatch, and network behavior. A component that passes in JSDOM and fails in Chromium is a component that fails in production.
