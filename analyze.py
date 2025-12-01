import argparse
import json
import os

ESTIMATE_FIELD = "customfield_10016"
ACTUAL_FIELD = "customfield_10028"

TAXONOMY_NAMES = ["bug", "chore", "incident", "planned", "responsibility", "support", "unplanned"]

KIND_BY_STATE = {"active": "in_progress", "closed": "final"}

# Delivery outcomes are only comparable between observations of the same kind:
# an in-progress completion rate is not the same outcome as a final one.
DELIVERY_OUTCOME_METRICS = frozenset({
    "delivery.completed",
    "delivery.incomplete",
    "delivery.high_priority_incomplete",
})


def _metric_definitions():
    """Definition signature per comparable metric path: numerator file,
    denominator population, and unit. Prior analyses must carry the identical
    signature before their values are compared."""
    defs = {}

    def add(path, numerator_file, denominator_file):
        defs[path] = {
            "numerator": f"count({numerator_file})",
            "denominator": f"count({denominator_file})",
            "unit": "fraction",
        }

    for name in ("completed", "incomplete", "high_priority_incomplete"):
        add(f"delivery.{name}", f"delivery/{name}.json", "all-issues.json")
    for name in ("missing", "within_tolerance", "over_25", "over_50", "over_100"):
        denom = "all-issues.json" if name == "missing" else "estimation/eligible.json"
        add(f"estimation.{name}", f"estimation/{name}.json", denom)
    for name in ("active", "aging_2d", "aging_4d", "aging_7d", "blocked", "reopened"):
        add(f"flow.{name}", f"flow/{name}.json", "all-issues.json")
    for name in TAXONOMY_NAMES:
        add(f"taxonomy.{name}", f"taxonomy/{name}.json", "all-issues.json")
    return defs


def _metric_value(artifact, path):
    node = artifact
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    if not isinstance(node, dict):
        return None
    return node.get("percentage")


def _load(path):
    with open(path) as f:
        return json.load(f)


def _load_pop(path):
    data = _load(path)
    if isinstance(data, dict) and data.get("unavailable"):
        return data
    return data


def _dedup(issues):
    seen = set()
    out = []
    for i in issues:
        if i["key"] not in seen:
            seen.add(i["key"])
            out.append(i)
    return out


def _validate(issues, all_index, label):
    for i in issues:
        if i["key"] not in all_index:
            raise ValueError(f"{i['key']} not in issues/all.json (from {label})")


def _is_unavail(pop):
    return isinstance(pop, dict) and pop.get("unavailable")


def _keys(issues):
    return {i["key"] for i in issues}


def _taxonomy_of(key, tax_indices):
    return sorted(name for name, ks in tax_indices.items() if key in ks)


def _evidence(issues, all_index, tax_indices):
    result = []
    for i in sorted(issues, key=lambda x: x["key"]):
        f = i["fields"]
        result.append({
            "actual": f.get(ACTUAL_FIELD),
            "estimate": f.get(ESTIMATE_FIELD),
            "key": i["key"],
            "summary": f["summary"],
            "taxonomy": _taxonomy_of(i["key"], tax_indices),
        })
    return result


def _metric(pop, denom, all_index, tax_indices):
    if _is_unavail(pop):
        return {"count": None, "denominator": None, "issues": None, "percentage": None,
                "reason": pop["reason"], "unavailable": True}
    count = len(pop)
    return {
        "count": count,
        "denominator": denom,
        "issues": _evidence(pop, all_index, tax_indices),
        "percentage": count / denom if denom else None,
    }


def _intersect(signal_issues, category_pop, all_index, tax_indices, signal_count, category_count):
    if _is_unavail(category_pop):
        return {
            "category_rate": {"count": None, "denominator": None, "issues": None, "percentage": None,
                               "reason": category_pop["reason"], "unavailable": True},
            "composition": {"count": None, "denominator": None, "issues": None, "percentage": None,
                            "reason": category_pop["reason"], "unavailable": True},
        }
    signal_keys = _keys(signal_issues)
    members = [i for i in category_pop if i["key"] in signal_keys]
    count = len(members)
    ev = _evidence(members, all_index, tax_indices)
    return {
        "category_rate": {
            "count": count,
            "denominator": category_count,
            "issues": ev,
            "percentage": count / category_count if category_count else None,
        },
        "composition": {
            "count": count,
            "denominator": signal_count,
            "issues": ev,
            "percentage": count / signal_count if signal_count else None,
        },
    }


