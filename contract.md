# Acquisition Contract

Status: **partially verified** — the command surface, flags, and authentication
mechanism below were confirmed against ACLI 1.3.36-stable on 2026-09-13. There
is still no authorized Jira identity, no confirmed target deployment, and no
board owner confirmation, so the response envelope, null handling, pagination
output, and every site-specific definition remain provisional.

---

## ACLI

**Installed**: `acli version 1.3.36-stable`, downloaded from the official
`acli.atlassian.com` Linux amd64 binary URL into `~/.local/bin` on 2026-09-13
(nothing vendored in this repository). `acli jira` is documented as
**Jira Cloud commands** — a Data Center or Server deployment is not supported
by this binary; the target deployment must be Jira Cloud.

Verified against the installed binary's help output:

| Command | Verified flags |
|---|---|
| `acli jira board list-sprints` | `--id string` (required), `--state` (`future,active,closed`, comma-separated), `--paginate` ("loads all sprints and output as they become available"), `--json`, `--csv`, `--limit int` (default 50) |
| `acli jira sprint list-workitems` | `--board int` (required), `--sprint int` (required), `--jql string`, `--fields string` (default `"key,issuetype,summary,assignee,priority,status"`), `--json`, `--csv`, `--limit int` (default 50 per page), `--paginate` ("continue paginating to fetch all pages of results or up to the provided limit") |
| `acli jira sprint view` | `--id string` (required), `--json` — fallback for sprint details |
| `acli jira workitem search` | `--jql/-j`, `--fields/-f` (default `"issuetype,key,assignee,priority,status,summary"`), `--json`, `--paginate`, `--limit/-l`, `--count`, `--filter`, `--web` |
| `acli jira board view` | replaces deprecated `board get` (removal scheduled 2026-12-01) |

The plan's distinction is confirmed: `board list-sprints` takes `--id`;
`sprint list-workitems` requires both `--board int` and `--sprint int` and
accepts `--jql` and `--fields`. The default `--fields` vocabulary includes
`key` and omits labels and custom fields, so acquisition requests fields
explicitly. `acli jira field` has no list command, so custom field names
cannot be enumerated through ACLI.

Expected commands (from PLAN.md citing ACLI documentation):

```sh
# Confirm before live use
acli --version

# List active sprints for a board
acli jira board list-sprints \
  --id "$JIRA_BOARD_ID" \
  --state active \
  --paginate \
  --json

# List all work items in a sprint with evidence fields
acli jira sprint list-workitems \
  --board "$JIRA_BOARD_ID" \
  --sprint "$SPRINT_ID" \
  --paginate \
  --fields "key,summary,status,priority,issuetype,labels,$ESTIMATE_FIELD,$ACTUAL_FIELD" \
  --json

# JQL-filtered subset of sprint issues
acli jira sprint list-workitems \
  --board "$JIRA_BOARD_ID" \
  --sprint "$SPRINT_ID" \
  --jql '...' \
  --paginate \
  --fields "key,summary,status,issuetype,labels" \
  --json
```

RESOLVED: `--id` for `board list-sprints` and `--board`/`--sprint` for
`sprint list-workitems`; `--fields` is accepted by `sprint list-workitems`.
Still open: whether `--jql` combines with the required `--board`/`--sprint`
scope or replaces it, and whether custom field IDs are accepted in
`--fields`.

---

## Authentication

ACLI handles Atlassian authentication. Python never receives or uses credentials.

Verified against ACLI 1.3.36-stable:

- `acli jira auth login --web` — browser OAuth flow
- `acli jira auth login --site "<site>.atlassian.net" --email <email> --token` —
  API token read from **stdin** (not an environment variable)
- `acli jira auth status|switch|logout` — account inspection and management
- Configuration lives under `~/.config/acli/*.yaml` (mode 600), outside this
  repository

