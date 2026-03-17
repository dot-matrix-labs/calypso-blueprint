# Task Queue & Worker Service Architecture Blueprint

## Scope

This blueprint defines the security-first architecture for a PostgreSQL-backed task queue and narrowly scoped Rust worker services. It covers:

- Queue schema and job lifecycle
- Worker lifecycle and concurrency model
- Trust boundaries and permission model
- API gateway responsibilities for all mutations
- Failure, retry, and dead-letter handling
- Operational safeguards

This blueprint implements the constraints defined in the WORKER domain blueprint and IMPL-WORKER-RS implementation rules. It provides the concrete schema, Rust implementation patterns, and operational procedures for an async (Tokio-based), minimal-dependency task processing system.

Out of scope: vendor CLI integration details (covered by WORKER-D-004), digital twin execution (covered by WORKER-D-006), and ledger transaction signing (covered by ledger-blueprint.md).

---

## User Stories

These user stories define the workloads this architecture must support today and the workloads it must not preclude in the future.

### Primary: AI Agent CLI Orchestration

> As a platform operator, I want workers to spawn and babysit long-running AI CLI processes
> (claude-code, codex, gemini-cli) so that tasks like code review, code generation, and
> analysis can run concurrently within a single worker replica without blocking the claim loop.

This is the dominant workload. A worker claims a task, spawns a vendor CLI as a child process, waits for it to complete (seconds to minutes), captures structured output, and submits the result via the API gateway. The worker must be able to supervise multiple in-flight CLI processes concurrently — a synchronous, single-threaded loop would leave one replica idle for the entire duration of each subprocess, requiring N replicas for N concurrent tasks. Async I/O with `tokio::process::Command` allows a single replica to babysit multiple subprocesses while remaining responsive to new claims and shutdown signals.

### Primary: API-Mediated Task Execution

> As a platform operator, I want workers to respond to tasks by making authenticated HTTP calls
> to external APIs (AI vendor APIs, internal microservices) so that the platform can orchestrate
> multi-step workflows where each step is an API call with structured input/output.

Workers read task payloads containing opaque resource IDs, fetch business data through the API gateway's read endpoints, call external vendor APIs, and submit structured results back through the API gateway. All I/O is network-bound. Multiple concurrent tasks each spending time waiting on HTTP responses is textbook async I/O.

### Secondary: Batch and Analytical Workloads

> As a data team member, I want to enqueue analytical tasks (summarization, classification,
> embedding generation) that process batches of records by reference, so that analytical
> workloads flow through the same audited, access-controlled pipeline as interactive tasks.

These tasks read batches of resource IDs from the payload, fetch data through read endpoints, call vendor APIs for each item, and submit aggregated results. They are I/O-bound with higher fan-out than interactive tasks.

### Future: Streaming and Incremental Results

> As a user watching a long-running code generation task, I want to see incremental progress
> (streaming CLI output, partial results) so that I have visibility into task execution
> without waiting for full completion.

A synchronous worker cannot stream incremental results while executing — it blocks on the subprocess. An async worker can multiplex subprocess output monitoring with WebSocket or SSE delivery to the API gateway. This user story does not require implementation today but the async foundation must not preclude it.

### Future: CPU/GPU Inference

> As a platform architect, I want the task queue model to support a future where some agent
> types run local inference (CPU or GPU) rather than calling external vendor APIs, so that
> the security model, queue schema, audit trail, and API-mediated write path remain unchanged
> regardless of whether the "AI work" happens locally or remotely.

This workload is compute-bound rather than I/O-bound. It does not change the architecture:
- The task queue, claim flow, delegated tokens, and API-mediated writes are workload-agnostic
- A CPU/GPU inference worker would claim tasks identically, execute inference locally instead of spawning a CLI, and submit results through the same API path
- The worker binary would link an inference runtime (e.g., `llama.cpp` via FFI, `candle`, or `burn`) but the security constraints are unchanged: SELECT-only DB access, writes through API, audit on every execution
- Compute-bound workers would likely run one task at a time (inference saturates CPU/GPU), making concurrency configuration per-agent-type rather than global
- GPU scheduling and resource limits would be handled at the Kubernetes level (resource requests, node affinity, device plugins), not in the worker binary

