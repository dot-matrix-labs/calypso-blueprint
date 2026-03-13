# PostgreSQL Ledger Blueprint

## Scope

This blueprint defines a core ledger subsystem on PostgreSQL with:

- cryptographically signed transactions from humans or AI agents
- append-only ledger storage
- deterministic transaction validation and state application
- rollback by signed compensating transactions
- auditability from ledger genesis to current state
- sandbox-friendly replay checkpoints for fast digital twin simulation

Out of scope: APIs, streaming, sharding, managed-service operations, and non-core product workflows.

## Design Goals

1. Never mutate or delete accepted ledger transactions.
2. Make acceptance deterministic: the same ordered ledger must yield the same state.
3. Separate immutable facts (ledger) from derived materialized state.
4. Make tampering evident with signatures, canonical payload hashing, and hash chaining.
5. Support rollback only through explicit, signed compensating transactions.
6. Preserve authority, execution provenance, and platform acceptance as separate facts for consequential operations.

## Core Model

The system has two storage layers:

- `ledger_transactions`: immutable source of truth
- `ledger_state_accounts`: current materialized account state derived from accepted transactions

Optional helper tables improve auditability and key control:

- `ledger_actor_keys`: actor public keys and key lifecycle
- `ledger_state_versions`: point-in-time state snapshots per accepted transaction
- `ledger_replay_checkpoints`: reusable replay checkpoints for fast digital twin materialization

## Transaction Format

Use a canonical JSON payload and sign the canonical bytes. Prefer Ed25519 for simplicity, deterministic signatures, and fast verification. Support secp256k1 only if compatibility with an existing wallet ecosystem is required.

For consequential enterprise operations, the production ledger should use dual attribution:

- `principal_actor_*`: who had authority for the action
- `executing_actor_*`: which agent, worker, or user client assembled and submitted it
- `validator_*`: which platform validator accepted it

The envelope below is the minimal shape. Enterprise deployments should extend it with explicit principal and executor fields rather than collapsing both into a single actor identity.

### Envelope

```json
{
  "transaction_id": "01JNWQ0M7M5X4FJ7NZM3YVYVPS",
  "transaction_type": "transfer",
  "actor_id": "user_123",
  "actor_kind": "human",
  "actor_key_id": "key_2026_01",
  "submitted_at": "2026-03-12T14:32:01.123Z",
  "payload": {
    "from_account_id": "acct_ops",
    "to_account_id": "acct_vendor",
    "asset_code": "USD",
    "amount_minor": 250000,
    "nonce": 48,
    "memo": "invoice_8841"
  },
  "previous_hash": "base64url(prev_ledger_hash)",
  "payload_hash": "base64url(sha256(canonical_payload))",
  "signature": "base64url(ed25519_signature)"
}
```

### Canonical Signing Input

Sign this exact byte sequence:

```text
transaction_id || transaction_type || actor_id || actor_kind || actor_key_id || submitted_at || previous_hash || payload_hash
```

Rules:

- `payload` must be canonicalized before hashing, for example RFC 8785 JSON Canonicalization Scheme.
- Timestamps must be RFC 3339 UTC with millisecond precision.
- `transaction_id` must be client-generated and globally unique. ULID works well because it preserves order for audit views while remaining unique.
- `nonce` must be monotonic per actor or per account authority to prevent replay.

## Key Management

### Humans

- Store private keys in hardware-backed keystores where possible.
- Associate each active signing key with a stable `actor_id`.
- Rotate by inserting a new active public key record; never overwrite historical keys.

### AI Agents

- Give each agent its own `actor_id` and scoped signing key.
- Keep agent private keys in a KMS/HSM-backed signing service; do not expose raw private key material to the model runtime.
- Bind each agent key to explicit authority scopes such as allowed transaction types, allowed accounts, and spending caps.

### Shared Rules

- Verification uses only registered public keys from `ledger_actor_keys`.
- Key revocation blocks new transactions but does not invalidate already accepted historical entries.
- Include `valid_from` and `valid_to` windows so verification is done against the key that was valid at `submitted_at`.
- Pin the accepted signature algorithm per ledger deployment or ledger domain; do not negotiate algorithms per request.

## PostgreSQL Schema

### Immutable Ledger Table