def _load_and_prepare(path, all_index, label):
    pop = _load_pop(path)
    if not _is_unavail(pop):
        pop = _dedup(pop)
        _validate(pop, all_index, label)
    return pop


def _load_snapshots(snapshots_dir, board_id, sprint_id):
    """Load earlier observation directories for the current sprint. Each
    snapshot is a run-directory of the same shape as the current input. Only
    snapshots whose sprint.json matches the current board and sprint are used;
    they are returned in observation-time order."""
    snaps = []
    if not snapshots_dir or not os.path.isdir(snapshots_dir):
        return snaps
    for root, _dirs, files in os.walk(snapshots_dir):
        if "sprint.json" not in files:
            continue
        sprint = _load(os.path.join(root, "sprint.json"))
        if sprint.get("board_id") != board_id or sprint.get("sprint_id") != sprint_id:
            continue
        all_issues = _dedup(_load(os.path.join(root, "all-issues.json")))
        tax_indices = {}
        for name in TAXONOMY_NAMES:
            pop = _load_pop(os.path.join(root, "taxonomy", f"{name}.json"))
            if not _is_unavail(pop):
                tax_indices[name] = _keys(pop)
        snaps.append({
            "path": root,
            "sprint": sprint,
            "all_issues": all_issues,
            "all_index": {i["key"]: i for i in all_issues},
            "tax_indices": tax_indices,
            "active": _load_pop(os.path.join(root, "flow", "active.json")),
            "blocked": _load_pop(os.path.join(root, "flow", "blocked.json")),
        })
    snaps.sort(key=lambda s: s["sprint"].get("observation_time") or "")
    seen = set()
    unique = []
    for s in snaps:
        t = s["sprint"].get("observation_time")
        if t in seen:
            continue
        seen.add(t)
        unique.append(s)
    return unique


def _scope_section(current_all, all_index, tax_indices, snaps, current_time):
    """Compare the earliest earlier snapshot's canonical keys with the current
    canonical keys. Added/removed keys are key-set differences only; added
    issues are reported separately from the Jira-supplied unplanned taxonomy.
    Removed evidence is taken from the baseline snapshot, not the current
    population."""
    baseline = None
    for s in snaps:
        t = s["sprint"].get("observation_time") or ""
        if t and current_time and t < current_time:
            baseline = s
            break
    if baseline is None:
        return {
            "available": False,
            "reason": "no earlier snapshot for this sprint; scope change unavailable",
        }
    base_keys = _keys(baseline["all_issues"])
    cur_keys = _keys(current_all)
    added_keys = sorted(cur_keys - base_keys)
    removed_keys = sorted(base_keys - cur_keys)
    base_index = baseline["all_index"]
    unplanned_keys = tax_indices.get("unplanned")
    if unplanned_keys is None:
        added_unplanned_keys = None
        added_not_unplanned_keys = None
    else:
        added_unplanned_keys = sorted(k for k in added_keys if k in unplanned_keys)
        added_not_unplanned_keys = sorted(k for k in added_keys if k not in unplanned_keys)
    return {
        "available": True,
        "baseline_observation_time": baseline["sprint"].get("observation_time"),
        "baseline_sprint_state": baseline["sprint"].get("sprint_state"),
        "added": {
            "count": len(added_keys),
            "keys": added_keys,
            "issues": _evidence([all_index[k] for k in added_keys], all_index, tax_indices),
        },
        "removed": {
            "count": len(removed_keys),
            "keys": removed_keys,
            "issues": _evidence([base_index[k] for k in removed_keys], base_index, baseline["tax_indices"]),
        },
        "added_unplanned_keys": added_unplanned_keys,
        "added_not_unplanned_keys": added_not_unplanned_keys,
    }