This user story is explicitly distant-future. The architecture must not preclude it, but no design decisions should be made to optimize for it today.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  TRUST BOUNDARY: Application Perimeter                                      │
│                                                                             │
│  ┌──────────────┐         ┌──────────────────────────────┐                  │
│  │  User Client  │────────▶│  API Gateway (Axum)          │                  │
│  │  (browser,    │  HTTPS  │                              │                  │
│  │   CLI, SDK)   │◀────────│  - Auth / session middleware  │                  │
│  └──────────────┘         │  - Task creation endpoint     │                  │
│                            │  - Task claim endpoint        │                  │
│                            │  - Result submission endpoint │                  │
│                            │  - Audit logging endpoint     │                  │
│                            │  - Business rule validation   │                  │
│                            └──────────┬───────────────────┘                  │
│                                       │                                      │
│            TRUST BOUNDARY: DB Write   │  Full read/write                     │
│            ─────────────────────────  │  (api_service role)                  │
│                                       ▼                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  PostgreSQL                                                         │    │
│  │                                                                     │    │
│  │  ┌─────────────────────┐   ┌──────────────────────────────────┐    │    │
│  │  │  task_queue table    │   │  task_queue_view_<agent_type>    │    │    │
│  │  │  (API writes only)   │   │  (per-type filtered, SELECT-only)│    │    │
│  │  └─────────────────────┘   └──────────────┬───────────────────┘    │    │
│  │                                            │                        │    │
│  │  ┌──────────────────────────────────────┐  │                        │    │
│  │  │  task_audit_log table                │  │                        │    │
│  │  │  (API writes only, append-only)       │  │                        │    │
│  │  └──────────────────────────────────────┘  │                        │    │
│  └────────────────────────────────────────────┼────────────────────────┘    │
│                                               │                             │
│            TRUST BOUNDARY: Worker Isolation    │  SELECT only                │
│            ─────────────────────────────────── │  (agent_<type> role)        │
│                                               ▼                             │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │  Worker Pod (per agent type)                                       │     │
│  │                                                                    │     │
│  │  ┌──────────────────────────┐                                      │     │
│  │  │  worker binary           │──── SELECT ──▶ task_queue_view       │     │
│  │  │  (statically linked,     │                                      │     │
│  │  │   distroless container)  │──── HTTPS ───▶ API Gateway           │     │
│  │  │                          │     (claim, submit result, audit)     │     │
│  │  └──────────────────────────┘                                      │     │
│  │                                                                    │     │
│  │  Network policy:                                                   │     │
│  │    ✓ API Gateway (HTTPS)                                           │     │
│  │    ✓ PostgreSQL (SELECT-only via role)                              │     │
│  │    ✓ Declared vendor API hosts                                     │     │
│  │    ✗ All other egress blocked                                      │     │
│  └────────────────────────────────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Trust Boundaries

There are three discrete trust zones. Crossing a boundary requires authentication and authorization.

### Zone 1: API Gateway (Full Trust)

- Runs as PostgreSQL role `api_service` with full read/write on business tables
- Validates all inputs, enforces business rules, checks authorization
- Issues and validates delegated tokens
- Writes audit log entries
- The **only** component that can mutate the task queue or business data

### Zone 2: PostgreSQL (Enforcement Layer)

- Enforces role-based access at the database level
- `api_service` role: full CRUD on task_queue, task_audit_log, business tables
- `agent_<type>` roles: SELECT-only on `task_queue_view_<type>`
- Row-level security ensures agent roles only see their own task types
- INSERT/UPDATE/DELETE from an agent role produces a PostgreSQL permission error

### Zone 3: Worker Pods (Least Privilege)

- No direct access to business tables — structurally unreachable
- SELECT-only on a filtered view of pending tasks for their type
- All mutations submitted via authenticated HTTPS to the API gateway
- No shell, no package manager, no runtime binary installation
- Network egress restricted to API gateway + declared vendor hosts

---

## Permission Model

### PostgreSQL Roles

```sql
-- API service role: full access (used only by API gateway)
CREATE ROLE api_service WITH LOGIN PASSWORD '...';
GRANT ALL ON task_queue, task_audit_log TO api_service;
-- (plus business table grants as needed)

-- Per-agent-type role: SELECT-only on filtered view
CREATE ROLE agent_coding WITH LOGIN PASSWORD '...';
GRANT SELECT ON task_queue_view_coding TO agent_coding;
-- No grants on any other table. Period.

CREATE ROLE agent_analysis WITH LOGIN PASSWORD '...';
GRANT SELECT ON task_queue_view_analysis TO agent_analysis;
```