```sql
create table ledger_actor_keys (
  key_id text primary key,
  actor_id text not null,
  actor_kind text not null check (actor_kind in ('human', 'ai', 'system')),
  algorithm text not null check (algorithm in ('ed25519', 'secp256k1')),
  public_key bytea not null,
  scope jsonb not null default '{}'::jsonb,
  valid_from timestamptz not null,
  valid_to timestamptz,
  revoked_at timestamptz,
  created_at timestamptz not null default now()
);

create table ledger_transactions (
  ledger_seq bigserial primary key,
  transaction_id text not null unique,
  transaction_type text not null,
  actor_id text not null,
  actor_kind text not null check (actor_kind in ('human', 'ai', 'system')),
  actor_key_id text not null references ledger_actor_keys(key_id),
  submitted_at timestamptz not null,
  recorded_at timestamptz not null default now(),
  payload jsonb not null,
  payload_canonical bytea not null,
  payload_hash bytea not null,
  previous_hash bytea,
  ledger_hash bytea not null,
  signature bytea not null,
  signature_algorithm text not null check (signature_algorithm in ('ed25519', 'secp256k1')),
  status text not null check (status in ('accepted', 'rejected')) default 'accepted',
  rejection_reason text,
  rollback_of_transaction_id text references ledger_transactions(transaction_id),
  constraint ledger_previous_hash_required
    check ((ledger_seq = 1 and previous_hash is null) or ledger_seq > 1)
);

create unique index ledger_transactions_one_rollback_per_target
  on ledger_transactions (rollback_of_transaction_id)
  where rollback_of_transaction_id is not null and status = 'accepted';

create index ledger_transactions_actor_idx
  on ledger_transactions (actor_id, submitted_at);

create index ledger_transactions_type_idx
  on ledger_transactions (transaction_type, submitted_at);
```

Notes:

- `payload_canonical` stores the exact signed bytes used to derive `payload_hash`.
- `ledger_hash` is the tamper-evident chain hash for this row.
- Rejected transactions may be retained for forensic purposes, but only `accepted` rows are applied to state.

### Materialized State Tables

```sql
create table ledger_state_accounts (
  account_id text not null,
  asset_code text not null,
  balance_minor bigint not null,
  version bigint not null,
  last_transaction_id text not null,
  updated_at timestamptz not null default now(),
  primary key (account_id, asset_code),
  foreign key (last_transaction_id) references ledger_transactions(transaction_id)
);

create table ledger_state_versions (
  transaction_id text primary key references ledger_transactions(transaction_id),
  state_hash bytea not null,
  created_at timestamptz not null default now()
);

create table ledger_replay_checkpoints (
  checkpoint_id text primary key,
  based_on_transaction_id text not null references ledger_transactions(transaction_id),
  state_hash bytea not null,
  checkpoint_ref text not null,
  created_at timestamptz not null default now()
);
```

Notes:

- `version` increments exactly once per accepted state transition affecting a row.
- `ledger_state_versions` stores a digest of the post-transaction materialized state, which helps auditors detect divergence between ledger replay and live state.
- `ledger_replay_checkpoints` identifies reusable baseline states for fast replay and digital twin creation.

## Tamper Evidence

Each accepted row stores:

- `payload_hash = sha256(payload_canonical)`
- `ledger_hash = sha256(previous_hash || transaction_id || payload_hash || actor_id || submitted_at || signature)`

Implementation pattern:

1. Lock the chain tip with `select ledger_hash from ledger_transactions where status = 'accepted' order by ledger_seq desc limit 1 for update`.
2. Build the new `ledger_hash` from that tip.
3. Insert the new row in the same database transaction as state updates.

This guarantees:

- accepted ledger order is total and serial
- post-fact updates to old rows break the chain during verification
- auditors can recompute all hashes from genesis inside PostgreSQL or externally

Recommended hardening:

- Revoke `UPDATE`, `DELETE`, and `TRUNCATE` on `ledger_transactions` from the application role.
- Add a trigger that raises on attempted row mutation as a defense-in-depth control.

Example trigger:

```sql
create function deny_ledger_mutation() returns trigger language plpgsql as $$
begin
  raise exception 'ledger_transactions is append-only';
end;
$$;

create trigger ledger_no_update
  before update or delete on ledger_transactions
  for each row execute function deny_ledger_mutation();
```

