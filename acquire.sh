#!/usr/bin/env bash
set -euo pipefail

JIRA_BOARD_ID="${JIRA_BOARD_ID:?JIRA_BOARD_ID is required}"
SPRINT_ID="${SPRINT_ID:-}"
ACLI="${ACLI:-acli}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
QUERIES_DIR="$SCRIPT_DIR/queries"
# `key` is part of the documented --fields vocabulary (ACLI 1.3.36 default:
# "key,issuetype,summary,assignee,priority,status"); the analyzer indexes
# evidence by issue key, so request it explicitly.
FIELDS="key,summary,status,priority,issuetype,labels,customfield_10016,customfield_10028"

ACQUISITION_START="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

ACLI_VERSION="$("$ACLI" --version 2>&1)" \
    || { echo "ERROR: acli --version failed" >&2; exit 1; }

# Select sprint — auto-discover one active sprint, or use explicit SPRINT_ID.
if [ -z "$SPRINT_ID" ]; then
    SPRINTS_RAW="$("$ACLI" jira board list-sprints \
        --id "$JIRA_BOARD_ID" --state active --paginate --json)" \
        || { echo "ERROR: board list-sprints failed" >&2; exit 1; }
    SPRINTS_ARR="$(printf '%s' "$SPRINTS_RAW" \
        | jq 'if type == "array" then . else .values // .sprints // [] end')"
    SPRINT_COUNT="$(printf '%s' "$SPRINTS_ARR" | jq 'length')"
    if [ "$SPRINT_COUNT" -ne 1 ]; then
        echo "ERROR: $SPRINT_COUNT active sprint(s) on board $JIRA_BOARD_ID; set SPRINT_ID explicitly" >&2
        exit 1
    fi
    SPRINT_OBJ="$(printf '%s' "$SPRINTS_ARR" | jq '.[0]')"
else
    SPRINTS_RAW="$("$ACLI" jira board list-sprints \
        --id "$JIRA_BOARD_ID" --paginate --json)" \
        || { echo "ERROR: board list-sprints failed" >&2; exit 1; }
    SPRINTS_ARR="$(printf '%s' "$SPRINTS_RAW" \
        | jq 'if type == "array" then . else .values // .sprints // [] end')"
    SPRINT_OBJ="$(printf '%s' "$SPRINTS_ARR" \
        | jq --arg id "$SPRINT_ID" '[.[] | select((.id | tostring) == $id)] | .[0] // empty')"
    if [ -z "$SPRINT_OBJ" ]; then
        echo "ERROR: sprint $SPRINT_ID not found on board $JIRA_BOARD_ID" >&2
        exit 1
    fi
fi

SPRINT_ID="$(printf '%s' "$SPRINT_OBJ" | jq -r '.id')"
SPRINT_NAME="$(printf '%s' "$SPRINT_OBJ" | jq -r '.name')"
SPRINT_STATE="$(printf '%s' "$SPRINT_OBJ" | jq -r '.state')"
SPRINT_START="$(printf '%s' "$SPRINT_OBJ" | jq -r '.startDate // .sprint_start // ""')"
SPRINT_END="$(printf '%s' "$SPRINT_OBJ" | jq -r '.endDate // .sprint_end // ""')"

OBSERVATION_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RUN_DIR="$SCRIPT_DIR/runs/$OBSERVATION_TIME"
mkdir -p "$RUN_DIR/delivery" "$RUN_DIR/estimation" "$RUN_DIR/flow" "$RUN_DIR/taxonomy"

trap 'rm -rf "$RUN_DIR"' EXIT

# Run an ACLI command, validate JSON, flatten paged envelope if present, write to file.
_capture() {
    local label="$1" out="$2"
    shift 2
    local tmp flat
    tmp="$(mktemp)"
    if ! "$@" > "$tmp" 2>&1; then
        rm -f "$tmp"
        echo "ERROR: ACLI command failed for $label" >&2
        exit 1
    fi
    if ! flat="$(jq 'if type == "array" then . else .issues // [] end' "$tmp" 2>/dev/null)"; then
        rm -f "$tmp"
        echo "ERROR: malformed JSON from ACLI for $label" >&2
        exit 1
    fi
    if ! printf '%s' "$flat" | jq -e 'type == "array"' > /dev/null; then
        rm -f "$tmp"
        echo "ERROR: ACLI output for $label did not resolve to an array" >&2
        exit 1
    fi
    printf '%s\n' "$flat" > "$out"
    rm -f "$tmp"
}

