# Snapshot fixtures

Run-directory snapshots of `Platform Sprint 42` (board 42, sprint 420,
2026-08-11 to 2026-08-22), following the same directory shape as
`fixtures/sprint-42/` and `acquire.sh` run directories. The analyzer consumes
these for scope change and blocked/active set comparison; it does not implement
a scheduler or query Jira history.

## Story

| Observation | State | Population |
| --- | --- | --- |
| `2026-08-11T090000Z` (start) | active | 9 issues: the 8 planned items including PLAT-111 and PLAT-112, plus PLAT-104 |
| `2026-08-14T090000Z` (middle) | active | 11 issues: PLAT-108 and PLAT-109 added as unplanned incident work |
| `2026-08-18T090000Z` (current, in `fixtures/sprint-42/`) | active | 10 issues: PLAT-110 added as planned scope; PLAT-111 and PLAT-112 descoped |
| `2026-08-22T090000Z` (final) | closed | 10 issues; 7 completed, 3 incomplete |

Against the earliest earlier snapshot, the current run reports exactly:

- added: `PLAT-108`, `PLAT-109`, `PLAT-110`
- removed: `PLAT-111`, `PLAT-112`
- added and unplanned: `PLAT-108`, `PLAT-109`; added and not unplanned: `PLAT-110`
- PLAT-104 is unplanned but present from the start, so it is never
  added-since-start: the two sets stay separate.

Blocked and active sets are authored per observation; because observations are
intermittent samples, the analyzer records that exact transition times and
uninterrupted active duration cannot be established from them.

Note: the current observation's `taxonomy/planned.json` includes PLAT-110 even
though it entered the sprint mid-way; `planned.jql` is a provisional,
owner-confirmable predicate recorded in the contract.
