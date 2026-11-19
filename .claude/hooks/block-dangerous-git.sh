#!/bin/bash
# PreToolUse guardrail for Bash. A convenience for the agent, not enforcement:
# CI and branch protection are authoritative (see CONTRIBUTING.md).

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command')

DANGEROUS_PATTERNS=(
  "--no-verify"
  "git (commit|am)([[:space:]].*)?[[:space:]]-[a-zA-Z]*n[a-zA-Z]*([[:space:]]|$)"
  "git push .*(--force|-f([[:space:]]|$)|--delete)"
  "git push .*(main|master)([[:space:]]|$)"
  "git push[[:space:]]*$"
  "gh pr merge"
  "reset --hard"
  "git clean -[a-z]*f"
  "git branch -D"
  "git checkout \."
  "git restore \."
)

for pattern in "${DANGEROUS_PATTERNS[@]}"; do
  if echo "$COMMAND" | grep -qE -- "$pattern"; then
    echo "BLOCKED: '$COMMAND' matches dangerous pattern '$pattern'. The user has prevented you from doing this." >&2
    exit 2
  fi
done

exit 0