## Ledger Versus Audit Log

The ledger is the immutable journal of accepted business facts. It is not the security audit log.

Use the ledger to answer:

- which business transaction was accepted
- what compensation reversed which prior transaction
- what current state should be after replay

Use the independent audit log to answer:

- who attempted a read or write
- which submission was rejected and why
- which operator approved or revoked authority
- which recovery or digital twin action occurred

Enterprise systems need both records because operational history and business-fact history are different things.

## Deterministic Validator

The validator is the only component allowed to append accepted ledger rows and mutate state tables. It runs inside a single PostgreSQL transaction.

### Validator Responsibilities

1. Parse and canonicalize the submitted payload.
2. Resolve the actor public key by `actor_key_id`.
3. Verify key validity window, revocation status, and transaction scope.
4. Recompute `payload_hash` and verify the detached signature.
5. Enforce replay protection with actor nonce rules.
6. Enforce business rules against current state.
7. Insert immutable ledger row.
8. Apply deterministic state transition.
9. Persist post-state hash.
10. Commit or reject atomically.

### Validation Pseudocode

```text
function processTransaction(tx):
  begin db transaction

  canonical_payload = canonicalize(tx.payload)
  payload_hash = sha256(canonical_payload)
  assert payload_hash == tx.payload_hash

  actor_key = load ledger_actor_keys where key_id = tx.actor_key_id for share
  assert actor_key exists
  assert actor_key.actor_id == tx.actor_id
  assert actor_key.revoked_at is null or actor_key.revoked_at > tx.submitted_at
  assert actor_key.valid_from <= tx.submitted_at
  assert actor_key.valid_to is null or actor_key.valid_to >= tx.submitted_at
  assert tx.transaction_type allowed by actor_key.scope

  signing_input = encodeEnvelopeFields(tx, payload_hash)
  assert verifySignature(actor_key.algorithm, actor_key.public_key, signing_input, tx.signature)

  assert nonceIsNext(tx.actor_id, tx.payload.nonce)

  current_tip = select latest accepted ledger row for update
  expected_previous_hash = current_tip.ledger_hash or null
  assert tx.previous_hash == expected_previous_hash

  current_state = loadRequiredStateRows(tx.payload) for update
  proposed_changes = applyBusinessRules(tx, current_state)
  assert proposed_changes is valid

  new_ledger_hash = sha256(expected_previous_hash || tx.transaction_id || payload_hash || tx.actor_id || tx.submitted_at || tx.signature)

  insert into ledger_transactions(...)
    values (..., canonical_payload, payload_hash, expected_previous_hash, new_ledger_hash, ...)

  writeStateChanges(proposed_changes, tx.transaction_id)
  state_hash = hashMaterializedStateRows(proposed_changes.affected_rows)
  insert into ledger_state_versions(transaction_id, state_hash)

  recordNonce(tx.actor_id, tx.payload.nonce)
  commit
```

### Business Rule Pseudocode

```text
function applyBusinessRules(tx, state):
  switch tx.transaction_type:
    case "deposit":
      assert tx.payload.amount_minor > 0
      increment balance of target account

    case "transfer":
      assert tx.payload.amount_minor > 0
      assert tx.payload.from_account_id != tx.payload.to_account_id
      assert source balance >= tx.payload.amount_minor
      decrement source balance
      increment destination balance

    case "rollback":
      return applyRollbackRules(tx, state)

    default:
      reject "unsupported_transaction_type"

  return proposed_changes
```

The validator must not depend on non-deterministic inputs such as wall-clock reads during rule evaluation, remote API calls, randomized values, or mutable external caches.

## Rollback via Compensating Transactions

Rollback never deletes, edits, or marks the original transaction as removed. It adds a new signed transaction whose effect neutralizes the target transaction.

### Rollback Payload

