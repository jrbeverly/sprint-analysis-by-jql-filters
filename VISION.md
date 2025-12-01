# Vision — Jira Sprint Analysis Through ACLI and JQL

## Purpose

Build a sprint-analysis system that minimizes custom Jira integration software.

The system should use the official Atlassian Command Line Interface, `acli`, as the exclusive interface between the analysis workflow and Jira.

Python must not authenticate to Jira.

Python must not call Jira REST APIs.

Python must not implement Jira queries.

Python receives only local JSON artifacts that have already been produced by ACLI.

The architectural boundary is:

```text
Jira
  ↓
ACLI + JQL
  ↓
local JSON artifacts
  ↓
small Python analysis
  ↓
detail-rich analysis.json
```

The primary design objective is to push:

- issue selection;
- sprint selection;
- taxonomy;
- categorization;
- deterministic predicates;
- straightforward historical predicates;

into Jira and JQL.

Python should be responsible only for analysis that is substantially easier after the relevant Jira data has already been materialized locally.

---

# Design Principle

The system should not become a Jira analytics application written in Python.

It should instead be:

```text
ACLI = acquisition

JQL = classification

Python = arithmetic + aggregation

JSON = interface
```

If a question can reasonably be answered by a JQL predicate, prefer the JQL predicate.

If a question requires arithmetic across the resulting issue sets, perform that arithmetic in Python.

If historical snapshots already contain the required information, analyze those snapshots rather than querying Jira history again.

The preferred direction is always:

```text
more declarative Jira queries
less Jira-aware Python
```

---

# Fixed Board

The analysis operates against one explicitly configured Scrum board.

For example:

```text
JIRA_BOARD_ID=123
```

The workflow does not need generalized board discovery.

The board is infrastructure/configuration.

ACLI can inspect the board and its sprints.

Conceptually:

```bash
acli jira board list-sprints \
    --board "$JIRA_BOARD_ID" \
    --json
```

The workflow determines the sprint being analyzed and records its identity.

For example:

```json
{
  "board_id": 123,
  "sprint_id": 456,
  "sprint_name": "Platform Sprint 42"
}
```

The board ID should not be rediscovered by Python.

---

# ACLI Is the Jira Boundary

All Jira interaction occurs before Python begins.

ACLI retrieves sprint data using commands conceptually equivalent to:

```bash
acli jira sprint list-workitems \
    --board "$JIRA_BOARD_ID" \
    --sprint "$SPRINT_ID" \
    --paginate \
    --json
```

ACLI also supports JQL directly when listing sprint work items:

```bash
acli jira sprint list-workitems \
    --board "$JIRA_BOARD_ID" \
    --sprint "$SPRINT_ID" \
    --jql '...' \
    --paginate \
    --json
```

General JQL searches may use:

```bash
acli jira workitem search \
    --jql '...' \
    --paginate \
    --json
```

The outputs are redirected into local files.

Python does not need to know:

- the Jira hostname;
- Jira credentials;
- API tokens;
- REST endpoint names;
- Jira pagination;
- HTTP status codes;
- Jira authentication;
- Jira API versions.

That responsibility belongs to ACLI.

---

# Acquisition Model

The acquisition phase should produce a directory of ordinary JSON artifacts.

Conceptually:

```text
input/
  sprint.json

  issues/
    all.json

  delivery/
    completed.json
    incomplete.json

  estimation/
    over-25.json
    over-50.json
    over-100.json
    missing.json

  flow/
    aging-2d.json
    aging-4d.json
    aging-7d.json
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

These are examples rather than a mandatory fixed list.

The important property is that each artifact represents a meaningful set of Jira work items.

---

# JQL as the Analytical Vocabulary

JQL filters should define as much of the analytical vocabulary as practical.

Instead of Python implementing:

```text
Is this an incident?

Is this unplanned?

Is this a bug?

Is this support work?

Is this operational responsibility?

