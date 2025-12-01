#!/usr/bin/env bash
# ACLI stub. Logs each invocation as a JSON array to STUB_LOG and returns
# canned responses from STUB_SPRINTS_FILE and STUB_ISSUES_FILE.

jq -cn '$ARGS.positional' --args -- "$@" >> "${STUB_LOG:-/dev/null}"

if [ -n "${STUB_FAIL_ON:-}" ] && printf '%s\n' "$@" | grep -qF "$STUB_FAIL_ON"; then
    echo "stub: injected failure for: $STUB_FAIL_ON" >&2
    exit 1
fi

if [ -n "${STUB_MALFORMED_ON:-}" ] && printf '%s\n' "$@" | grep -qF "$STUB_MALFORMED_ON"; then
    printf '{not-valid-json'
    exit 0
fi

case "$*" in
    "--version"*)
        printf '%s\n' "${STUB_VERSION:-acli version 1.0.0 (stub)}"
        ;;
    *"board list-sprints"*)
        if [ -n "${STUB_SPRINTS_FILE:-}" ]; then
            cat "$STUB_SPRINTS_FILE"
        else
            printf '[{"id":420,"name":"Sprint 42","state":"active","startDate":"2026-08-11T00:00:00.000Z","endDate":"2026-08-22T00:00:00.000Z"}]\n'
        fi
        ;;
    *"sprint list-workitems"*)
        if [ -n "${STUB_ISSUES_FILE:-}" ]; then
            cat "$STUB_ISSUES_FILE"
        else
            printf '[]\n'
        fi
        ;;
    *)
        printf 'stub: unknown command: %s\n' "$*" >&2
        exit 1
        ;;
esac
