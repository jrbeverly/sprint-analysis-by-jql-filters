#!/usr/bin/env bash
# Focused tests for acquire.sh using a shell ACLI stub.
# Stub results are local wiring evidence; they do not prove real ACLI pagination
# or Jira authentication.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
EXPERIMENT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
STUB="$SCRIPT_DIR/stub.sh"
ACQUIRE="$EXPERIMENT_DIR/acquire.sh"
QUERIES_DIR="$EXPERIMENT_DIR/queries"

chmod +x "$STUB"

PASS=0
FAIL=0

_pass() { PASS=$((PASS+1)); printf 'PASS %s\n' "$1"; }
_fail() { FAIL=$((FAIL+1)); printf 'FAIL %s\n' "$1"; }
_assert() { "$@" && _pass "$1" || _fail "$1"; }

TMP=""
_setup() {
    TMP="$(mktemp -d)"
    STUB_LOG="$TMP/stub.log"
    SPRINTS_FILE="$TMP/sprints.json"
    ISSUES_FILE="$TMP/issues.json"
    printf '[{"id":420,"name":"Sprint 42","state":"active","startDate":"2026-08-11T00:00:00.000Z","endDate":"2026-08-22T00:00:00.000Z"}]\n' \
        > "$SPRINTS_FILE"
    printf '[]\n' > "$ISSUES_FILE"
    export JIRA_BOARD_ID=42
    export ACLI="$STUB"
    export STUB_LOG STUB_SPRINTS_FILE="$SPRINTS_FILE" STUB_ISSUES_FILE="$ISSUES_FILE"
    unset SPRINT_ID STUB_FAIL_ON STUB_MALFORMED_ON
}

_teardown() {
    [ -n "${TMP:-}" ] && rm -rf "$TMP"
    [ -d "$EXPERIMENT_DIR/runs" ] && rm -rf "$EXPERIMENT_DIR/runs"
    unset STUB_LOG STUB_SPRINTS_FILE STUB_ISSUES_FILE STUB_FAIL_ON STUB_MALFORMED_ON SPRINT_ID || true
}

_count_run_dirs() {
    if [ -d "$EXPERIMENT_DIR/runs" ]; then
        find "$EXPERIMENT_DIR/runs" -maxdepth 1 -mindepth 1 -type d | wc -l
    else
        echo 0
    fi
}

# ── 1. Basic acquisition produces all expected files ────────────────────────

_setup
RUN="$(bash "$ACQUIRE")"
_assert test -f "$RUN/sprint.json"
_assert test -f "$RUN/provenance.json"
_assert test -f "$RUN/all-issues.json"
_assert test -f "$RUN/delivery/completed.json"
_assert test -f "$RUN/delivery/incomplete.json"
_assert test -f "$RUN/delivery/high-priority-incomplete.json"
_assert test -f "$RUN/delivery/spillover.json"
_assert test -f "$RUN/estimation/eligible.json"
_assert test -f "$RUN/estimation/missing.json"
_assert test -f "$RUN/estimation/within-tolerance.json"
_assert test -f "$RUN/estimation/over-25.json"
_assert test -f "$RUN/estimation/over-50.json"
_assert test -f "$RUN/estimation/over-100.json"
_assert test -f "$RUN/flow/active.json"
_assert test -f "$RUN/flow/aging-2d.json"
_assert test -f "$RUN/flow/aging-4d.json"
_assert test -f "$RUN/flow/aging-7d.json"
_assert test -f "$RUN/flow/stale.json"
_assert test -f "$RUN/flow/blocked.json"
_assert test -f "$RUN/flow/reopened.json"
_assert test -f "$RUN/taxonomy/planned.json"
_assert test -f "$RUN/taxonomy/unplanned.json"
_assert test -f "$RUN/taxonomy/incident.json"
_assert test -f "$RUN/taxonomy/bug.json"
_assert test -f "$RUN/taxonomy/chore.json"
_assert test -f "$RUN/taxonomy/support.json"
_assert test -f "$RUN/taxonomy/responsibility.json"
_teardown

# ── 2. board list-sprints called with required flags ────────────────────────