Is this ticket missing an estimate?
```

Jira answers those questions.

The existing Jira taxonomy is treated as authoritative.

For example:

```text
Unplanned
Incident
Bug
Chore
Support
Responsibility
Security
Maintenance
Feature
...
```

are Jira concepts.

Python does not reproduce their definitions.

This makes the taxonomy independently editable.

Changing the definition of an analytical category should normally mean changing a JQL expression, label convention, or saved Jira filter rather than changing Python.

---

# Canonical Analytical Dimensions

The initial analysis should concentrate on five areas.

## 1. Delivery

Questions:

```text
What was completed?

What remained incomplete?

What spilled over?

Did high-priority work remain incomplete?
```

Where possible, JQL produces the relevant issue sets.

Python calculates counts, ratios, intersections, and comparisons.

---

# 2. Plan Change

Questions:

```text
How much work was planned?

How much was unplanned?

How much operational work appeared?

How much incident/support/responsibility work occurred?
```

The existing Jira taxonomy should carry most of this responsibility.

For example:

```text
unplanned.json
incident.json
support.json
responsibility.json
```

can be produced directly from Jira predicates.

Python should not classify these issues itself.

---

# 3. Estimation Accuracy

Estimation accuracy is intentionally implemented using finite JQL classification wherever practical.

Assume estimates use a controlled finite vocabulary.

For example:

```text
1
2
3
5
8
13
```

Instead of Python determining whether every issue exceeded its estimate by 25%, JQL can enumerate the finite possibilities.

Conceptually:

```text
estimate = 1 AND actual > threshold
OR
estimate = 2 AND actual > threshold
OR
estimate = 3 AND actual > threshold
...
```

This produces analytical sets such as:

```text
within-tolerance.json
over-25.json
over-50.json
over-100.json
```

Python then calculates:

```text
count(over-25) / estimated issues

count(over-50) / estimated issues

count(over-100) / estimated issues
```

Python does not need to contain the policy defining what constitutes the >25%, >50%, or >100% classifications if those definitions can remain in JQL.

---

# 4. Flow and Aging

Useful deterministic sets may include:

```text
active > 2 days

active > 4 days

active > 7 days

blocked

reopened

stale / not recently updated

incomplete
```

JQL should perform these classifications wherever Jira's fields and history operators permit it.

Python consumes the resulting issue sets.

Where an exact duration genuinely cannot be represented through the available Jira/JQL model, Python may calculate it from already-downloaded timestamps or snapshots.

That is an exception rather than the default.

---

# 5. Friction and Rework

The system should identify issue populations associated with delivery friction.

Examples:

```text
blocked
reopened
bugs
incidents
regressions
support
unplanned work
```

Again, Jira determines membership.

Python determines relationships.

This distinction is important.

JQL can tell us:

```text
these 11 tickets were spillover

these 9 tickets were unplanned

these 5 tickets were incidents
```

Python can cheaply discover:

```text
7 of the 11 spillover tickets were unplanned

4 of those 7 were incidents
```

The analytical power comes from intersections of already meaningful Jira sets.

---

# Taxonomy as an Analytical Dimension

The existing rich Jira taxonomy should be exploited heavily.

Taxonomy is not merely another family of metrics.

It is a dimension through which other metrics can be explained.

For example:

```text
                    ALL   BUG   INCIDENT   UNPLANNED   SUPPORT

Spillover            18%    9%      31%        29%        22%
Over 50%             11%   19%      27%        16%         9%
Aged >4 days         14%   22%       8%        11%        17%
Reopened              6%   18%       4%         3%         5%
```

The system does not necessarily need to execute every possible Cartesian combination as a Jira query.

It may download the canonical sets once and calculate intersections locally by Jira issue key.

For example:

```python
spillover & incidents
```

is simply an intersection of two sets of issue keys.

This is an appropriate use of Python because Python is not deciding what "spillover" or "incident" means.

It is merely performing set arithmetic on classifications Jira has already supplied.

---

# Python Responsibility

Python should be intentionally boring.

Its input is local JSON.

Its output is local JSON.

Its core operations should largely consist of:

```text
load
count
intersect
divide
compare
group
serialize
```

Conceptually:

```python
all_issues = load("issues/all.json")
spillover = load("delivery/spillover.json")
incidents = load("taxonomy/incident.json")