### Row-Level Security

```sql
ALTER TABLE task_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY agent_coding_read ON task_queue
    FOR SELECT
    TO agent_coding
    USING (agent_type = 'coding' AND status IN ('pending', 'claimed'));

CREATE POLICY agent_analysis_read ON task_queue
    FOR SELECT
    TO agent_analysis
    USING (agent_type = 'analysis' AND status IN ('pending', 'claimed'));
```

### Delegated Token Scoping

Each task carries a single-use capability token with these claims:

| Claim | Purpose |
|-------|---------|
| `task_id` | Binds token to exactly one task |
| `user_id` | The principal whose authority the write executes under |
| `agent_type` | Must match the claiming worker's type |
| `allowed_endpoints` | Explicit list of API paths this token may call |
| `exp` | Short TTL (minutes, not hours) |
| `jti` | Unique token ID for single-use enforcement |

The API gateway rejects any token where:
- `task_id` does not match the request path
- `agent_type` does not match the authenticated worker
- `jti` has already been consumed (stored in a consumed-tokens set with TTL-based eviction)
- `exp` has passed

---

## Queue Schema

### task_queue table

```sql
CREATE TABLE task_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key TEXT UNIQUE NOT NULL,

    -- Routing
    agent_type      TEXT NOT NULL,       -- e.g. 'coding', 'analysis'
    job_type        TEXT NOT NULL,       -- e.g. 'code_review', 'summarize'

    -- Status lifecycle
    status          TEXT NOT NULL DEFAULT 'pending'
                    CHECK (status IN (
                        'pending',
                        'claimed',
                        'running',
                        'submitting',
                        'completed',
                        'failed',
                        'dead'
                    )),

    -- Payload: opaque references only, never business data
    payload         JSONB NOT NULL,      -- {"resource_id": "...", "action": "..."}

    -- Attribution
    created_by      UUID NOT NULL,       -- user who created the task
    correlation_id  UUID NOT NULL,       -- traces task through system
    claimed_by      TEXT,                -- worker instance identity
    claimed_at      TIMESTAMPTZ,

    -- Delegated credential
    delegated_token TEXT,                -- single-use capability token

    -- Result
    result          JSONB,               -- structured result submitted via API
    completed_at    TIMESTAMPTZ,
    error_message   TEXT,

    -- Retry
    attempt         INT NOT NULL DEFAULT 0,
    max_attempts    INT NOT NULL DEFAULT 3,
    next_retry_at   TIMESTAMPTZ,

    -- Timeout
    claim_expires_at TIMESTAMPTZ,        -- stale claim recovery deadline

    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    -- Priority (lower = higher priority)
    priority        INT NOT NULL DEFAULT 100
);

-- Index for worker polling: find claimable tasks efficiently
CREATE INDEX idx_task_queue_poll
    ON task_queue (agent_type, status, priority, created_at)
    WHERE status = 'pending';

-- Index for stale claim recovery
CREATE INDEX idx_task_queue_stale_claims
    ON task_queue (status, claim_expires_at)
    WHERE status = 'claimed';

-- Index for idempotency lookups
CREATE INDEX idx_task_queue_idempotency
    ON task_queue (idempotency_key);

-- Notify workers on new task insertion
CREATE OR REPLACE FUNCTION notify_task_inserted()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('task_queue_' || NEW.agent_type, NEW.id::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER task_queue_notify
    AFTER INSERT ON task_queue
    FOR EACH ROW
    EXECUTE FUNCTION notify_task_inserted();
```

### Per-Agent-Type Views

```sql
CREATE VIEW task_queue_view_coding AS
    SELECT id, job_type, status, payload, correlation_id,
           priority, created_at, attempt, max_attempts
    FROM task_queue
    WHERE agent_type = 'coding'
      AND status IN ('pending', 'claimed');

-- Note: delegated_token, created_by, result, and error_message
-- are NOT exposed in the view. Workers receive tokens only
-- through the claim API response.
```