_setup
bash "$ACQUIRE" > /dev/null
if grep -q '"--state"' "$STUB_LOG" && grep -q '"active"' "$STUB_LOG"; then
    _pass "board list-sprints uses --state active"
else
    _fail "board list-sprints uses --state active"
fi
if grep -q '"--paginate"' "$STUB_LOG"; then
    _pass "board list-sprints uses --paginate"
else
    _fail "board list-sprints uses --paginate"
fi
if grep -q '"--json"' "$STUB_LOG"; then
    _pass "board list-sprints uses --json"
else
    _fail "board list-sprints uses --json"
fi
_teardown

# ── 3. sprint list-workitems called with required flags ─────────────────────

_setup
bash "$ACQUIRE" > /dev/null
if grep '"list-workitems"' "$STUB_LOG" | grep -q '"--paginate"'; then
    _pass "sprint list-workitems uses --paginate"
else
    _fail "sprint list-workitems uses --paginate"
fi
if grep '"list-workitems"' "$STUB_LOG" | grep -q '"--fields"'; then
    _pass "sprint list-workitems uses --fields"
else
    _fail "sprint list-workitems uses --fields"
fi
if grep '"list-workitems"' "$STUB_LOG" | grep -q '"--json"'; then
    _pass "sprint list-workitems uses --json"
else
    _fail "sprint list-workitems uses --json"
fi
_teardown

# ── 4. Query calls use --jql with content from the literal query files ───────

_setup
bash "$ACQUIRE" > /dev/null
# Each JQL-filtered call must carry --jql
if grep '"list-workitems"' "$STUB_LOG" | grep -q '"--jql"'; then
    _pass "subset queries carry --jql flag"
else
    _fail "subset queries carry --jql flag"
fi
# The completed.jql content (statusCategory = Done) must appear in a --jql argument
if grep -q "statusCategory = Done" "$STUB_LOG"; then
    _pass "delivery/completed.jql content routed to --jql"
else
    _fail "delivery/completed.jql content routed to --jql"
fi
# taxonomy/incident.jql uses labels = "incident"; JSON-encodes inner quotes as \"
if grep -qF 'labels = \"incident\"' "$STUB_LOG"; then
    _pass "taxonomy/incident.jql content routed to --jql"
else
    _fail "taxonomy/incident.jql content routed to --jql"
fi
_teardown

# ── 5. Paged envelope flattened — {"issues":[...]} → flat array ─────────────

_setup
ENVELOPE_FILE="$TMP/envelope.json"
ISSUE='{"id":"1","self":"x","key":"T-1","fields":{"summary":"s","status":{"name":"Done","statusCategory":{"key":"done","name":"Done"}},"priority":{"name":"Medium"},"issuetype":{"name":"Story"},"labels":[],"customfield_10016":null,"customfield_10028":null}}'
printf '{"maxResults":50,"startAt":0,"total":1,"issues":[%s]}\n' "$ISSUE" > "$ENVELOPE_FILE"
export STUB_ISSUES_FILE="$ENVELOPE_FILE"
RUN="$(bash "$ACQUIRE")"
if jq -e 'type == "array"' "$RUN/all-issues.json" > /dev/null; then
    _pass "paged envelope flattened to array"
else
    _fail "paged envelope flattened to array"
fi
if [ "$(jq 'length' "$RUN/all-issues.json")" -eq 1 ]; then
    _pass "envelope flattening preserves issue"
else
    _fail "envelope flattening preserves issue"
fi
_teardown

# ── 6. Flat array preserved as-is ───────────────────────────────────────────

_setup
FLAT_FILE="$TMP/flat.json"
printf '[{"id":"2","self":"x","key":"T-2","fields":{"summary":"flat","status":{"name":"Done","statusCategory":{"key":"done","name":"Done"}},"priority":{"name":"Low"},"issuetype":{"name":"Task"},"labels":[],"customfield_10016":null,"customfield_10028":null}}]\n' \
    > "$FLAT_FILE"
export STUB_ISSUES_FILE="$FLAT_FILE"
RUN="$(bash "$ACQUIRE")"
if jq -e 'type == "array"' "$RUN/all-issues.json" > /dev/null; then
    _pass "flat array preserved as array"
else
    _fail "flat array preserved as array"