def _observation_entry(observation_time, sprint_state, pop, all_index, tax_indices):
    if _is_unavail(pop):
        return {
            "observation_time": observation_time,
            "sprint_state": sprint_state,
            "unavailable": True,
            "reason": pop["reason"],
        }
    return {
        "observation_time": observation_time,
        "sprint_state": sprint_state,
        "keys": sorted(_keys(pop)),
        "evidence": _evidence(pop, all_index, tax_indices),
    }


def _observations_section(snaps, current_time, current_state, flow_active, flow_blocked, all_index, tax_indices):
    """Per-observation sets for blocked and active populations. Only snapshots
    strictly earlier than the current observation appear; the current input is
    the final entry. Observations are intermittent samples, so exact
    transition times and uninterrupted durations cannot be established."""
    earlier = [s for s in snaps if (s["sprint"].get("observation_time") or "") < (current_time or "")]
    blocked = {
        "observations": [
            _observation_entry(s["sprint"].get("observation_time"), s["sprint"].get("sprint_state"),
                               s["blocked"], s["all_index"], s["tax_indices"])
            for s in earlier
        ] + [_observation_entry(current_time, current_state, flow_blocked, all_index, tax_indices)],
        "limits": ["intermittent observations cannot establish exact transition times"],
    }
    active = {
        "observations": [
            _observation_entry(s["sprint"].get("observation_time"), s["sprint"].get("sprint_state"),
                               s["active"], s["all_index"], s["tax_indices"])
            for s in earlier
        ] + [_observation_entry(current_time, current_state, flow_active, all_index, tax_indices)],
        "limits": [
            "intermittent observations cannot establish exact transition times",
            "uninterrupted active duration cannot be established",
        ],
    }
    return {"blocked": blocked, "active": active}


def _load_history(history_dir, current_sprint):
    """Read earlier analysis.json artifacts from the same board, ordered by
    sprint date rather than numeric sprint ID. Current-sprint reruns, latest
    copies duplicating a per-sprint artifact, other boards, and sprints newer
    than the current one are excluded with recorded reasons."""
    entries = []
    excluded = []
    if not history_dir or not os.path.isdir(history_dir):
        return entries, excluded
    paths = []
    for root, _dirs, files in os.walk(history_dir):
        for fname in files:
            if fname == "analysis.json":
                paths.append(os.path.join(root, fname))

    def is_latest_copy(path):
        return os.path.basename(os.path.dirname(path)) == "latest"

    board_id = current_sprint.get("board_id")
    sprint_id = current_sprint.get("sprint_id")
    sprint_start = current_sprint.get("sprint_start") or ""

    by_sprint = {}
    for path in sorted(paths):
        art = _load(path)
        sprint = art.get("sprint")
        if not isinstance(sprint, dict):
            raise ValueError("%s: analysis is missing sprint identity" % path)
        info = {"path": path, "sprint_id": sprint.get("sprint_id"), "sprint_name": sprint.get("sprint_name")}
        if sprint.get("board_id") != board_id:
            excluded.append({**info, "board_id": sprint.get("board_id"), "reason": "different board"})
            continue
        if sprint.get("sprint_id") == sprint_id:
            excluded.append({**info, "reason": "current sprint rerun"})
            continue
        if sprint_start and (sprint.get("sprint_start") or "") > sprint_start:
            excluded.append({**info, "sprint_start": sprint.get("sprint_start"), "reason": "newer than current sprint"})
            continue
        by_sprint.setdefault(sprint.get("sprint_id"), []).append((path, art, sprint))

    for key, group in by_sprint.items():
        group.sort(key=lambda t: (is_latest_copy(t[0]), t[0]))
        entries.append(group[0])
        for path, _art, sprint in group[1:]:
            reason = "duplicate of the same sprint (latest copy)" if is_latest_copy(path) else "duplicate of the same sprint"
            excluded.append({"path": path, "sprint_id": sprint.get("sprint_id"),
                             "sprint_name": sprint.get("sprint_name"), "reason": reason})
    entries.sort(key=lambda e: (e[2].get("sprint_start") or "", str(e[2].get("sprint_id"))))
    return entries, excluded