An unauthenticated invocation fails with
`✗ Error: unauthorized: use 'acli jira auth login' to authenticate` and a
**nonzero exit code**, so `acquire.sh` failure propagation works without
network access or credentials. No credential material exists in this
environment; an authorized Jira identity is a missing prerequisite for the
live smoke test.

---

## sprint.json

Acquisition writes one file at `{run_dir}/sprint.json`. Python reads it to
identify the sprint and anchor observation times.

```json
{
  "board_id": 123,
  "sprint_id": 456,
  "sprint_name": "Platform Sprint 42",
  "sprint_state": "active",
  "sprint_start": "2026-08-11T00:00:00.000Z",
  "sprint_end": "2026-08-22T00:00:00.000Z",
  "observation_time": "2026-08-18T09:00:00Z",
  "acquisition_start": "2026-08-18T08:55:00Z",
  "acquisition_end": "2026-08-18T09:01:30Z"
}
```

- `board_id`, `sprint_id`: integers from Jira
- `sprint_state`: `"active"`, `"closed"`, or `"future"`
- All timestamps: ISO-8601 UTC strings
- `observation_time`: the moment this snapshot represents (frozen into output artifacts)
- `acquisition_start` / `acquisition_end`: wall-clock range of the ACLI queries

Sprint selection belongs to acquisition (`acquire.sh`), not Python. If zero or
more than one active sprint is found, acquisition must fail with an error rather
than making an arbitrary choice.

---

## ACLI JSON envelope

OPEN RISK: the exact envelope ACLI emits with `--json --paginate` is unconfirmed.
The official command reference pages document flags and invocation examples but
**not** the JSON output shape, so the envelope is only observable against a live
authorized site. Acquisition keeps the current defensive flattening
(`.issues`, or pass-through for a flat array) until then.

Expected shape for `sprint list-workitems` based on the Jira Agile REST API:

```json
{
  "maxResults": 50,
  "startAt": 0,
  "total": 24,
  "issues": [
    {
      "id": "10042",
      "self": "https://example.atlassian.net/rest/agile/1.0/issue/10042",
      "key": "PLAT-101",
      "fields": {
        "summary": "Upgrade authentication middleware",
        "status": {
          "name": "In Progress",
          "statusCategory": { "key": "indeterminate", "name": "In Progress" }
        },
        "priority": { "name": "High" },
        "issuetype": { "name": "Story" },
        "labels": ["unplanned", "security"],
        "customfield_10016": 3,
        "customfield_XXXXX": null
      }
    }
  ]
}
```

With `--paginate`, ACLI is expected to combine multiple pages. The outer envelope
and whether pagination metadata appears once or is stripped entirely is
unconfirmed.

Acquisition must write each population file as a flat JSON array. If ACLI already
emits a flat array, no transformation is needed. If it emits a paged envelope,
acquisition extracts with `jq '.issues'` or the confirmed equivalent. Python does
not implement pagination.

---

## Issue fields

Python extracts these paths from each issue object in a population file:

| Python path | Jira field | Status |
|---|---|---|
| `issue["key"]` | Issue key | Always present: `"PLAT-101"` |
| `issue["fields"]["summary"]` | Issue title | Always present string |
| `issue["fields"]["status"]["statusCategory"]["key"]` | Status category | `"done"`, `"indeterminate"`, or `"new"` |
| `issue["fields"]["status"]["name"]` | Status name | Human-readable |
| `issue["fields"]["priority"]["name"]` | Priority name | OPEN RISK: may be `null` for unprioritized issues |
| `issue["fields"]["issuetype"]["name"]` | Issue type | `"Story"`, `"Bug"`, `"Task"`, ... |
| `issue["fields"]["labels"]` | Labels array | May be `[]` |
| `issue["fields"][ESTIMATE_FIELD]` | Story-point estimate | OPEN RISK: site-specific custom field name |
| `issue["fields"][ACTUAL_FIELD]` | Actual value | OPEN RISK: site-specific, must share units with estimate |