### task_audit_log table

```sql
CREATE TABLE task_audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_id         UUID NOT NULL REFERENCES task_queue(id),
    correlation_id  UUID NOT NULL,

    -- Who
    actor_type      TEXT NOT NULL,       -- 'user', 'worker', 'system'
    actor_id        TEXT NOT NULL,       -- user UUID or worker instance ID
    agent_type      TEXT,                -- null for user/system actions

    -- What
    operation       TEXT NOT NULL,       -- 'created', 'claimed', 'executed',
                                         -- 'submitted', 'completed', 'failed',
                                         -- 'retried', 'dead_lettered'
    -- Hashes, not content
    input_hash      TEXT,                -- SHA-256 of input payload
    output_hash     TEXT,                -- SHA-256 of output payload

    -- Context
    token_jti       TEXT,                -- which delegated token was used
    metadata        JSONB,               -- operation-specific structured data

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Append-only: no UPDATE or DELETE grants to any role
-- Only api_service has INSERT

CREATE INDEX idx_audit_log_task
    ON task_audit_log (task_id, created_at);

CREATE INDEX idx_audit_log_correlation
    ON task_audit_log (correlation_id, created_at);
```

---

## Worker Lifecycle

### Startup

```
1. Read configuration from environment:
   - AGENT_TYPE (e.g., "coding")
   - DATABASE_URL (points to agent_<type> role credentials)
   - API_GATEWAY_URL
   - WORKER_INSTANCE_ID (unique per replica, set by deployment)
   - CLAIM_TIMEOUT_SECONDS
   - POLL_INTERVAL_SECONDS
   - MAX_CONCURRENT_TASKS (default: 4, upper bound per replica)

2. Initialize Tokio runtime (multi-thread, default thread count).

3. Open tokio-postgres connection pool (SELECT-only role).
   - Verify SELECT-only access: attempt INSERT → expect permission error
   - If INSERT succeeds: PANIC. Role misconfigured. Do not proceed.

4. Open reqwest::Client (connection-pooled, reused across tasks).

5. LISTEN on channel 'task_queue_<agent_type>' for notifications
   (tokio-postgres async notification stream).

6. Enter main loop.
```

### Main Loop (Async, Bounded Concurrency)

The worker runs a claim loop that feeds tasks into a bounded task set. Each claimed
task executes as an independent Tokio task. A semaphore limits concurrency to
`MAX_CONCURRENT_TASKS` — the worker never claims more work than it can supervise.

```
// Semaphore bounds in-flight task count
let sem = Arc::new(Semaphore::new(max_concurrent_tasks));
let mut task_set = JoinSet::new();

loop {
    tokio::select! {
        // Branch 1: Acquire permit and poll for new work
        permit = sem.clone().acquire_owned() => {
            let permit = permit.unwrap();

            // Poll for pending tasks
            let rows = sqlx_query(
                "SELECT id, job_type, payload, correlation_id, priority
                 FROM task_queue_view_{type}
                 WHERE status = 'pending'
                 ORDER BY priority ASC, created_at ASC
                 LIMIT 1"
            ).await;

            if rows.is_empty() {
                drop(permit);  // Release permit, nothing to do
                // Wait for LISTEN/NOTIFY or poll_interval timeout
                wait_for_notification_or_timeout(poll_interval).await;
                continue;
            }

            let task = rows[0].clone();

            // Claim via API (NOT via direct DB write)
            let claim_response = http_client.post(
                format!("{api_url}/tasks/{}/claim", task.id)
            )
            .header("Authorization", format!("Bearer {}", worker_service_token))
            .header("X-Worker-Instance", &worker_instance_id)
            .header("X-Correlation-Id", task.correlation_id)
            .send().await;

            match claim_response.status() {
                409 => { drop(permit); continue; }  // Already claimed
                200 => { /* proceed */ }
                _   => { drop(permit); log_error(...); backoff().await; continue; }
            }

            let delegated_token = claim_response.json().delegated_token;

            // Spawn task execution as independent Tokio task
            task_set.spawn(async move {
                // Execute task (may spawn CLI subprocess, call vendor APIs, etc.)
                let result = execute_job(task.job_type, task.payload).await;

                // Submit result via API
                let submit = http_client.post(
                    format!("{api_url}/tasks/{}/result", task.id)
                )
                .header("Authorization", format!("Bearer {}", delegated_token))
                .header("X-Worker-Instance", &worker_instance_id)
                .header("X-Correlation-Id", task.correlation_id)
                .header("X-Idempotency-Key", format!("{}:{}", task.id, task.attempt))
                .json(&result)
                .send().await;

                if submit.status() != 200 {
                    log_error("submit failed", task.id);
                    // Task will be retried via stale claim recovery
                }

                drop(permit);  // Release semaphore slot
            });
        }

        // Branch 2: Reap completed tasks from JoinSet
        Some(completed) = task_set.join_next() => {
            if let Err(e) = completed {
                log_error("task panicked", e);
                // Semaphore permit was dropped on panic — slot is freed
                // Task will be recovered via stale claim expiry
            }
        }

        // Branch 3: Shutdown signal
        _ = tokio::signal::ctrl_c() => {
            break;
        }
    }
}
```

