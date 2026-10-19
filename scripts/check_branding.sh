#!/usr/bin/env bash
#
# Check that repository tracked files are clean of old hackathon / provider branding.
# Fails if any of: amd, rocm, vllm, hackathon, lablab, token factory, judge, radeon
# appear (case-insensitive) in tracked files other than lockfiles and node_modules.
#
set -euo pipefail

# Build search pattern dynamically so this script file itself doesn't trigger false positives
P_AMD="a""md"
P_ROCM="r""ocm"
P_VLLM="v""llm"
P_HACK="hack""athon"
P_LAB="lab""lab"
P_TF="token"" factory"
P_JUDGE="jud""ge"
P_RAD="rad""eon"

PATTERN="($P_AMD|$P_ROCM|$P_VLLM|$P_HACK|$P_LAB|$P_TF|$P_JUDGE|$P_RAD)"

echo "Scanning tracked repository files for obsolete branding keywords..."

MATCHES=$(git grep -i -I -E "$PATTERN" -- \
  ":(exclude)*.lock" \
  ":(exclude)*lock.yaml" \
  ":(exclude)pnpm-lock.yaml" \
  ":(exclude)node_modules" \
  ":(exclude)scripts/check_branding.sh" || true)

if [ -n "$MATCHES" ]; then
  echo "ERROR: Branding check failed. Obsolete branding terms found:"
  echo "$MATCHES"
  exit 1
fi

echo "✓ Branding check passed: repository is clean."
exit 0
