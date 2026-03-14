# Userflow State Machine Specification

<!-- last-edited: 2026-03-14 -->

CONTEXT MAP
this ──implements──────▶ blueprints/ux-blueprint.md §Pattern 1: Service Flow Mapping
this ──referenced by──── development/development-standards.md (feature implementation workflow)
this ──referenced by──── development/product-owner-interview.md (requirements capture)

> **Purpose:** This document provides the template and guidelines for formalizing user workflows as deterministic state machines. Every primary user goal must be mapped to a state machine before implementation begins.

---

## Overview

A **userflow state machine** defines the sequence of states a user moves through to accomplish a goal. It is the authoritative specification for:
- Entry and exit conditions
- All intermediate states and their meaning
- Transitions and what triggers each one
- Feedback provided at each state
- Invariants that must hold throughout the flow

This specification is independent of visual interface, technology stack, or actor type (human end-user, administrator, AI agent). Multiple rendering surfaces (web UI, API, CLI) are derived from the same state machine.

---

## Template: Userflow State Machine

For each primary user goal, define a state machine with the following structure:

```
# [Goal Name] State Machine

## Entry Condition
[What must be true for a user to begin this flow?]
Example: User is authenticated; User has created a workspace

## Exit Condition (Goal Achieved)
[What marks the successful completion of this flow?]
Example: Payment confirmed and subscription activated

## States and Transitions

### State: [STATE_NAME]
**Meaning:** [What does this state represent?]
**Entry:** [How does the user reach this state?]
**Available Actions:**
  - [Action] → [Next State] (triggered by: [event/user action])
  - [Action] → [Next State] (triggered by: [event/user action])
**Feedback:**
  - [What does the system show the user?]
  - [What is the user's expectation at this point?]
**Invariants:**
  - [What must be true while in this state?]
  - [What data is locked or read-only?]

---

## Full State Diagram

[ASCII diagram showing all states and transitions, or reference to a mermaid diagram]

---

## Edge Cases and Recoveries

| Edge Case | Current State | Trigger | Recovery Path |
|-----------|---------------|---------|----------------|
| [Scenario] | [State] | [Event] | [Resolution State] |

---

## Antipatterns (What NOT to do)

- [ ] Do not define states that have no valid transitions (dead ends)
- [ ] Do not allow two equally valid paths from the same state to different endpoints
- [ ] Do not hide required steps behind optional UI disclosure
- [ ] Do not mix implementation concerns (loading spinners, HTTP errors) into logical states

```

---

## How to Write Userflow State Machines

### 1. Identify the Primary User Goal

Start with the simplest, most common path to success. Example goals:
- "User signs up and creates a workspace"
- "Admin approves a pending bulk action"
- "Agent retrieves a list of resources and filters by criteria"

### 2. Define Entry and Exit

**Entry Condition:** What must be true before the flow starts?
- User is unauthenticated and opening the app for the first time
- User is authenticated and viewing a dashboard
- Agent is initialized with a valid API token and scope

**Exit Condition:** What marks success?
- User receives a confirmation email and workspace is created
- Bulk action executed and admin sees success notification
- Agent receives paginated results and stops making requests

### 3. List All Possible States

Brainstorm every state a user can occupy:
- `awaiting_input` — waiting for the user to type or select
- `validating` — system is checking input (validation, API call, DB lookup)
- `confirming` — system is asking the user to confirm a destructive or significant action
- `processing` — system is executing the user's request
- `success` — goal achieved, showing confirmation
- `error` — something went wrong, user can retry or escalate

**Avoid implementation-specific states:**
- ✗ `loading` (implementation detail; use `validating` or `processing` instead)
- ✗ `http_error_500` (implementation detail; use `error` with error code in payload)
- ✗ `button_disabled` (implementation detail; not a state)

### 4. Define Transitions

For each state, list every valid action and where it leads:

```
State: awaiting_input
  - User enters valid data → validating
  - User clicks "Cancel" → (exit flow) or (previous state)
  - User leaves page without saving → (warning) → confirm_abandon

State: validating
  - Validation passes → confirming
  - Validation fails → awaiting_input (with error feedback)
  - Timeout → error (with retry option)
```

### 5. Write Feedback for Each State

For each state, specify what the user sees and hears:

```
State: processing
Feedback:
  - Visual: progress indicator or "Processing your request..." message
  - Timing: if > 2 seconds, explain what is happening
  - User expectation: "I submitted something, the system is working on it"
  - Abort option: "Cancel" button available? Yes/No
```

### 6. Document Edge Cases

For each state, list what can go wrong and how the flow recovers:

```
State: processing
Edge cases:
  - User closes browser → recovery: state is persisted server-side, user can resume on re-open
  - Network timeout → recovery: retry button available, state remains `processing`
  - Server error → recovery: transition to `error` state with retry path
```

### 7. Verify Completeness

Before implementation, verify:
- [ ] Every state has at least one valid transition out (no dead ends)
- [ ] No two transitions from the same state lead to the same outcome (no redundant paths)
- [ ] Entry and exit conditions are unambiguous
- [ ] Edge cases either transition to a valid recovery state or explicitly document why they cannot occur
- [ ] All terminology is used consistently (no `user input` vs `user_input` mixing)

---

## Integration with Implementation

Once the state machine is defined and signed off:

1. **Implement state enum:** Each state is an explicit type in code, not a string or magic number
2. **Implement transitions:** Only valid transitions are possible in code; invalid transitions raise errors
3. **Test state coverage:** Every state is reachable in tests; every transition is tested
4. **Document API contracts:** API endpoints return a `state` field that matches the state machine definition
5. **Agent scopes:** Agents can only trigger actions valid from the current state (enforced server-side)

---

## Examples

### Example 1: Sign Up Flow

```
# User Sign Up State Machine

## Entry Condition
User is unauthenticated and visits the sign-up page

## Exit Condition
User has verified email and created a workspace

## States

### State: awaiting_email
User has not yet entered an email address
Transitions:
  - User enters valid email → validating_email

### State: validating_email
System is checking if email is already registered
Transitions:
  - Email is unique → awaiting_password
  - Email already exists → error_email_exists (user can sign in instead)
  - Network timeout → error_network (user can retry)

### State: awaiting_password
User is entering password and reviewing requirements
Transitions:
  - User enters valid password → password_strength_check
  - User enters weak password → error_weak_password (with guidance)

### State: password_strength_check
System is evaluating password strength
Transitions:
  - Password meets requirements → awaiting_confirmation
  - Password is weak → error_weak_password

### State: awaiting_confirmation
User is reviewing sign-up summary and confirming
Transitions:
  - User clicks "Create Account" → processing
  - User clicks "Cancel" → (exit flow)

### State: processing
System is creating account and sending verification email
Transitions:
  - Account created and email sent → awaiting_verification
  - Email service unavailable → error_email_send (user can retry)
  - Account creation failed → error_database

### State: awaiting_verification
User has received verification email and must click link
Feedback: "Check your inbox for a verification link (valid for 24 hours)"
Transitions:
  - User clicks verification link → verified
  - 24 hours pass without verification → error_verification_expired (can resend)

### State: verified
Email is verified; user can now create workspace
Transitions:
  - User creates workspace → success
  - User navigates away → (exit flow, account is created but inactive)
```

---

## Anti-Example: What NOT to Do

❌ **Bad:** Mixing implementation with state machine

```
State: loading_spinner
State: http_error_code_422
State: button_disabled
State: waiting_for_api_response
```

These are implementation details, not logical states. Refactor to:

```
State: validating
State: validation_failed
State: awaiting_confirmation
State: processing
```

---

## References

- `blueprints/ux-blueprint.md` - Full UX design philosophy
- `development/product-owner-interview.md` - Requirements that feed into state machines
- `development/development-standards.md` - Implementation workflow that follows state machines