```json
{
  "transaction_id": "01JNWQ8T8CJ8X7S8PJ9AB5RFAT",
  "transaction_type": "rollback",
  "actor_id": "agent_reconciler",
  "actor_kind": "ai",
  "actor_key_id": "agent_key_2026_03",
  "submitted_at": "2026-03-12T14:42:09.000Z",
  "payload": {
    "target_transaction_id": "01JNWQ0M7M5X4FJ7NZM3YVYVPS",
    "reason_code": "duplicate_transfer",
    "compensation": {
      "from_account_id": "acct_vendor",
      "to_account_id": "acct_ops",
      "asset_code": "USD",
      "amount_minor": 250000
    },
    "nonce": 201
  },
  "previous_hash": "base64url(prev_ledger_hash)",
  "payload_hash": "base64url(sha256(canonical_payload))",
  "signature": "base64url(ed25519_signature)"
}
```

### Rollback Rules

1. The target transaction must exist and be `accepted`.
2. The target must not already have an accepted rollback.
3. The rollback actor must be authorized for rollback operations on the target domain.
4. The compensating effect must be deterministic and explicit in the payload.
5. The rollback must preserve invariants, for example no negative balance after compensation.
6. Rollbacks can themselves be compensated by a later signed transaction if a rollback was erroneous.

### Rollback Validator Pseudocode

```text
function applyRollbackRules(tx, state):
  target = load accepted ledger transaction by tx.payload.target_transaction_id for update
  assert target exists
  assert no accepted rollback exists for target.transaction_id
  assert actorCanRollback(tx.actor_id, target)

  compensation = tx.payload.compensation
  reconstructed_effect = deriveInverseEffect(target)
  assert compensation == reconstructed_effect

  affected_state = load accounts referenced by compensation for update
  assert affected_state.source.balance >= compensation.amount_minor

  decrement compensation.from_account_id
  increment compensation.to_account_id

  return proposed_changes with rollback_of_transaction_id = target.transaction_id
```

Auditors can always see:

- the original transaction
- the rollback transaction
- the actor who initiated each
- the reason code
- the final net state after both were applied

## Auditability and Traceability

Every ledger row records:

- stable `transaction_id`
- actor identity and actor kind
- signing key used
- client-submitted timestamp and server-recorded timestamp
- signed payload bytes and signature
- chain position via `ledger_seq`, `previous_hash`, and `ledger_hash`

### Reconstructing Current State

Auditors should be able to ignore the materialized state and rebuild balances from ledger only:

```text
state = empty map
for tx in accepted ledger ordered by ledger_seq:
  state = applyBusinessRules(tx, state)
return state
```

Audit workflow:

1. Verify the chain from genesis by recomputing `payload_hash` and `ledger_hash`.
2. Verify each signature against the actor key valid at submission time.
3. Replay accepted transactions in `ledger_seq` order.
4. Compare replayed balances with `ledger_state_accounts`.
5. Compare recomputed per-transaction state digests with `ledger_state_versions`.

## Digital Twin Support

The ledger should support fast digital twin creation for sandboxed simulation of consequential transactions.

### Purpose

Digital twins let a human or agent test a transaction sequence against production-relevant state without mutating production databases.

Typical uses:

- previewing a transfer, approval chain, or workflow transition
- testing downstream event consequences before commit
- evaluating rollback and compensation behavior
- comparing multiple candidate transaction strategies

### Twin Source of Truth

A twin should be created from one of two sources:

1. a recent storage snapshot paired with a verified `state_hash`
2. a `ledger_replay_checkpoint` plus replay of later accepted transactions

The second model is especially valuable for ledgered systems because it keeps twin creation tied to verified ledger history rather than ad hoc row copying.

### Twin Requirements

- twin creation must complete in seconds for the common case
- the twin must use isolated credentials and isolated mutable storage
- the twin must preserve validator logic, policy rules, and ledger semantics
- all actions inside the twin must be marked as sandbox actions in audit records
- twin teardown must remove mutable state and revoke associated credentials

### Twin Execution Model

```text
select verified checkpoint
  -> materialize isolated twin state
  -> replay later accepted transactions if needed
  -> run proposed transaction sequence through the same validator
  -> capture resulting state diff, emitted events, and compensations
  -> return simulation artifact
  -> destroy twin
```

### Twin Output

The output of a twin run should include:

- accepted and rejected simulated transactions
- resulting account or entity state diffs
- emitted downstream events
- invariant check results
- compensating transactions that would be needed to reverse the simulated run
- reference to the source checkpoint or ledger position used

Digital twin output is advisory until a separate live submission is authorized and accepted.

## Cryptographic Verification Steps