analysis = {
    "total": len(all_issues),
    "spillover": {
        "count": len(spillover),
        "percentage": len(spillover) / len(all_issues),
        "incidents": len(spillover & incidents),
    },
}
```

This is the desired level of sophistication.

Python should not contain:

```text
JiraClient
JiraRepository
SprintService
TaxonomyService
IssueClassifier
JQLBuilder
JiraDTO
SprintAnalyzerFactory
```

There is no reason for these abstractions.

---

# Detailed Issue Evidence

The output should not contain metrics alone.

It should retain the issues that caused those metrics.

For example:

```json
{
  "estimate_accuracy": {
    "over_50_percent": {
      "count": 4,
      "percentage": 0.12,
      "issues": [
        {
          "key": "PLAT-142",
          "summary": "Upgrade authentication middleware",
          "estimate": 3,
          "actual": 6,
          "taxonomy": ["unplanned", "security"]
        }
      ]
    }
  }
}
```

This is important because the artifact is intended to support later human or AI interpretation.

A statement such as:

```text
12% of estimated work exceeded its estimate by more than 50%
```

is useful.

A statement accompanied by:

```text
these four tickets caused it
```

is much more useful.

---

# Output Artifact

The final product is one detail-rich JSON document.

Conceptually:

```text
analysis.json
```

It should contain both summary metrics and supporting evidence.

A possible shape is:

```json
{
  "sprint": {},
  "delivery": {},
  "scope": {},
  "estimation": {},
  "flow": {},
  "friction": {},
  "taxonomy": {},
  "intersections": {},
  "history": {},
  "observations": {}
}
```

The schema should remain practical rather than abstract.

It exists to make downstream interpretation easy.

---

# Synthetic Development Data

Development and testing should not require access to production Jira data.

A synthetic ACLI-output fixture should model a believable sprint.

For example:

```text
fixtures/
  sprint-42/
    issues/
    delivery/
    estimation/
    flow/
    taxonomy/
```

The synthetic sprint should deliberately contain interesting conditions:

```text
planned work that completed

planned work that spilled

unplanned work

incidents

support responsibilities

bugs

reopened work

blocked work

accurately estimated work

25%+ estimate misses

50%+ estimate misses

100%+ estimate misses

aging work

high-priority unfinished work
```

The Python analysis should run identically against synthetic and real ACLI output.

This reinforces the architectural boundary:

```text
Python does not care where the JSON came from.
```

---

# Snapshot Model

The system assumes a snapshotting mechanism already exists.

Snapshots preserve the state of the board/sprint at useful points in time.

Conceptually:

```text
snapshots/
  sprint-42/
    2026-08-17T090000Z/
    2026-08-19T090000Z/
    2026-08-21T090000Z/
    2026-08-24T090000Z/
    final/
```

A snapshot contains enough downloaded Jira state to reproduce the analysis for that point in time.

The analysis process can therefore compare:

```text
current state
vs
earlier state
```

without asking Jira to reconstruct everything historically.

---

# Historical Analysis

Previous sprint analyses are ordinary JSON artifacts.

For example:

```text
analysis/
  sprint-39/
    analysis.json

  sprint-40/
    analysis.json

  sprint-41/
    analysis.json

  sprint-42/
    analysis.json
```

The current analysis can load previous analyses directly.

This allows extremely simple trend calculation.

Conceptually:

```python
previous = load_previous_analyses()
current = analyze_current()

current["history"] = {
    "spillover": [
        previous[0]["delivery"]["spillover"]["percentage"],
        previous[1]["delivery"]["spillover"]["percentage"],
        current["delivery"]["spillover"]["percentage"],
    ]
}
```

No Jira call is required for this.

---

# Historical Snapshot Analysis

Snapshots also allow questions that ordinary current-state JQL cannot easily answer.

For example:

```text
Was this ticket present at sprint start?