Null representation: JSON `null` is used for absent optional values. A null
estimate is treated as "missing estimate". Python does not coerce `null` to zero.

---

## Estimate and actual fields

OPEN RISK: both field names are site-specific custom fields. ACLI 1.3.36's
`jira field` group offers only create/delete/restore/update — no list command —
so the names must come from the board owner or the Jira UI, not from ACLI.

Likely candidates:
- Estimate: `customfield_10016` (story points, common Jira default)
- Actual: a separate custom field, if one exists

Requirements confirmed before live use:
- Estimate and actual must share the same unit (both story points, or both time
  in the same unit)
- Story points are not comparable to `timespent` (seconds); do not treat them as
  equivalent by default
- If no comparable actual field exists, estimation accuracy is unavailable for
  this site

Estimate vocabulary: assumed finite — `1, 2, 3, 5, 8, 13`. Issues with an
estimate outside this set are treated as unsupported for estimation analysis and
counted under `missing.json`.

---

## Population files

Each population file is a flat JSON array of issue objects in the ACLI shape
above. An empty query result is an empty array `[]`, not an absent file.

Directory layout under the run directory:

```
sprint.json
all-issues.json
delivery/
  completed.json
  incomplete.json
  high-priority-incomplete.json
  spillover.json
estimation/
  eligible.json
  within-tolerance.json
  over-25.json
  over-50.json
  over-100.json
  missing.json
flow/
  active.json
  aging-2d.json
  aging-4d.json
  aging-7d.json
  stale.json
  blocked.json
  reopened.json
taxonomy/
  planned.json
  unplanned.json
  incident.json
  bug.json
  chore.json
  support.json
  responsibility.json
```

Note: the canonical population file is `all-issues.json` (in the sprint root,
not in a subdirectory). A sub-directory named `issues/` is gitignored at the
repository level and cannot be committed.

`all-issues.json` is the canonical sprint population. All other files contain
subsets of those same issues, identified by issue key. A key in any subset file
that does not appear in `all-issues.json` is rejected by the analyzer.

---

## Population semantics

Proposed definitions — board owner must confirm the actual JQL predicates.

| File | Proposed meaning |
|---|---|
| `issues/all.json` | All issues in the sprint regardless of status |
| `delivery/completed.json` | Issues with `statusCategory = done` at observation time |
| `delivery/incomplete.json` | Sprint issues not in `done` at observation time |
| `estimation/missing.json` | Issues with no estimate or an unsupported estimate value |
| `estimation/over-25.json` | Estimated issues where actual > 1.25 × estimate |
| `estimation/over-50.json` | Estimated issues where actual > 1.5 × estimate |
| `estimation/over-100.json` | Estimated issues where actual > 2.0 × estimate |
| `flow/aging-2d.json` | Issues active for more than 2 calendar days at observation time |
| `flow/aging-4d.json` | Issues active for more than 4 calendar days |
| `flow/aging-7d.json` | Issues active for more than 7 calendar days |
| `flow/blocked.json` | Issues currently flagged blocked |
| `flow/reopened.json` | Issues that moved from done back to a non-done status |
| `taxonomy/planned.json` | Issues present at sprint start |
| `taxonomy/unplanned.json` | Issues added after sprint start or otherwise flagged unplanned |
| `taxonomy/incident.json` | Issues classified as incidents |
| `taxonomy/bug.json` | Issues of type Bug or labelled as bugs |
| `taxonomy/chore.json` | Issues classified as chores or maintenance |
| `taxonomy/support.json` | Issues classified as support requests |
| `taxonomy/responsibility.json` | Issues classified as operational responsibility |

OPEN RISK: the exact JQL predicates for each population require board owner
confirmation. In particular:
- "Completed" may differ from `statusCategory = done` depending on the board's
  done column configuration
