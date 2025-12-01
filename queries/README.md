# JQL Query Index

Status: **provisional** — predicates are based on documented Jira/JQL behaviour; none
confirmed against a live board. Site-specific field names and taxonomy values require
board owner confirmation before live use. All queries retain the fixed board and sprint
scope. `$BOARD_ID`, `$SPRINT_ID`, and custom field names are placeholders.

Command-surface facts verified against installed ACLI 1.3.36-stable (2026-09-13):
`sprint list-workitems` requires `--board int` and `--sprint int` and accepts
`--jql`, `--fields` (default `"key,issuetype,summary,assignee,priority,status"`),
`--json`, `--paginate`, and `--limit`. Two live checks follow from that before
these files are trusted against Jira:

- `board = "$BOARD_ID"` is not a documented JQL field in the ACLI reference
  examples; verify whether `--jql` combines with or replaces the required
  `--board`/`--sprint` scope before relying on either behavior.
- `sprint = "$SPRINT_ID"` substitutes a numeric ID into a quoted-string JQL
  value; Jira `sprint` matching of quoted names versus numeric IDs must be
  confirmed on the live site (or the clauses dropped in favor of the scope flags).

## Delivery

| File | Population | Denominator | Required fields | Notes |
|---|---|---|---|---|
| `delivery/completed.jql` | Issues with statusCategory = Done at observation time | `all-issues.json` | status | Board done-column config may differ from statusCategory |
| `delivery/incomplete.jql` | Issues not in Done at observation time | `all-issues.json` | status | Active-sprint incomplete ≠ confirmed spillover |
| `delivery/high-priority-incomplete.jql` | Incomplete issues with priority Critical or High | `delivery/incomplete.json` | status, priority | Priority vocabulary is site-specific |
| `delivery/spillover.jql` | — | — | — | **Unavailable**: active sprint; proposed definition is final-snapshot incomplete, pending board owner confirmation |

## Estimation

| File | Population | Denominator | Required fields | Notes |
|---|---|---|---|---|
| `estimation/eligible.jql` | Issues with a supported positive estimate (1,2,3,5,8,13) and a usable actual value | `all-issues.json` | customfield_10016, customfield_10028 | Field names are provisional site-specific values |
| `estimation/missing.jql` | Issues with no estimate or an estimate outside the supported vocabulary, or with no actual | `all-issues.json` | customfield_10016, customfield_10028 | Null or unsupported estimate treated as missing |
| `estimation/within-tolerance.jql` | Eligible issues where actual ≤ 1.25 × estimate | `estimation/eligible.json` | customfield_10016, customfield_10028 | Strictly non-overlapping with over-25 |
| `estimation/over-25.jql` | Eligible issues where actual > 1.25 × estimate | `estimation/eligible.json` | customfield_10016, customfield_10028 | Nested: over-100 ⊆ over-50 ⊆ over-25 |
| `estimation/over-50.jql` | Eligible issues where actual > 1.5 × estimate | `estimation/eligible.json` | customfield_10016, customfield_10028 | |
| `estimation/over-100.jql` | Eligible issues where actual > 2.0 × estimate | `estimation/eligible.json` | customfield_10016, customfield_10028 | |

## Flow

| File | Population | Denominator | Required fields | Notes |
|---|---|---|---|---|
| `flow/active.jql` | Issues currently in an active (indeterminate) status | `all-issues.json` | status | |
| `flow/aging-2d.jql` | Active issues in current status for more than 2 calendar days | `all-issues.json` | status, statusCategory, changelog | OPEN RISK: requires Jira history predicate; provisional |
| `flow/aging-4d.jql` | Active issues in current status for more than 4 calendar days | `all-issues.json` | status, changelog | |
| `flow/aging-7d.jql` | Active issues in current status for more than 7 calendar days | `all-issues.json` | status, changelog | |
| `flow/stale.jql` | — | — | — | **Unavailable**: requires time-since-last-update predicate; cannot substitute `updated` timestamp for time-active duration |
| `flow/blocked.jql` | Issues currently flagged as blocked | `all-issues.json` | labels or flag field | OPEN RISK: blocked representation is site-specific (label, flag, status) |
| `flow/reopened.jql` | Issues that moved from Done back to a non-Done status | `all-issues.json` | changelog | OPEN RISK: requires changelog history predicate |

## Taxonomy

| File | Population | Denominator | Required fields | Notes |
|---|---|---|---|---|
| `taxonomy/planned.jql` | Issues present in the sprint at sprint start | `all-issues.json` | sprint changelog | OPEN RISK: requires sprint-membership history predicate |
| `taxonomy/unplanned.jql` | Issues added to the sprint after start, or labelled unplanned | `all-issues.json` | labels, sprint changelog | Definition is site-specific |
| `taxonomy/incident.jql` | Issues classified as incidents | `all-issues.json` | labels, issuetype | |
| `taxonomy/bug.jql` | Issues of type Bug or labelled as bugs | `all-issues.json` | issuetype, labels | |
| `taxonomy/chore.jql` | Issues classified as chores or maintenance | `all-issues.json` | issuetype, labels | |
| `taxonomy/support.jql` | Issues classified as support requests | `all-issues.json` | labels, issuetype | |
| `taxonomy/responsibility.jql` | Issues classified as operational responsibility | `all-issues.json` | issuetype, labels | |