1. Canonicalize `payload`.
2. Compute `payload_hash = sha256(canonical_payload)`.
3. Build the signing input from envelope fields in fixed order.
4. Fetch public key by `actor_key_id`.
5. Confirm algorithm matches both key record and envelope.
6. Confirm key validity window and revocation status at `submitted_at`.
7. Verify detached signature.
8. Reject if any envelope field used for signing differs from stored values.
9. Only after signature success, evaluate nonce and business rules.

PostgreSQL should store verification artifacts, but signature verification itself is usually best done in the application validator using a vetted crypto library rather than handwritten SQL crypto.

## High-Level Flow

```text
Signed transaction submitted
  -> canonicalize payload
  -> verify actor key, scope, nonce, signature
  -> lock ledger tip + required state rows
  -> validate deterministic business rules
  -> append immutable ledger row with previous_hash + ledger_hash
  -> apply state changes
  -> persist state digest
  -> commit

Rollback submitted
  -> same signature and scope checks
  -> load original accepted transaction
  -> derive and verify compensating effect
  -> append rollback ledger row
  -> apply compensating state change
  -> commit
```

## Example State Evolution

### Transfer

Before:

- `acct_ops/USD = 900000`
- `acct_vendor/USD = 100000`

After accepted transfer of `250000`:

- `acct_ops/USD = 650000`
- `acct_vendor/USD = 350000`

After accepted rollback of same transfer:

- `acct_ops/USD = 900000`
- `acct_vendor/USD = 100000`

The ledger contains three facts: prior state, original transfer, and rollback. Nothing is erased.

## Implementation Plan

1. Define canonical transaction schema in TypeScript, including envelope, payload variants, canonicalization rules, and signing input encoding.
2. Implement key registry persistence and admin migration for `ledger_actor_keys`, including key validity windows and scopes.
3. Add PostgreSQL migrations for `ledger_transactions`, `ledger_state_accounts`, and `ledger_state_versions`.
4. Implement append-only database protections: privileges, mutation-deny trigger, and idempotency constraints.
5. Build a validator module that performs canonicalization, signature verification, nonce checks, and transaction-type dispatch inside one database transaction.
6. Implement deterministic handlers for the minimum transaction set: `deposit`, `transfer`, and `rollback`.
7. Add ledger hashing logic that locks the accepted chain tip and computes `previous_hash` and `ledger_hash`.
8. Add state materialization logic with row-level locking and monotonic `version` increments.
9. Add replay tooling that reconstructs state from accepted ledger rows and compares it with materialized state.
10. Add tests:
    - signature success and failure
    - replay protection via nonce reuse
    - insufficient funds rejection
    - rollback of valid transfer
    - duplicate rollback rejection
    - tamper detection when a historical row is modified in a fixture
    - digital twin creation from checkpoint
    - sandbox transaction sequence produces deterministic state diff
    - twin teardown leaves production unchanged
11. Add checkpoint generation and retention rules for digital twin creation.
12. Add operational runbooks for key rotation, key revocation, offline audit replay, and digital twin recovery testing.

## Security Considerations

- Prefer Ed25519 unless an external interoperability requirement forces secp256k1.
- Keep private keys outside application memory where possible by using KMS/HSM signing.
- Scope AI agent keys narrowly and separately from human keys.
- Treat canonicalization as part of the security boundary; mismatched canonicalization breaks verification.
- Reject transactions whose `submitted_at` lies too far outside an allowed skew window if your threat model includes delayed replay.
- Enforce nonce uniqueness in durable storage, not in process memory.
- Lock both chain tip and affected state rows to avoid concurrent acceptance races.
- Keep rejected transactions for forensics if needed, but never let them affect state.
- Periodically run full chain verification and ledger-to-state replay to detect corruption or unauthorized writes.
- Use verified replay checkpoints for digital twins so sandbox execution starts from known-good state rather than unverified copies.

## Recommended Minimal First Release

If implementation must be phased, the smallest defensible first release is:

- Ed25519 only
- one asset class
- `deposit`, `transfer`, and `rollback`
- account-balance state table only
- key registry with scope enforcement
- full replay verifier
- one verified replay checkpoint path for digital twin simulation

That is enough to establish the security and audit model before adding richer business transaction types.