### Subprocess Execution (CLI Agents)

The primary execution path spawns a vendor CLI binary as an async child process:

```rust
async fn execute_cli_task(job_type: &str, payload: &TaskPayload) -> TaskResult {
    // tokio::process::Command — array form, no shell interpolation
    let mut child = tokio::process::Command::new("/usr/local/bin/claude-code")
        .arg("--print")
        .arg("--output-format").arg("json")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("vendor CLI binary missing from container image");

    // Feed input via stdin (no shell interpolation possible)
    child.stdin.take().unwrap().write_all(input_bytes).await?;

    // Await completion — this yields to the Tokio executor,
    // allowing other tasks to run while this subprocess executes
    let output = child.wait_with_output().await?;

    // Parse structured output
    TaskResult::from_cli_output(&output.stdout, &output.stderr)
}
```

While this subprocess runs (potentially minutes), the Tokio executor is free to:
- Poll for and claim additional tasks (up to `MAX_CONCURRENT_TASKS`)
- Submit results from other completed tasks
- Respond to shutdown signals
- Process LISTEN/NOTIFY events

### Graceful Shutdown

```
On SIGTERM / SIGINT (via tokio::signal):
  1. Stop claiming new tasks (exit the claim loop)
  2. Wait for in-flight tasks to complete (with bounded timeout)
     - Each task in the JoinSet gets a grace period
  3. For tasks that cannot complete within timeout:
     - Kill child processes (child.kill())
     - Do NOT submit partial results
     - Tasks will be recovered via stale claim expiry
  4. Close database connections and HTTP client
  5. Exit 0
```

---

## API Gateway Responsibilities

The API gateway is the **sole write surface** for the task queue and all business data. Every endpoint below validates authentication, authorization, and business rules before any mutation.

### POST /tasks — Create Task

**Called by:** Authenticated user (or system on behalf of user)

1. Validate request body (job_type, agent_type, payload references)
2. Verify caller is authorized to create tasks of this type
3. Verify `idempotency_key` is unique (return existing task if duplicate)
4. Validate payload contains only opaque references (IDs), not business data
5. Generate single-use delegated token (not yet returned — returned on claim)
6. INSERT into `task_queue` with status `pending`
7. INSERT audit log entry: operation `created`
8. Return task ID and status

### POST /tasks/{id}/claim — Claim Task

**Called by:** Worker (authenticated with worker service token)

1. Verify worker service token and extract `agent_type`
2. Verify task's `agent_type` matches worker's `agent_type`
3. Execute atomic claim:
   ```sql
   UPDATE task_queue
   SET status = 'claimed',
       claimed_by = $worker_instance_id,
       claimed_at = now(),
       claim_expires_at = now() + interval '$claim_timeout seconds',
       attempt = attempt + 1,
       updated_at = now()
   WHERE id = $task_id
     AND status = 'pending'
   RETURNING *;
   ```
4. If zero rows updated: return `409 Conflict` (already claimed or not pending)
5. Return task details + delegated token in response body
6. INSERT audit log entry: operation `claimed`

### POST /tasks/{id}/result — Submit Result

**Called by:** Worker (authenticated with single-use delegated token)

1. Validate delegated token:
   - `task_id` matches path
   - `jti` not in consumed-tokens set
   - `exp` not passed
   - `agent_type` matches worker's identity