def _history_section(result, definitions, current_kind, entries, excluded_files):
    """Per comparable metric: current, previous, historical average, and dated
    history. Only prior values whose recorded definition matches the current
    one are compared; null prior values and kind-mismatched delivery outcomes
    are excluded with reasons. The average uses included prior values only."""
    metrics = {}
    for path, definition in definitions.items():
        m = {
            "definition": definition,
            "current": _metric_value(result, path),
            "previous": None,
            "historical_average": None,
            "history": [],
            "excluded": [],
        }
        for _path, art, sprint in entries:
            prior = {
                "sprint_id": sprint.get("sprint_id"),
                "sprint_name": sprint.get("sprint_name"),
                "sprint_start": sprint.get("sprint_start"),
            }
            prior_defs = art.get("definitions")
            prior_definition = prior_defs.get(path) if isinstance(prior_defs, dict) else None
            if prior_definition is None:
                reason = ("prior analysis lacks metric definitions"
                          if prior_defs is None else "prior analysis lacks definition for this metric")
                m["excluded"].append({**prior, "reason": reason})
                continue
            if prior_definition != definition:
                m["excluded"].append({**prior, "reason": "incompatible metric definition"})
                continue
            value = _metric_value(art, path)
            if value is None:
                m["excluded"].append({**prior, "reason": "prior value null"})
                continue
            kind = art.get("observation_kind") or KIND_BY_STATE.get(sprint.get("sprint_state"), "unknown")
            if path in DELIVERY_OUTCOME_METRICS and kind != current_kind:
                m["excluded"].append({**prior, "reason": f"observation kind mismatch: {kind} vs {current_kind}"})
                continue
            m["history"].append({
                **prior,
                "sprint_end": sprint.get("sprint_end"),
                "observation_time": art.get("observation_time"),
                "observation_kind": kind,
                "value": value,
            })
        if m["history"]:
            m["previous"] = m["history"][-1]["value"]
            m["historical_average"] = sum(e["value"] for e in m["history"]) / len(m["history"])
        metrics[path] = m
    return {
        "sources": [
            {
                "path": path,
                "sprint_id": sprint.get("sprint_id"),
                "sprint_name": sprint.get("sprint_name"),
                "sprint_start": sprint.get("sprint_start"),
                "observation_time": art.get("observation_time"),
                "observation_kind": art.get("observation_kind")
                or KIND_BY_STATE.get(sprint.get("sprint_state"), "unknown"),
            }
            for path, art, sprint in entries
        ],
        "excluded": excluded_files,
        "metrics": metrics,
    }