fi
if [ "$(jq 'length' "$RUN/all-issues.json")" -eq 1 ]; then
    _pass "flat array preserves issue count"
else
    _fail "flat array preserves issue count"
fi
_teardown

# ── 7. Explicit SPRINT_ID used without --state active ───────────────────────

_setup
MULTI_SPRINTS="$TMP/multi.json"
printf '[{"id":419,"name":"Sprint 41","state":"closed","startDate":"2026-07-28T00:00:00.000Z","endDate":"2026-08-08T00:00:00.000Z"},{"id":420,"name":"Sprint 42","state":"active","startDate":"2026-08-11T00:00:00.000Z","endDate":"2026-08-22T00:00:00.000Z"}]\n' \
    > "$MULTI_SPRINTS"
export STUB_SPRINTS_FILE="$MULTI_SPRINTS"
export SPRINT_ID=419
RUN="$(bash "$ACQUIRE")"
# board list-sprints should NOT use --state active when SPRINT_ID is set
if ! grep '"board list-sprints"' "$STUB_LOG" | grep -q '"active"'; then
    _pass "explicit SPRINT_ID does not filter by active state"
else
    _fail "explicit SPRINT_ID does not filter by active state"
fi
# sprint.json should record the explicitly selected sprint
RECORDED_ID="$(jq -r '.sprint_id' "$RUN/sprint.json")"
if [ "$RECORDED_ID" = "419" ]; then
    _pass "explicit SPRINT_ID recorded in sprint.json"
else
    _fail "explicit SPRINT_ID recorded in sprint.json (got: $RECORDED_ID)"
fi
_teardown

# ── 8. Zero active sprints fails with nonzero exit ──────────────────────────

_setup
printf '[]\n' > "$SPRINTS_FILE"
unset SPRINT_ID
if ! bash "$ACQUIRE" > /dev/null 2>&1; then
    _pass "zero active sprints exits nonzero"
else
    _fail "zero active sprints exits nonzero"
fi
_teardown

# ── 9. Multiple active sprints fails with nonzero exit ──────────────────────

_setup
printf '[{"id":420,"name":"S42","state":"active","startDate":"2026-08-11T00:00:00.000Z","endDate":"2026-08-22T00:00:00.000Z"},{"id":421,"name":"S43","state":"active","startDate":"2026-08-25T00:00:00.000Z","endDate":"2026-09-05T00:00:00.000Z"}]\n' \
    > "$SPRINTS_FILE"
unset SPRINT_ID
if ! bash "$ACQUIRE" > /dev/null 2>&1; then
    _pass "multiple active sprints exits nonzero"
else
    _fail "multiple active sprints exits nonzero"
fi
_teardown

# ── 10. ACLI command failure propagates — acquire exits nonzero ─────────────

_setup
export STUB_FAIL_ON="list-workitems"
if ! bash "$ACQUIRE" > /dev/null 2>&1; then
    _pass "ACLI failure propagates to nonzero exit"
else
    _fail "ACLI failure propagates to nonzero exit"
fi
_teardown

# ── 11. Malformed JSON from ACLI causes nonzero exit ────────────────────────

_setup
export STUB_MALFORMED_ON="list-workitems"
if ! bash "$ACQUIRE" > /dev/null 2>&1; then
    _pass "malformed ACLI JSON causes nonzero exit"
else
    _fail "malformed ACLI JSON causes nonzero exit"
fi
_teardown

# ── 12. Failed acquisition removes the partial run directory ────────────────

_setup
export STUB_FAIL_ON="list-workitems"
RUNS_BEFORE="$(_count_run_dirs)"
bash "$ACQUIRE" > /dev/null 2>&1 || true
RUNS_AFTER="$(_count_run_dirs)"
if [ "$RUNS_AFTER" -eq "$RUNS_BEFORE" ]; then
    _pass "failed acquisition removes partial run directory"
else
    _fail "failed acquisition removes partial run directory"
fi
_teardown

# ── 13. Unavailable sentinels are written for spillover and stale ────────────

_setup
RUN="$(bash "$ACQUIRE")"
if jq -e '.unavailable == true' "$RUN/delivery/spillover.json" > /dev/null; then
    _pass "delivery/spillover.json has unavailable=true"