2. Mark `jti` as consumed (INSERT into consumed tokens table or in-memory set with TTL)
3. Validate result structure
4. Execute business-side mutations on behalf of `user_id` from token:
   - Same authorization checks as if the user submitted directly
   - Same schema validation
   - Same business rule enforcement
5. UPDATE task_queue: status `completed`, result, completed_at
6. INSERT audit log entries: operation `submitted`, operation `completed`
7. Return confirmation

### Stale Claim Recovery (Scheduled)

**Called by:** System timer (cron or pg_cron)

```sql
UPDATE task_queue
SET status = CASE
        WHEN attempt >= max_attempts THEN 'dead'
        ELSE 'pending'
    END,
    claimed_by = NULL,
    claimed_at = NULL,
    claim_expires_at = NULL,
    next_retry_at = CASE
        WHEN attempt >= max_attempts THEN NULL
        ELSE now() + (interval '1 second' * power(2, attempt))
    END,
    updated_at = now()
WHERE status = 'claimed'
  AND claim_expires_at < now()
RETURNING id, status;
```

INSERT audit log entry for each recovered task: operation `retried` or `dead_lettered`.

---

## Job Lifecycle Example

### Scenario: User requests a code review

```
Time  Actor         Action
────  ────────────  ──────────────────────────────────────────────────────

T0    User          POST /tasks
                    {
                      "agent_type": "coding",
                      "job_type": "code_review",
                      "idempotency_key": "pr-42-review-v1",
                      "payload": {
                        "pull_request_id": "pr_42",
                        "repository_id": "repo_7"
                      }
                    }

T1    API Gateway   Validates user auth, checks user can request reviews
                    Generates delegated token (task-scoped, single-use)
                    INSERT task_queue (status: pending)
                    INSERT audit_log (operation: created)
                    pg_notify('task_queue_coding', task_id)
                    Returns: { "task_id": "abc-123", "status": "pending" }

T2    Worker        Receives notification on 'task_queue_coding' channel
                    SELECT from task_queue_view_coding → sees task abc-123
                    POST /tasks/abc-123/claim
                    (with worker service token + worker instance ID)

T3    API Gateway   Validates worker identity and agent_type match
                    Atomic UPDATE ... WHERE status = 'pending'
                    Returns: { task details + delegated_token }
                    INSERT audit_log (operation: claimed)

T4    Worker        Executes code review:
                    - Reads PR data via API: GET /pull-requests/pr_42
                      (using worker service token, read-only)
                    - Calls vendor AI API with PR diff
                    - Structures review output

T5    Worker        POST /tasks/abc-123/result
                    Authorization: Bearer <delegated_token>
                    {
                      "status": "success",
                      "output": {
                        "review_comment_ids": ["comment_1", "comment_2"],
                        "summary": "..."
                      }
                    }

T6    API Gateway   Validates delegated token:
                    - task_id matches ✓
                    - jti not consumed ✓
                    - not expired ✓
                    - agent_type matches ✓
                    Marks jti as consumed
                    Executes business mutation ON BEHALF OF original user:
                    - Creates review comments (same auth checks as user)
                    UPDATE task_queue: status → completed
                    INSERT audit_log (operation: submitted)
                    INSERT audit_log (operation: completed)

T7    User          Sees review comments on PR, attributed to them
                    Audit trail shows: user authorized, worker executed
```

---

## Failure & Retry Model

### Failure Modes

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Worker crashes after claim | `claim_expires_at` passes | Stale claim recovery resets to `pending` |
| Worker crashes before claim | No side effects | Task remains `pending`, another worker claims |
| API gateway rejects result | HTTP 4xx/5xx | Worker logs error; task recovered via stale claim expiry |
| Delegated token expired | HTTP 401 | Task recovered via stale claim expiry with new token |
| Delegated token already consumed | HTTP 403 | Result was already submitted; worker treats as success |
| Business rule violation | HTTP 422 | Task marked `failed`; no retry (business error, not transient) |
| Vendor API timeout | Worker-side timeout | Worker submits error result; task may be retried |
| Database connection lost | Connection error | Worker reconnects with backoff; uncompleted claim expires |

### Retry Strategy

