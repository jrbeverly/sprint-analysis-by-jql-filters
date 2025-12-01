# Implementation plan

Target: `jira/sprint-analysis-by-jql-filters/`. Issue #401 delivers this plan;
the steps below are proposed implementation work, not completed functionality.

Keep acquisition in a small shell script, classifications in literal JQL files,
and analysis in one Python standard-library script. All inputs, fixtures, scripts,
and outputs stay within this experiment. No service, database, deployment,
scheduler, Jira client, or shared experiment dependency is needed.

## 1. Settle the acquisition contract

Use one fixed Scrum board and record the selected sprint's ID, name, state,
dates, and acquisition time in `sprint.json`. Assume one active sprint; if there
are none or several, require an explicit sprint selection instead of guessing.
Keep this selection outside Python.

The vision's ACLI examples are conceptual. The official
[board command](https://developer.atlassian.com/cloud/acli/reference/commands/jira-board-list-sprints/)
uses `--id`, not `--board`:

```sh
acli jira board list-sprints --id "$JIRA_BOARD_ID" --state active --paginate --json
acli jira sprint list-workitems --board "$JIRA_BOARD_ID" --sprint "$SPRINT_ID" --paginate --json
```

The [sprint command](https://developer.atlassian.com/cloud/acli/reference/commands/jira-sprint-list-workitems/)
documents `--jql` and `--fields`. Its default fields omit estimate and actual
values, so request the evidence fields explicitly. Use
[workitem search](https://developer.atlassian.com/cloud/acli/reference/commands/jira-workitem-search/)
only when needed, retaining the same board filter and sprint scope in its JQL.

Before live implementation, inspect the installed ACLI version and command help,
then capture a small sanitized response to settle the JSON envelope, custom-field
names, null representation, and multi-page output. Preserve ACLI issue JSON;
Python may extract fields and keys but must not implement pagination. If output
needs flattening, do that in acquisition with a direct shell/jq operation.
Record the version and literal queries alongside the captured input for replay.

Confirm these site-specific facts with the board owner: board filter, completion
and spillover definitions, taxonomy predicates, estimate vocabulary, actual field
and units, and available aging/reopening history. Estimates and actuals must use
comparable units. Do not assume story points can be compared with logged seconds.
These facts block live query finalization, not synthetic development.

Done when the input shape and each population's meaning are explicit, with
unverified site assumptions labeled rather than presented as working queries.

## 2. Build a synthetic dataset and the first local analysis

Create `fixtures/sprint-42/` with `sprint.json`, `issues/all.json`, and canonical
set files matching the agreed ACLI shape. Until a live capture is available,
label that shape provisional. Include completed and incomplete planned work,
unplanned work, incidents, support, responsibilities, bugs, blocked/reopened
items, aging work, high-priority incomplete work, and estimate boundary cases.
Use invented summaries and identities only.

Start `analyze.py` with delivery counts and one incident intersection. Index
evidence by issue key, deduplicate membership, sort output keys/issues, and emit
local `analysis.json`. The same entry point must accept fixtures and acquired
files without a synthetic-data branch. Freeze the observation time in the input
so replay produces identical output.

For an independently calculated first example, use ten current issues, six
completed and four incomplete. Two of the four incomplete issues are incidents:
incomplete rate is 0.4 and its incident composition is 0.5. Check the exact two
evidence keys and summaries as well as those numbers.

Done when this runs without ACLI, credentials, Jira access, or third-party Python
packages and preserves issue-level evidence.

## 3. Extend the canonical sets and arithmetic

Add literal query files under `queries/` and corresponding fixture outputs.
Use a short table in that directory to record each file's predicate, population,
denominator, and required fields; do not build a query language or Python JQL
builder. Introduce the following sets in small increments:

| Area | Jira-supplied sets | Local calculation |
| --- | --- | --- |
| Delivery | completed, incomplete, high-priority incomplete, spillover where supported | Counts and rates over the declared sprint population |
| Scope/taxonomy | planned, unplanned, incident, bug, chore, support, responsibility; other existing categories as needed | Counts, rates, and intersections |
| Estimation | eligible, missing, within tolerance, over-25, over-50, over-100 | Counts divided by the eligible population |
| Flow | active, aging-2d/4d/7d, stale, blocked, reopened | Counts, rates, and snapshot comparisons |
| Friction | blocked, reopened, bug, incident, regression, support, unplanned | Intersections explaining affected work |

For finite estimates such as 1, 2, 3, 5, 8, 13, enumerate literal JQL clauses
comparing the actual field to each constant threshold. Define “over” as strictly
greater than 1.25, 1.5, or 2 times the estimate; the sets are nested. Eligibility
requires a supported positive estimate and a usable actual in the agreed units.
Report missing/unsupported inputs separately. Keep the policy in JQL rather than
recalculating membership in Python. If the site's fields cannot support it,
mark the metric unavailable with a reason pending a suitable Jira predicate.

Do not equate active-sprint incomplete work with confirmed spillover. Propose
final-snapshot incomplete work as outgoing spillover, subject to the owner's
definition; label the active-sprint signal as incomplete. For aging, use an
appropriate Jira field/history predicate, not issue creation or last-update time
as a substitute for time active. Where unavailable, use downloaded timestamps or
snapshot observations and label the resulting duration and its sampling limits.

Each metric should contain count, denominator, percentage as a fraction in [0,1],
and sorted issue evidence (key, summary, relevant estimate/actual values and
taxonomy memberships). A zero denominator produces `null`, not zero or NaN.
Missing required files fail the run; an explicitly unsupported metric has a
reason and null values, while a successfully queried empty set has count zero.
Reject category keys outside the canonical population rather than silently
changing the denominator; retain older evidence separately for removed work.

Distinguish `count(metric ∩ category) / count(category)` from composition
`count(metric ∩ category) / count(metric)`. Taxonomy can overlap, so composition
need not sum to one. Cover delivery, scope, estimation, flow, friction, taxonomy,
intersections, history, and structured availability observations in the output.
Include no aggregate health score or individual productivity ranking.

Done when every supported signal has hand-checked membership, a named denominator,
and enough evidence to explain its result without another Jira call.

## 4. Compare existing snapshots and previous analyses

Consume the existing snapshot mechanism's directories; do not implement its
scheduler. Add fixture start, middle, and final snapshots and two previous sprint
analysis files. Compare start/current keys to show added and removed work, and
compare blocked/active sets over time. Keep “added since start” separate from
Jira's unplanned taxonomy. Without a start snapshot, scope change is unavailable;
intermittent snapshots cannot prove exact transition times or continuous activity.

Read previous analyses from the same board in sprint-date order, not numeric ID
order. Exclude current-sprint reruns and `latest` duplicates. For each comparable
metric provide current, previous, historical average, and dated history, with the
average using prior non-null values only. Record metric definitions/units so a
changed definition is not silently compared with earlier values. No prior data
means empty history and null comparison values. Distinguish in-progress and final
observations rather than presenting them as equivalent delivery outcomes.

Done when fixture comparisons identify the exact added/removed keys and the
expected trend values, and missing history remains explicit.

## 5. Acquire and publish through local files

Implement `acquire.sh` to invoke ACLI with the fixed board/sprint and literal
queries into a fresh run directory. Authenticate through ACLI outside analysis;
do not pass credentials into Python's environment. Do not commit tokens or real
Jira exports. Check acquisition success and complete JSON before analysis so a
failed command cannot be mistaken for an empty population or reuse stale files.
Record acquisition start/end times: sequential Jira queries are not an atomic
snapshot. Retry a whole capture manually if membership becomes inconsistent.

Implement `publish.sh` as local file writes after successful analysis:

```text
analysis/sprints/<sprint-id>/snapshots/<observation-time>.json
analysis/sprints/<sprint-id>/analysis.json
analysis/latest/analysis.json
```

Preserve immutable observations and replace current files only with complete
JSON. Assume a single writer and chronological active-sprint runs. A historical
replay writes to a separate output directory and does not move global `latest`
backward. A run for Sprint 43 must leave Sprint 42's artifacts intact. Identical
reruns may reuse an identical immutable artifact but must not overwrite differing
content at the same timestamp. Remote publishing and environment provisioning
are outside this experiment's initial flow.

Done when a fixture run can acquire via a shell stub, analyze, and publish locally,
with failed acquisition leaving published files untouched.

## Validation and capability limits

Proposed commands below become available with implementation; they do not exist
yet. Run them from this experiment directory. Keep verification in one small
`unittest` file plus a shell acquisition stub, with manually authored expectations.

```sh
python3 -m unittest discover -s tests -p 'test_*.py'
python3 analyze.py --input fixtures/sprint-42 --output work/analysis.json
python3 -m json.tool work/analysis.json > /dev/null
bash -n acquire.sh publish.sh
```

The local suite should cover the arithmetic example, deduplication, empty sprint,
zero denominator, missing actual/estimate, strict threshold boundaries and nested
sets, overlapping taxonomy, missing files, unavailable metrics, snapshots, trends,
deterministic replay, and two-sprint publication. Stub ACLI to verify arguments,
query-file routing, JSON capture, and failure propagation. Run the analyzer with
ACLI absent from PATH and credentials absent; inspect that it contains no HTTP,
authentication, subprocess acquisition, JQL, or taxonomy rules. Copy the experiment
to a temporary directory and repeat the fixture flow to demonstrate isolation.

An agent can implement and execute those local checks. Fixture membership checks
verify arithmetic, not whether Jira evaluates a query correctly. A stub cannot
verify ACLI pagination, response shape, authentication, permissions, or site fields.

A later read-only live smoke test requires an installed compatible ACLI, an
authorized Jira identity, network access, the fixed board, and confirmed field and
taxonomy definitions. Confirm the target Jira deployment is supported by that
ACLI before attempting it. Compare query keys against Jira for a known sprint,
including more than one page and values exactly at estimate thresholds. Replay
the resulting files offline through the same analyzer. Report inaccessible or
unsupported checks as unverified; do not replace ACLI with direct REST calls.

For this planning issue, validation is document review against every vision area,
relative-link checks, and diff/whitespace scope checks. The directory initially
contained only `VISION.md`, and `acli` was absent from PATH during review; no
application test, live acquisition, or deployment has been claimed.
