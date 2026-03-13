#!/usr/bin/env bash
# validate-commit-metadata.sh: Validates GIT_BRAIN_METADATA JSON schema.
# Usage: echo "$JSON" | .githooks/validate-commit-metadata.sh

set -euo pipefail

# Read from stdin
INPUT=$(cat)

if [[ -z "$INPUT" ]]; then
    echo "GIT_BRAIN_METADATA: JSON block is empty." >&2
    exit 1
fi

# Check for valid JSON syntax using jq
if ! echo "$INPUT" | jq . >/dev/null 2>&1; then
    echo "GIT_BRAIN_METADATA: JSON parse error." >&2
    echo "Ensure the block is valid JSON with no trailing commas." >&2
    exit 1
fi

REQUIRED=("retroactive_prompt" "outcome" "context" "agent" "session")
MISSING=()

for field in "${REQUIRED[@]}"; do
    VALUE=$(echo "$INPUT" | jq -r ".$field" 2>/dev/null)
    if [[ "$VALUE" == "null" || -z "${VALUE// /}" ]]; then
        MISSING+=("$field")
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "GIT_BRAIN_METADATA: Missing or empty required fields: $(IFS=,; echo "${MISSING[*]}")" >&2
    echo "All of the following must be present and non-empty:" >&2
    for field in "${REQUIRED[@]}"; do
        echo "  - $field" >&2
    done
    exit 1
fi

RETROACTIVE_PROMPT=$(echo "$INPUT" | jq -r '.retroactive_prompt')
if [[ ${#RETROACTIVE_PROMPT} -lt 50 ]]; then
    echo "GIT_BRAIN_METADATA: retroactive_prompt is too short (minimum 50 characters)." >&2
    echo "It must be specific enough for another agent to reproduce this change." >&2
    exit 1
fi

exit 0