- **Exponential backoff**: `next_retry_at = now() + 2^attempt seconds`
- **Max attempts**: configurable per job type (default: 3)
- **Dead letter**: after `max_attempts`, status → `dead`
- **No retry on business errors**: if the API returns 422, the task is `failed` immediately (retrying won't fix a business rule violation)
- **Idempotency keys**: prevent duplicate task creation and duplicate result submission

### Dead Letter Handling

Tasks in `dead` status:
- Remain in the queue table for inspection (never deleted)
- Are visible to operators via admin API
- Require manual intervention: either fix and re-enqueue, or acknowledge
- Trigger alerting (metric: `task_queue_dead_total` by agent_type and job_type)

---

## Operational Safeguards

### Startup Verification

Every worker verifies its security posture on startup before entering the main loop:

```rust
// Verify SELECT-only access — if this succeeds, the role is misconfigured
let probe = client.execute(
    "INSERT INTO task_queue (id) VALUES (gen_random_uuid())",
    &[],
).await;
match probe {
    Ok(_) => panic!("FATAL: worker role has INSERT access to task_queue"),
    Err(e) if is_permission_denied(&e) => { /* expected */ },
    Err(e) => panic!("FATAL: unexpected error during role verification: {}", e),
}
```

### Health Checks

| Check | Frequency | Action on failure |
|-------|-----------|-------------------|
| DB connection alive | Every poll cycle | Reconnect with backoff |
| API gateway reachable | Every claim/submit | Log, backoff, retry |
| Role still SELECT-only | Startup only | Panic if write succeeds |
| Stale claims exist | Scheduled (60s) | System recovers automatically |
| Dead letter queue depth | Continuous metric | Alert if > threshold |

### Metrics (exposed via /metrics or structured logs)

```
task_queue_pending_total{agent_type, job_type}
task_queue_claimed_total{agent_type, job_type}
task_queue_completed_total{agent_type, job_type}
task_queue_failed_total{agent_type, job_type}
task_queue_dead_total{agent_type, job_type}
task_claim_duration_seconds{agent_type}
task_execution_duration_seconds{agent_type, job_type}
task_submit_duration_seconds{agent_type}
task_retry_total{agent_type, job_type}
worker_poll_empty_total{agent_type}
worker_inflight_tasks{agent_type}           # current semaphore usage
worker_max_concurrent_tasks{agent_type}     # semaphore capacity
worker_subprocess_duration_seconds{agent_type, job_type, binary}
```

### Concurrency Safety

- **Claim atomicity**: `UPDATE ... WHERE status = 'pending' RETURNING` guarantees exactly one winner
- **No double-execution**: a claimed task is invisible to other workers (RLS + status filter)
- **No lost tasks**: stale claim recovery returns uncompleted claims to `pending`
- **No duplicate results**: delegated token `jti` single-use enforcement + idempotency keys

---

## Rust Implementation Rules

### Crate Dependencies (Minimal)

```toml
[dependencies]
tokio = { version = "1", features = ["full"] }
tokio-postgres = "0.7"     # Async PostgreSQL client with LISTEN/NOTIFY
reqwest = { version = "0.12", features = ["json"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
uuid = { version = "1", features = ["v4"] }
sha2 = "0.10"               # For input/output hashing in audit entries
tracing = "0.1"
tracing-subscriber = "0.3"
```

### Why async (Tokio)

The dominant workload is **spawning CLI subprocesses that run for seconds to minutes**.
A synchronous worker blocks its entire OS thread (and its entire replica) while waiting
for a subprocess to finish. This means N concurrent tasks require N replicas, each with
its own memory footprint, database connection, and Kubernetes pod overhead.

Async I/O solves this without complexity disproportionate to the benefit:

- **`tokio::process::Command`** makes subprocess waiting non-blocking — one replica
  can babysit 4+ CLI processes concurrently, yielding while each runs
- **`tokio-postgres`** provides native async LISTEN/NOTIFY — no polling thread needed
- **`reqwest`** provides connection-pooled async HTTP — claim and submit calls don't
  block the executor while waiting for the API gateway
- **`tokio::select!`** cleanly multiplexes claim polling, task completion reaping,
  and shutdown signal handling in a single loop
- **`JoinSet` + `Semaphore`** provide bounded concurrency with clear resource accounting
- **`tokio::signal`** handles graceful shutdown without custom signal infrastructure

The complexity cost is real but contained:
- All task-level state is owned by the spawned future (no shared mutable state)
- The semaphore makes concurrency limits explicit and auditable
- Send/Sync bounds are satisfied naturally since task futures own their data
- The worker crate has no shared mutable state beyond the semaphore and shutdown flag

Horizontal scaling (more replicas) remains available for throughput beyond what
bounded concurrency provides. Async and horizontal scaling are complementary, not
alternatives — async reduces per-replica waste, replicas increase total capacity.

This aligns with IMPL-WORKER-RS-002 (tokio-task-loop) from the existing rules.

### Code structure

```
crates/worker/
├── src/
│   ├── main.rs          # #[tokio::main], config, claim loop, JoinSet
│   ├── config.rs        # Environment variable parsing
│   ├── queue.rs         # tokio-postgres polling and LISTEN/NOTIFY stream
│   ├── api_client.rs    # reqwest client for claim/submit/audit
│   ├── subprocess.rs    # tokio::process::Command wrapper (array-form only)
│   ├── handlers/        # One module per job_type
│   │   ├── mod.rs
│   │   └── code_review.rs
│   └── types.rs         # Shared structs (Task, ClaimResponse, etc.)
└── Cargo.toml
```

### Explicit SQL — no ORM, no query builder

```rust
// Polling for tasks (tokio-postgres, async)
const POLL_QUERY: &str = "
    SELECT id, job_type, payload, correlation_id, priority
    FROM task_queue_view_coding
    WHERE status = 'pending'
    ORDER BY priority ASC, created_at ASC
    LIMIT 1
";

let rows = client.query(POLL_QUERY, &[]).await?;

// The worker NEVER writes SQL that mutates. All mutations go through api_client.
// There are no INSERT, UPDATE, or DELETE strings anywhere in the worker crate.
```

### Compile-time enforcement

The `crates/worker` Cargo.toml must NOT depend on `crates/db` (the write layer). If a developer adds that dependency, the Cargo workspace dependency graph check in CI fails. The worker binary physically cannot call database write functions because the code is not linked.

---

## Adding a New Agent Type

Adding a new agent type is an architectural decision requiring:

1. **Database migration**: new role, new view, new RLS policy
2. **API gateway update**: register new agent_type in claim/result validation
3. **Worker binary**: new handler module in `crates/worker/src/handlers/`
4. **Kubernetes manifest**: new Deployment, Secret (DB credentials + vendor keys), NetworkPolicy
5. **CI update**: build and push new container image
6. **Monitoring**: new dashboard panel, alerting thresholds

This is intentionally not self-service. Each new agent type expands the attack surface and operational burden. It requires code review and explicit approval.

---

## Rule Traceability

This blueprint implements or refines the following rules:

| Rule | Name | Relationship |
|------|------|-------------|
| WORKER-P-001 | read-only-database-access | Queue schema enforces SELECT-only agent roles |
| WORKER-P-002 | writes-through-authenticated-api | All mutations go through API gateway |
| WORKER-P-006 | single-use-task-scoped-tokens | Delegated token model defined here |
| WORKER-P-008 | agent-type-isolation | Per-type roles, views, and RLS policies |
| WORKER-D-001 | task-queue-read-only-view | View schema defined here |
| WORKER-D-002 | delegated-user-token | Token lifecycle defined here |
| WORKER-D-005 | structured-execution-audit-log | Audit log schema defined here |
| WORKER-D-007 | per-agent-type-database-role | Role creation and grants defined here |
| IMPL-WORKER-RS-002 | tokio-task-loop | Implemented: async Tokio loop with bounded concurrency |
| IMPL-WORKER-RS-003 | select-only-db-role | Startup verification implemented |
| IMPL-WORKER-RS-004 | writes-through-reqwest-api | Implemented: reqwest async HTTP client |
| IMPL-WORKER-RS-005 | delegated-token-submission | Token flow defined here |
| IMPL-WORKER-RS-006 | command-array-spawn | Implemented: tokio::process::Command array form |
| IMPL-WORKER-RS-007 | structured-execution-audit | Audit schema and flow defined here |
| IMPL-WORKER-RS-011 | anti-direct-db-writes | Cargo dependency graph enforcement |