else
    _fail "delivery/spillover.json has unavailable=true"
fi
if jq -e '.unavailable == true' "$RUN/flow/stale.json" > /dev/null; then
    _pass "flow/stale.json has unavailable=true"
else
    _fail "flow/stale.json has unavailable=true"
fi
if jq -e '.reason | type == "string"' "$RUN/delivery/spillover.json" > /dev/null; then
    _pass "delivery/spillover.json has reason string"
else
    _fail "delivery/spillover.json has reason string"
fi
_teardown

# ── 14. sprint.json records required identity fields ────────────────────────

_setup
RUN="$(bash "$ACQUIRE")"
for field in board_id sprint_id sprint_name sprint_state sprint_start sprint_end observation_time acquisition_start acquisition_end; do
    if jq -e "has(\"$field\")" "$RUN/sprint.json" > /dev/null; then
        _pass "sprint.json has $field"
    else
        _fail "sprint.json has $field"
    fi
done
_teardown

# ── 15. provenance.json records ACLI version and query provenance ────────────

_setup
RUN="$(bash "$ACQUIRE")"
for field in acli_version queries_dir board_id sprint_id; do
    if jq -e "has(\"$field\")" "$RUN/provenance.json" > /dev/null; then
        _pass "provenance.json has $field"
    else
        _fail "provenance.json has $field"
    fi
done
if jq -e '.acli_version | contains("stub")' "$RUN/provenance.json" > /dev/null; then
    _pass "provenance.json records stub ACLI version"
else
    _fail "provenance.json records stub ACLI version"
fi
_teardown

# ── 16. Acquired run replays offline through the analyzer ───────────────────
# Replay a run directory produced by acquisition through analyze.py in a bare
# environment (no ACLI on PATH, no credentials), confirm byte-identical output
# on rerun, and that a historical replay into a separate output directory
# leaves the default analysis/ tree untouched.

_setup
RUN="$(bash "$ACQUIRE")"
OUT_A="$TMP/replay-a.json"
OUT_B="$TMP/replay-b.json"
if env -i PATH=/usr/bin:/bin python3 "$EXPERIMENT_DIR/analyze.py" --input "$RUN" --output "$OUT_A"; then
    _pass "acquired run replays with bare environment (no ACLI, no credentials)"
else
    _fail "acquired run replays with bare environment (no ACLI, no credentials)"
fi
if jq -e '.delivery and (.sprint | has("sprint_id"))' "$OUT_A" > /dev/null; then
    _pass "replayed analysis has delivery evidence and sprint identity"
else
    _fail "replayed analysis has delivery evidence and sprint identity"
fi
if env -i PATH=/usr/bin:/bin python3 "$EXPERIMENT_DIR/analyze.py" --input "$RUN" --output "$OUT_B" \
    && cmp -s "$OUT_A" "$OUT_B"; then
    _pass "acquired run replay is byte-identical on rerun"
else
    _fail "acquired run replay is byte-identical on rerun"
fi
DEFAULT_LATEST="$EXPERIMENT_DIR/analysis/latest/analysis.json"
if [ -f "$DEFAULT_LATEST" ]; then
    cp "$DEFAULT_LATEST" "$TMP/latest-before.json"
fi
if env -i PATH=/usr/bin:/bin bash "$EXPERIMENT_DIR/publish.sh" "$OUT_A" "$TMP/historical" > /dev/null 2>&1; then
    _pass "historical replay publishes into separate output directory"
else
    _fail "historical replay publishes into separate output directory"
fi
if [ -f "$TMP/historical/latest/analysis.json" ]; then
    _pass "historical replay writes its own latest"
else
    _fail "historical replay writes its own latest"
fi
if [ -f "$DEFAULT_LATEST" ]; then
    if cmp -s "$DEFAULT_LATEST" "$TMP/latest-before.json"; then
        _pass "historical replay leaves default latest untouched"
    else
        _fail "historical replay leaves default latest untouched"
    fi
else
    if [ ! -f "$DEFAULT_LATEST" ]; then
        _pass "historical replay does not create default latest"
    else
        _fail "historical replay does not create default latest"
    fi
fi
_teardown

printf '\n%d passed, %d failed\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]