# Acquire full sprint population.
_capture "all-issues" "$RUN_DIR/all-issues.json" \
    "$ACLI" jira sprint list-workitems \
        --board "$JIRA_BOARD_ID" --sprint "$SPRINT_ID" \
        --paginate --fields "$FIELDS" --json

# Execute each literal query file, substituting sprint/board/date placeholders.
_run_query() {
    local jql_file="$1"
    local rel="${jql_file#"$QUERIES_DIR/"}"
    local out="$RUN_DIR/${rel%.jql}.json"
    local jql
    jql="$(< "$jql_file")"
    jql="${jql//\$SPRINT_ID/$SPRINT_ID}"
    jql="${jql//\$BOARD_ID/$JIRA_BOARD_ID}"
    jql="${jql//\$SPRINT_START/$SPRINT_START}"
    _capture "$rel" "$out" \
        "$ACLI" jira sprint list-workitems \
            --board "$JIRA_BOARD_ID" --sprint "$SPRINT_ID" \
            --jql "$jql" --paginate --fields "$FIELDS" --json
}

for _f in \
    delivery/completed delivery/incomplete delivery/high-priority-incomplete \
    estimation/eligible estimation/missing estimation/within-tolerance \
    estimation/over-25 estimation/over-50 estimation/over-100 \
    flow/active flow/aging-2d flow/aging-4d flow/aging-7d \
    flow/blocked flow/reopened \
    taxonomy/planned taxonomy/unplanned taxonomy/incident taxonomy/bug \
    taxonomy/chore taxonomy/support taxonomy/responsibility; do
    _run_query "$QUERIES_DIR/$_f.jql"
done

# Unavailable sentinels for metrics that cannot be expressed as JQL queries.
printf '{"unavailable":true,"reason":"active sprint; spillover is final-snapshot incomplete, pending board owner confirmation"}\n' \
    > "$RUN_DIR/delivery/spillover.json"
printf '{"unavailable":true,"reason":"stale requires time-since-last-update; updated timestamp is not a substitute for time-active duration"}\n' \
    > "$RUN_DIR/flow/stale.json"

ACQUISITION_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

jq -n \
    --arg board_id "$JIRA_BOARD_ID" \
    --arg sprint_id "$SPRINT_ID" \
    --arg sprint_name "$SPRINT_NAME" \
    --arg sprint_state "$SPRINT_STATE" \
    --arg sprint_start "$SPRINT_START" \
    --arg sprint_end "$SPRINT_END" \
    --arg observation_time "$OBSERVATION_TIME" \
    --arg acquisition_start "$ACQUISITION_START" \
    --arg acquisition_end "$ACQUISITION_END" \
    '{
        board_id: ($board_id | tonumber? // $board_id),
        sprint_id: ($sprint_id | tonumber? // $sprint_id),
        sprint_name: $sprint_name,
        sprint_state: $sprint_state,
        sprint_start: $sprint_start,
        sprint_end: $sprint_end,
        observation_time: $observation_time,
        acquisition_start: $acquisition_start,
        acquisition_end: $acquisition_end
    }' > "$RUN_DIR/sprint.json"

jq -n \
    --arg acli_version "$ACLI_VERSION" \
    --arg queries_dir "$QUERIES_DIR" \
    --arg board_id "$JIRA_BOARD_ID" \
    --arg sprint_id "$SPRINT_ID" \
    '{acli_version: $acli_version, queries_dir: $queries_dir, board_id: $board_id, sprint_id: $sprint_id}' \
    > "$RUN_DIR/provenance.json"

trap - EXIT
echo "$RUN_DIR"