Was it introduced later?

Was it unfinished three days ago?

How long has it remained in the active population?

Did the blocked population increase during the sprint?
```

Rather than constructing sophisticated Jira history queries, the system may compare snapshots.

For example:

```text
sprint-start issue keys
        vs
current issue keys
```

immediately exposes work that appeared after the initial snapshot.

Likewise:

```text
Monday blocked set
Wednesday blocked set
Friday blocked set
```

provides a simple historical picture without requiring Python to understand Jira changelogs.

Snapshots turn history into set comparison.

That is desirable.

---

# Current Sprint and Latest Publication

Every analysis run publishes the resulting artifact to two logical locations.

The first location belongs permanently to the sprint being analyzed.

For example:

```text
analysis/sprints/42/analysis.json
```

The second is the rolling latest location:

```text
analysis/latest/analysis.json
```

Therefore a run for Sprint 42 produces:

```text
analysis/sprints/42/analysis.json
analysis/latest/analysis.json
```

When Sprint 43 becomes active, the same workflow naturally produces:

```text
analysis/sprints/43/analysis.json
analysis/latest/analysis.json
```

The previous sprint artifact remains untouched:

```text
analysis/sprints/42/analysis.json
```

while:

```text
analysis/latest/analysis.json
```

now represents Sprint 43.

No special latest-pointer database is required.

No active-sprint registry is required.

No cleanup operation is required.

Rolling time naturally maintains `latest`.

---

# Point-in-Time Analysis

The sprint-specific location may additionally preserve individual analysis runs.

For example:

```text
analysis/
  sprints/
    42/
      snapshots/
        2026-08-20T120000Z.json
        2026-08-21T120000Z.json
        2026-08-22T120000Z.json

      analysis.json
```

Here:

```text
snapshots/<timestamp>.json
```

is immutable point-in-time analysis.

And:

```text
analysis.json
```

is the latest analysis for that particular sprint.

The global:

```text
analysis/latest/analysis.json
```

is the latest analysis for whichever sprint is currently active.

This gives three useful levels:

```text
immutable historical observation

current state of a particular sprint

current state of the currently active sprint
```

without requiring a database.

---

# Trend Analysis

Historical metrics should provide context rather than merely archival storage.

For example:

```json
{
  "spillover": {
    "current": 0.22,
    "previous": 0.13,
    "historical_average": 0.11,
    "history": [
      { "sprint": 39, "value": 0.1 },
      { "sprint": 40, "value": 0.09 },
      { "sprint": 41, "value": 0.13 },
      { "sprint": 42, "value": 0.22 }
    ]
  }
}
```

The Python required for this is simple arithmetic over previously generated JSON.

The same applies to:

```text
completion
spillover
unplanned work
incidents
estimate accuracy
aging
blocked work
reopened work
```

The system should make trends easy to consume without trying to implement statistical sophistication unnecessarily.

---

# Analysis Should Preserve Context

A metric without context can be misleading.

For example:

```text
Spillover increased from 12% to 24%.
```

The artifact should make it possible to determine why.

Because taxonomy sets are retained, the analysis can expose:

```json
{
  "spillover": {
    "percentage": 0.24,
    "composition": {
      "unplanned": 0.61,
      "incident": 0.35,
      "support": 0.18
    }
  }
}
```

The analysis artifact does not necessarily need to produce prose explaining this.

It needs to provide enough structured evidence that a downstream consumer can observe:

```text
spillover increased

but most spillover came from unplanned incident work
```

That distinction is critical to useful sprint analysis.

---

# No Score

The system should avoid collapsing sprint health into a single numerical score.

For example:

```text
Sprint Health: 74/100
```

should not be a primary output.

Such scores hide useful information and create arbitrary weighting policy.

The output should instead preserve independent signals:

```text
delivery
predictability
estimation
flow
friction
work composition
historical direction
```

A downstream consumer may interpret those signals contextually.

---

# No Individual Productivity Scoring

The system should not attempt to determine individual developer productivity.

It should not produce:

```text
story points per engineer