def analyze(input_dir, output_path, snapshots_dir=None, history_dir=None):
    p = lambda *parts: os.path.join(input_dir, *parts)

    sprint = _load(p("sprint.json"))
    all_issues = _dedup(_load(p("all-issues.json")))
    all_index = {i["key"]: i for i in all_issues}
    total = len(all_issues)

    tax_pops = {}
    for name in TAXONOMY_NAMES:
        tax_pops[name] = _load_and_prepare(p("taxonomy", f"{name}.json"), all_index, f"taxonomy/{name}.json")

    tax_indices = {
        name: _keys(pop)
        for name, pop in tax_pops.items()
        if not _is_unavail(pop)
    }

    completed = _load_and_prepare(p("delivery", "completed.json"), all_index, "delivery/completed.json")
    incomplete = _load_and_prepare(p("delivery", "incomplete.json"), all_index, "delivery/incomplete.json")
    high_pri_inc = _load_and_prepare(p("delivery", "high-priority-incomplete.json"), all_index, "delivery/high-priority-incomplete.json")
    spillover = _load_pop(p("delivery", "spillover.json"))

    est_eligible = _load_and_prepare(p("estimation", "eligible.json"), all_index, "estimation/eligible.json")
    est_missing = _load_and_prepare(p("estimation", "missing.json"), all_index, "estimation/missing.json")
    est_within = _load_and_prepare(p("estimation", "within-tolerance.json"), all_index, "estimation/within-tolerance.json")
    est_over25 = _load_and_prepare(p("estimation", "over-25.json"), all_index, "estimation/over-25.json")
    est_over50 = _load_and_prepare(p("estimation", "over-50.json"), all_index, "estimation/over-50.json")
    est_over100 = _load_and_prepare(p("estimation", "over-100.json"), all_index, "estimation/over-100.json")

    flow_active = _load_and_prepare(p("flow", "active.json"), all_index, "flow/active.json")
    flow_aging2d = _load_and_prepare(p("flow", "aging-2d.json"), all_index, "flow/aging-2d.json")
    flow_aging4d = _load_and_prepare(p("flow", "aging-4d.json"), all_index, "flow/aging-4d.json")
    flow_aging7d = _load_and_prepare(p("flow", "aging-7d.json"), all_index, "flow/aging-7d.json")
    flow_stale = _load_pop(p("flow", "stale.json"))
    flow_blocked = _load_and_prepare(p("flow", "blocked.json"), all_index, "flow/blocked.json")
    flow_reopened = _load_and_prepare(p("flow", "reopened.json"), all_index, "flow/reopened.json")

    eligible_count = len(est_eligible) if not _is_unavail(est_eligible) else None

    incomplete_count = len(incomplete) if not _is_unavail(incomplete) else None
    incomplete_keys = _keys(incomplete) if not _is_unavail(incomplete) else set()

    availability = []
    for metric_path, pop in [
        ("delivery.spillover", spillover),
        ("flow.stale", flow_stale),
    ]:
        if _is_unavail(pop):
            availability.append({"metric": metric_path, "reason": pop["reason"], "unavailable": True})

    incomplete_taxonomy_intersections = {}
    if not _is_unavail(incomplete):
        for name, tax_pop in tax_pops.items():
            cat_count = len(tax_pop) if not _is_unavail(tax_pop) else None
            incomplete_taxonomy_intersections[name] = _intersect(
                incomplete, tax_pop, all_index, tax_indices, incomplete_count, cat_count
            )

    over25_taxonomy_intersections = {}
    if not _is_unavail(est_over25):
        over25_count = len(est_over25)
        for name, tax_pop in tax_pops.items():
            cat_count = len(tax_pop) if not _is_unavail(tax_pop) else None
            over25_taxonomy_intersections[name] = _intersect(
                est_over25, tax_pop, all_index, tax_indices, over25_count, cat_count
            )

    blocked_taxonomy_composition = {}
    if not _is_unavail(flow_blocked):
        blocked_count = len(flow_blocked)
        blocked_keys = _keys(flow_blocked)
        for name, tax_pop in tax_pops.items():
            if _is_unavail(tax_pop):
                blocked_taxonomy_composition[name] = {
                    "count": None, "denominator": None, "issues": None, "percentage": None,
                    "reason": tax_pop["reason"], "unavailable": True,
                }
            else:
                members = [i for i in tax_pop if i["key"] in blocked_keys]
                count = len(members)
                blocked_taxonomy_composition[name] = {
                    "count": count,
                    "denominator": blocked_count,
                    "issues": _evidence(members, all_index, tax_indices),
                    "percentage": count / blocked_count if blocked_count else None,
                }

    reopened_taxonomy_composition = {}
    if not _is_unavail(flow_reopened):
        reopened_count = len(flow_reopened)
        reopened_keys = _keys(flow_reopened)
        for name, tax_pop in tax_pops.items():
            if _is_unavail(tax_pop):
                reopened_taxonomy_composition[name] = {
                    "count": None, "denominator": None, "issues": None, "percentage": None,
                    "reason": tax_pop["reason"], "unavailable": True,
                }
            else:
                members = [i for i in tax_pop if i["key"] in reopened_keys]
                count = len(members)
                reopened_taxonomy_composition[name] = {
                    "count": count,
                    "denominator": reopened_count,
                    "issues": _evidence(members, all_index, tax_indices),
                    "percentage": count / reopened_count if reopened_count else None,
                }

    result = {
        "sprint": {
            "board_id": sprint["board_id"],
            "sprint_id": sprint["sprint_id"],
            "sprint_name": sprint["sprint_name"],
        },
        "observation_time": sprint["observation_time"],
        "delivery": {
            "total": total,
            "completed": _metric(completed, total, all_index, tax_indices),
            "high_priority_incomplete": _metric(high_pri_inc, total, all_index, tax_indices),
            "incomplete": {
                **_metric(incomplete, total, all_index, tax_indices),
                "composition": {
                    name: (
                        {
                            "count": None, "denominator": None, "issues": None, "percentage": None,
                            "reason": tax_pop["reason"], "unavailable": True,
                        }
                        if _is_unavail(tax_pop) else {
                            "count": len([i for i in tax_pop if i["key"] in incomplete_keys]),
                            "denominator": incomplete_count,
                            "issues": _evidence(
                                [i for i in tax_pop if i["key"] in incomplete_keys],
                                all_index, tax_indices,
                            ),
                            "percentage": (
                                len([i for i in tax_pop if i["key"] in incomplete_keys]) / incomplete_count
                                if incomplete_count else None
                            ),
                        }
                    )
                    for name, tax_pop in tax_pops.items()
                },
            },
            "spillover": _metric(spillover, None, all_index, tax_indices),
        },
        "estimation": {
            "eligible_count": eligible_count,
            "missing": _metric(est_missing, total, all_index, tax_indices),
            "over_100": _metric(est_over100, eligible_count, all_index, tax_indices),
            "over_25": _metric(est_over25, eligible_count, all_index, tax_indices),
            "over_50": _metric(est_over50, eligible_count, all_index, tax_indices),
            "within_tolerance": _metric(est_within, eligible_count, all_index, tax_indices),
        },
        "flow": {
            "active": _metric(flow_active, total, all_index, tax_indices),
            "aging_2d": _metric(flow_aging2d, total, all_index, tax_indices),
            "aging_4d": _metric(flow_aging4d, total, all_index, tax_indices),
            "aging_7d": _metric(flow_aging7d, total, all_index, tax_indices),
            "blocked": _metric(flow_blocked, total, all_index, tax_indices),
            "reopened": _metric(flow_reopened, total, all_index, tax_indices),
            "stale": _metric(flow_stale, None, all_index, tax_indices),
        },
        "friction": {
            "blocked": {
                **_metric(flow_blocked, total, all_index, tax_indices),
                "composition": blocked_taxonomy_composition,
            },
            "reopened": {
                **_metric(flow_reopened, total, all_index, tax_indices),
                "composition": reopened_taxonomy_composition,
            },
        },
        "taxonomy": {
            name: _metric(pop, total, all_index, tax_indices)
            for name, pop in tax_pops.items()
        },
        "intersections": {
            "incomplete_by_taxonomy": incomplete_taxonomy_intersections,
            "over_25_by_taxonomy": over25_taxonomy_intersections,
        },
        "availability": availability,
    }

    kind = KIND_BY_STATE.get(sprint.get("sprint_state"), "other")
    definitions = _metric_definitions()
    snaps = _load_snapshots(snapshots_dir, sprint.get("board_id"), sprint.get("sprint_id"))
    entries, excluded_files = _load_history(history_dir, sprint)

    result["definitions"] = definitions
    result["observation_kind"] = kind
    result["scope"] = _scope_section(all_issues, all_index, tax_indices, snaps,
                                     sprint.get("observation_time"))
    result["observations"] = _observations_section(
        snaps, sprint.get("observation_time"), sprint.get("sprint_state"),
        flow_active, flow_blocked, all_index, tax_indices,
    )
    result["history"] = _history_section(result, definitions, kind, entries, excluded_files)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)
        f.write("\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--snapshots", default=None, help="directory of earlier run-directory snapshots")
    parser.add_argument("--history", default=None, help="directory of earlier per-sprint analysis.json artifacts")
    args = parser.parse_args()
    analyze(args.input, args.output, snapshots_dir=args.snapshots, history_dir=args.history)


if __name__ == "__main__":
    main()
