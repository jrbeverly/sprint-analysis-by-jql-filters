#!/usr/bin/env bash
set -euo pipefail

# Publish a completed analysis artifact to three local locations:
#
#   <output>/sprints/<sprint-id>/snapshots/<observation-time>.json  (immutable)
#   <output>/sprints/<sprint-id>/analysis.json                      (sprint current)
#   <output>/latest/analysis.json                                   (global latest)
#
# Publication is local only. Observations are immutable: an identical rerun may
# reuse an existing observation, while differing content at the same timestamp
# fails before anything is written. Current files are replaced only with
# complete JSON and never moved backward in time. Historical replays target a
# separate output directory so they cannot move the default latest backward.

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

ANALYSIS_FILE="${1:-}"
OUTPUT_DIR="${2:-$SCRIPT_DIR/analysis}"

if [ -z "$ANALYSIS_FILE" ]; then
    echo "Usage: $0 ANALYSIS_JSON [OUTPUT_DIR]" >&2
    exit 1
fi

# ── Validate the artifact before touching anything ──────────────────────────

if [ ! -f "$ANALYSIS_FILE" ]; then
    echo "ERROR: analysis file not found: $ANALYSIS_FILE" >&2
    exit 1
fi

if ! jq -e '
    type == "object"
    and (.sprint | type) == "object"
    and (
        (.sprint.sprint_id | type) == "number"
        or ((.sprint.sprint_id | type) == "string" and .sprint.sprint_id != "")
    )
    and (.observation_time | type == "string" and length > 0)
' "$ANALYSIS_FILE" > /dev/null 2>&1; then
    echo "ERROR: analysis is not complete JSON (sprint.sprint_id and observation_time are required): $ANALYSIS_FILE" >&2
    exit 1
fi

SPRINT_ID="$(jq -r '.sprint.sprint_id' "$ANALYSIS_FILE")"
OBSERVATION_TIME="$(jq -r '.observation_time' "$ANALYSIS_FILE")"

case "$SPRINT_ID" in
    "" | */*) echo "ERROR: unusable sprint_id for a file path: $SPRINT_ID" >&2; exit 1 ;;
esac
case "$OBSERVATION_TIME" in
    "" | */*) echo "ERROR: unusable observation_time for a file path: $OBSERVATION_TIME" >&2; exit 1 ;;
esac

SPRINT_DIR="$OUTPUT_DIR/sprints/$SPRINT_ID"
SNAPSHOTS_DIR="$SPRINT_DIR/snapshots"
SNAPSHOT_FILE="$SNAPSHOTS_DIR/$OBSERVATION_TIME.json"
SPRINT_CURRENT="$SPRINT_DIR/analysis.json"
LATEST_FILE="$OUTPUT_DIR/latest/analysis.json"

# ── Check the immutable observation ─────────────────────────────────────────

if [ -f "$SNAPSHOT_FILE" ]; then
    if ! jq -e . "$SNAPSHOT_FILE" > /dev/null 2>&1; then
        echo "ERROR: existing observation is not valid JSON; refusing to overwrite: $SNAPSHOT_FILE" >&2
        exit 1
    fi
    if [ "$(jq -n --slurpfile existing "$SNAPSHOT_FILE" --slurpfile incoming "$ANALYSIS_FILE" '$existing == $incoming')" != "true" ]; then
        echo "ERROR: observation $OBSERVATION_TIME for sprint $SPRINT_ID already exists with different content; refusing to overwrite" >&2
        exit 1
    fi
    REUSE_OBSERVATION=1
else
    REUSE_OBSERVATION=0
fi

# ── Current files never move backward in time ────────────────────────────────
# Observation times are ISO-8601 UTC strings produced by acquisition in a
# consistent format, so lexicographic order is chronological order.

_guard_forward() {
    local file="$1" label="$2"
    if [ ! -f "$file" ]; then
        return 0
    fi
    local existing_time
    existing_time="$(jq -r '.observation_time // empty' "$file" 2>/dev/null || true)"
    if [ -n "$existing_time" ] && [ "$existing_time" \> "$OBSERVATION_TIME" ]; then
        echo "ERROR: refusing to move $label backward ($existing_time is newer than $OBSERVATION_TIME)" >&2
        exit 1
    fi
}

_guard_forward "$SPRINT_CURRENT" "sprint current"
_guard_forward "$LATEST_FILE" "global latest"

# ── Write files atomically: same-directory temp file then rename ─────────────

TMP_WRITE=""
trap '[ -n "$TMP_WRITE" ] && rm -f "$TMP_WRITE"' EXIT

_atomic_write() {
    local src="$1" dest="$2"
    mkdir -p "$(dirname "$dest")"
    TMP_WRITE="$(mktemp "$(dirname "$dest")/.publish.XXXXXX")"
    cp "$src" "$TMP_WRITE"
    mv "$TMP_WRITE" "$dest"
    TMP_WRITE=""
}

if [ "$REUSE_OBSERVATION" -eq 1 ]; then
    echo "reusing identical observation: $SNAPSHOT_FILE"
else
    _atomic_write "$ANALYSIS_FILE" "$SNAPSHOT_FILE"
    echo "published observation: $SNAPSHOT_FILE"
fi
_atomic_write "$ANALYSIS_FILE" "$SPRINT_CURRENT"
echo "published sprint current: $SPRINT_CURRENT"
_atomic_write "$ANALYSIS_FILE" "$LATEST_FILE"
echo "published latest: $LATEST_FILE"