tickets per engineer

developer ranking

individual velocity

individual performance score
```

The unit of analysis is the sprint and its delivery system.

Assignee information may remain available as evidence when operationally useful, but it should not become a performance-ranking mechanism.

---

# Example End-to-End Execution

Conceptually:

```text
1. Determine sprint
        ↓
2. ACLI downloads canonical sprint population
        ↓
3. ACLI executes analytical JQL queries
        ↓
4. JSON files exist locally
        ↓
5. Load previous snapshots / analyses
        ↓
6. Run small Python analysis
        ↓
7. Produce analysis.json
        ↓
8. Publish immutable point-in-time result
        ↓
9. Update sprint current result
        ↓
10. Update global latest result
```

The Jira-aware portion ends at step 3.

Everything after that operates on files.

---

# Example Workspace

A run may look approximately like:

```text
work/
  current/
    sprint.json

    issues/
      all.json

    delivery/
      completed.json
      spillover.json

    estimation/
      over-25.json
      over-50.json
      over-100.json

    flow/
      aging-2d.json
      aging-4d.json
      aging-7d.json
      blocked.json
      reopened.json

    taxonomy/
      incident.json
      bug.json
      unplanned.json
      chore.json
      support.json
      responsibility.json

  history/
    sprint-39.json
    sprint-40.json
    sprint-41.json

  output/
    analysis.json
```

Python effectively sees a local analytical dataset.

It does not see Jira.

---

# Authentication

ACLI owns Atlassian authentication.

For unattended execution, an Atlassian bot/service identity and API token may be supplied to ACLI.

Conceptually:

```bash
echo "$ATLASSIAN_API_TOKEN" |
  acli jira auth login \
    --site "$ATLASSIAN_SITE" \
    --email "$ATLASSIAN_EMAIL" \
    --token
```

The secret should be provided by the execution environment rather than committed to the analysis project.

Python never receives or uses the Atlassian credential.

---

# Implementation Philosophy

Prefer:

```bash
acli jira ... --json > something.json
```

over:

```python
jira.get(...)
```

Prefer:

```text
JQL predicate
```

over:

```python
if issue_matches_business_rule(issue):
```

Prefer:

```python
set(a) & set(b)
```

over implementing another query against Jira.

Prefer:

```python
count / total
```

over introducing an analytics framework.

Prefer reading:

```text
previous-analysis.json
```

over reconstructing historical Jira state.

Prefer snapshot comparison over sophisticated history-processing software when the snapshot already contains the required fact.

---

# Non-Goals

This project is not:

- a generalized Jira SDK;
- a Jira REST client;
- a replacement for Jira reporting;
- a data warehouse;
- a BI platform;
- an individual productivity tracker;
- a generalized statistical-analysis framework;
- a generalized workflow engine;
- a taxonomy implementation;
- a sprint-health scoring algorithm.

It is a deliberately small bridge from:

```text
Jira's existing structured knowledge
```

to:

```text
a rich machine-readable sprint analysis artifact.
```

---

# Success Criterion

The architecture is successful when the Python can be understood without knowing how to use Jira.

Someone reading the Python should see code concerned with:

```text
JSON
sets
counts
percentages
comparisons
history
output
```

They should not see code concerned with:

```text
JQL
HTTP
Jira authentication
Jira pagination
Jira endpoints
Jira query construction
Jira taxonomy rules
```

Jira and ACLI determine which work items belong to meaningful categories.

Snapshots preserve historical state.

Python combines those facts.

The final JSON artifact preserves enough metrics, history, taxonomy, intersections, and issue-level evidence for a downstream consumer to answer:

> How is this sprint going?

and:

> How did this sprint compare with how this team normally operates?

without needing to query Jira again.