- Current-sprint `incomplete` work is not the same as confirmed spillover from a
  prior sprint; do not conflate them
- Aging duration requires a Jira history predicate; issue creation or last-update
  time is not a substitute
- `blocked` and `reopened` may or may not be representable as pure JQL depending
  on how this board uses flags, labels, or workflow transitions

---

## Unavailability signals

Three states are possible for any population file:

| State | File present | Content |
|---|---|---|
| Successfully queried, empty | Yes | `[]` |
| Explicitly unavailable | Yes | `{"unavailable": true, "reason": "..."}` |
| Missing (acquisition error) | No | — |

A missing required file fails the analyzer run with an error. An `unavailable`
sentinel records the metric as unavailable with the given reason rather than
failing. An empty array produces zero-count metrics.

Required files: `sprint.json` and `all-issues.json`. All other files are required
unless an `unavailable` sentinel is present. Acquisition must write an
`unavailable` sentinel explicitly rather than omitting the file when a metric
cannot be queried.

---

## Metric definitions

Each metric carries its denominator and unit so that a changed JQL definition is
not silently compared against historical values using a different definition.

| Metric | Numerator | Denominator |
|---|---|---|
| Delivery completion rate | `count(completed)` | `count(all)` |
| Incomplete rate | `count(incomplete)` | `count(all)` |
| Estimation over-N rate | `count(over-N)` | `count(all) - count(missing)` |
| Taxonomy rate | `count(taxonomy_set)` | `count(all)` |
| Taxonomy composition of a signal | `count(signal ∩ taxonomy_set)` | `count(signal)` |

Zero denominator produces `null` (not `0` or `NaN`). Division is explicit.
Intersection is key matching only — no additional Jira query.

---

## Site-specific assumptions

These require confirmation from the board owner before live query finalization.
They do not block synthetic development.

1. Board ID
2. Board filter definition (which issues qualify for this board)
3. Sprint completion criterion (which status or board column counts as done)
4. Estimate custom field name and unit
5. Actual/logged effort custom field name, if any, and whether it shares units with estimates
6. Taxonomy label names or field values for `unplanned`, `incident`, `bug`, `chore`, `support`, `responsibility`
7. Whether aging can be expressed with a Jira/JQL history predicate, or must be derived from downloaded timestamps
8. Whether `blocked` has a Jira-native representation (flag, label, or status value)
9. Whether `reopened` has a Jira history predicate

---

## Outstanding live checks

Checked against the installed binary on 2026-09-13; the remainder requires an
authorized Jira Cloud identity and the board owner's confirmations:

1. ~~ACLI version and installed command surface~~ — resolved: 1.3.36-stable, see above
2. Exact `--json --paginate` envelope shape for `board list-sprints` and `sprint list-workitems` — **open**
3. ~~Whether `--fields` is accepted by `sprint list-workitems`~~ — resolved: yes, default `"key,issuetype,summary,assignee,priority,status"`
4. Custom field names and units for estimate and actual — **open** (`acli jira field` has no list command)
5. Jira flavour — partially resolved: this ACLI's `jira` group is **Cloud only**; the target deployment URL and flavour are unknown
6. Taxonomy label and field values for this board — **open**
7. Sprint completion and spillover definition for this board configuration — **open**
8. Whether aging, blocked, and reopened predicates are available as JQL — **open**

Missing prerequisites blocking the live smoke test, in order of dependency:

1. An authorized Jira identity (no `~/.config/acli` session; no API token available)
2. A confirmed target Jira Cloud deployment (no site name or URL exists anywhere in this repository)
3. The fixed Scrum board ID and its board filter definition
4. Board-owner confirmations: estimate/actual field names and units, completion and spillover definitions, taxonomy predicates, aging/reopening history support

The issue's read-only constraint stands: no Jira work items may be created or
modified to manufacture test data, and ACLI must not be replaced with direct
REST calls. None of the live checks above are claimed as passing.
