#!/usr/bin/env bash
# Run an AutoTyper `--smoke-test` command and fail unless it reports AUTOTYPER_SMOKE_OK.
#
# Usage: tools/smoke_check.sh <command> [args...]
# Example: xvfb-run -a tools/smoke_check.sh dist/AutoTyper --smoke-test
set -euo pipefail

readonly OK_MARKER="AUTOTYPER_SMOKE_OK"

[ "$#" -ge 1 ] || { echo "usage: $0 <command> [args...]" >&2; exit 2; }

status=0
output="$("$@" 2>&1)" || status=$?
echo "$output"
[ "$status" -eq 0 ] || { echo "error: '$1' exited with status $status" >&2; exit 1; }
case "$output" in
    *"$OK_MARKER"*) ;;
    *) echo "error: '$1' did not print $OK_MARKER" >&2; exit 1 ;;
esac
