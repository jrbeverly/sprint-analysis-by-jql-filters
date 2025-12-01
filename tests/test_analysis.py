import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import analyze

EXPERIMENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURES = os.path.join(EXPERIMENT_DIR, "fixtures", "sprint-42")
SNAPSHOTS_DIR = os.path.join(EXPERIMENT_DIR, "fixtures", "snapshots")
HISTORY_DIR = os.path.join(EXPERIMENT_DIR, "fixtures", "history")
FINAL_SNAPSHOT = os.path.join(SNAPSHOTS_DIR, "sprint-42", "2026-08-22T090000Z")

PUBLISH = os.path.join(EXPERIMENT_DIR, "publish.sh")
ACQUIRE = os.path.join(EXPERIMENT_DIR, "acquire.sh")
STUB = os.path.join(EXPERIMENT_DIR, "tests", "stub.sh")

SPRINT_DATA = {
    "board_id": 1,
    "sprint_id": 1,
    "sprint_name": "Test Sprint",
    "observation_time": "2026-01-01T00:00:00Z",
}

ISSUE = {
    "id": "1",
    "self": "https://example.atlassian.net/rest/agile/1.0/issue/1",
    "key": "TEST-1",
    "fields": {
        "summary": "Example issue",
        "status": {"name": "Done", "statusCategory": {"key": "done", "name": "Done"}},
        "priority": {"name": "Medium"},
        "issuetype": {"name": "Story"},
        "labels": [],
        "customfield_10016": None,
        "customfield_10028": None,
    },
}

UNAVAIL = {"unavailable": True, "reason": "test unavailable"}


def _read_json(path):
    with open(path) as f:
        return json.load(f)


def _run_publish(analysis_file, output_dir):
    return subprocess.run(
        ["bash", PUBLISH, analysis_file, output_dir],
        capture_output=True, text=True,
    )


def _write_analysis(path, sprint_id, observation_time, extra=None):
    art = {
        "sprint": {"board_id": 42, "sprint_id": sprint_id, "sprint_name": "Sprint %s" % sprint_id},
        "observation_time": observation_time,
        "delivery": {"total": 0},
    }
    art.update(extra or {})
    with open(path, "w") as f:
        json.dump(art, f, indent=2, sort_keys=True)
    return art


def _make_fixture(tmp, sprint=None, issues=None, overrides=None):
    for sub in ("delivery", "estimation", "flow", "taxonomy"):
        os.makedirs(os.path.join(tmp, sub), exist_ok=True)

    def w(rel, data):
        with open(os.path.join(tmp, rel), "w") as f:
            json.dump(data, f)

    w("sprint.json", sprint or SPRINT_DATA)
    w("all-issues.json", issues if issues is not None else [])

    defaults = {
        "delivery/completed.json": [],
        "delivery/incomplete.json": [],
        "delivery/high-priority-incomplete.json": [],
        "delivery/spillover.json": UNAVAIL,
        "estimation/eligible.json": [],
        "estimation/missing.json": [],
        "estimation/within-tolerance.json": [],
        "estimation/over-25.json": [],
        "estimation/over-50.json": [],
        "estimation/over-100.json": [],
        "flow/active.json": [],
        "flow/aging-2d.json": [],
        "flow/aging-4d.json": [],
        "flow/aging-7d.json": [],
        "flow/stale.json": UNAVAIL,
        "flow/blocked.json": [],
        "flow/reopened.json": [],
        "taxonomy/planned.json": [],
        "taxonomy/unplanned.json": [],
        "taxonomy/incident.json": [],
        "taxonomy/bug.json": [],
        "taxonomy/chore.json": [],
        "taxonomy/support.json": [],
        "taxonomy/responsibility.json": [],
    }
    for rel, default in defaults.items():
        data = (overrides or {}).get(rel, default)
        w(rel, data)


class TestTenIssueExample(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp()
        output = os.path.join(tmp, "analysis.json")
        analyze.analyze(FIXTURES, output)
        with open(output) as f:
            cls.r = json.load(f)

    def test_total_count(self):
        self.assertEqual(self.r["delivery"]["total"], 10)

    def test_completed_count(self):
        self.assertEqual(self.r["delivery"]["completed"]["count"], 6)

    def test_incomplete_count_and_rate(self):
        inc = self.r["delivery"]["incomplete"]
        self.assertEqual(inc["count"], 4)
        self.assertEqual(inc["denominator"], 10)
        self.assertAlmostEqual(inc["percentage"], 0.4)

    def test_incident_composition_count_and_rate(self):
        ic = self.r["delivery"]["incomplete"]["composition"]["incident"]
        self.assertEqual(ic["count"], 2)
        self.assertEqual(ic["denominator"], 4)
        self.assertAlmostEqual(ic["percentage"], 0.5)

    def test_incident_evidence_keys(self):
        issues = self.r["delivery"]["incomplete"]["composition"]["incident"]["issues"]
        self.assertEqual([i["key"] for i in issues], ["PLAT-108", "PLAT-109"])

    def test_incident_evidence_summaries(self):
        issues = self.r["delivery"]["incomplete"]["composition"]["incident"]["issues"]
        by_key = {i["key"]: i["summary"] for i in issues}
        self.assertEqual(by_key["PLAT-108"], "Resolve authentication service outage")
        self.assertEqual(by_key["PLAT-109"], "Fix broken login flow after deploy")

    def test_observation_time_from_input(self):
        self.assertEqual(self.r["observation_time"], "2026-08-18T09:00:00Z")

    def test_high_priority_incomplete_count(self):
        self.assertEqual(self.r["delivery"]["high_priority_incomplete"]["count"], 3)

    def test_high_priority_incomplete_keys(self):
        keys = [i["key"] for i in self.r["delivery"]["high_priority_incomplete"]["issues"]]
        self.assertEqual(keys, ["PLAT-107", "PLAT-108", "PLAT-109"])

    def test_spillover_unavailable(self):
        s = self.r["delivery"]["spillover"]
        self.assertTrue(s["unavailable"])
        self.assertIsNone(s["count"])
        self.assertIsNotNone(s["reason"])

    def test_estimation_eligible_count(self):
        self.assertEqual(self.r["estimation"]["eligible_count"], 4)

    def test_estimation_missing_count(self):
        m = self.r["estimation"]["missing"]
        self.assertEqual(m["count"], 6)
        self.assertEqual(m["denominator"], 10)
        self.assertAlmostEqual(m["percentage"], 0.6)

    def test_estimation_within_tolerance(self):
        w = self.r["estimation"]["within_tolerance"]
        self.assertEqual(w["count"], 2)
        self.assertEqual(w["denominator"], 4)
        self.assertAlmostEqual(w["percentage"], 0.5)

    def test_estimation_over_25(self):
        o = self.r["estimation"]["over_25"]
        self.assertEqual(o["count"], 2)
        self.assertEqual(o["denominator"], 4)
        self.assertAlmostEqual(o["percentage"], 0.5)

    def test_estimation_over_50(self):
        o = self.r["estimation"]["over_50"]
        self.assertEqual(o["count"], 1)
        self.assertEqual(o["denominator"], 4)
        self.assertAlmostEqual(o["percentage"], 0.25)

    def test_estimation_over_100(self):
        o = self.r["estimation"]["over_100"]
        self.assertEqual(o["count"], 1)
        self.assertEqual(o["denominator"], 4)
        self.assertAlmostEqual(o["percentage"], 0.25)

    def test_missing_keys_exact(self):
        keys = [i["key"] for i in self.r["estimation"]["missing"]["issues"]]
        self.assertEqual(keys, ["PLAT-104", "PLAT-105", "PLAT-107",
                                "PLAT-108", "PLAT-109", "PLAT-110"])

    def test_missing_evidence_distinguishes_no_estimate_from_no_actual(self):
        issues = {i["key"]: i for i in self.r["estimation"]["missing"]["issues"]}
        # Neither estimate nor actual is present.
        self.assertIsNone(issues["PLAT-104"]["estimate"])
        self.assertIsNone(issues["PLAT-104"]["actual"])
        # An estimate without a usable actual is still missing, not eligible.
        self.assertEqual(issues["PLAT-108"]["estimate"], 1)
        self.assertIsNone(issues["PLAT-108"]["actual"])
        self.assertEqual(issues["PLAT-110"]["estimate"], 3)
        self.assertIsNone(issues["PLAT-110"]["actual"])

    def test_nested_estimation_sets(self):
        keys25 = {i["key"] for i in self.r["estimation"]["over_25"]["issues"]}
        keys50 = {i["key"] for i in self.r["estimation"]["over_50"]["issues"]}
        keys100 = {i["key"] for i in self.r["estimation"]["over_100"]["issues"]}
        self.assertTrue(keys100.issubset(keys50))
        self.assertTrue(keys50.issubset(keys25))
        self.assertEqual(keys25, {"PLAT-101", "PLAT-106"})
        self.assertEqual(keys50, {"PLAT-106"})
        self.assertEqual(keys100, {"PLAT-106"})

    def test_evidence_fields_present(self):
        issue = self.r["estimation"]["over_25"]["issues"][0]
        self.assertIn("key", issue)
        self.assertIn("summary", issue)
        self.assertIn("estimate", issue)
        self.assertIn("actual", issue)
        self.assertIn("taxonomy", issue)

    def test_over_25_plat_101_evidence(self):
        issues = {i["key"]: i for i in self.r["estimation"]["over_25"]["issues"]}
        i = issues["PLAT-101"]
        self.assertEqual(i["estimate"], 3)
        self.assertEqual(i["actual"], 4)
        self.assertEqual(i["summary"], "Implement user authentication refresh")
        self.assertIn("planned", i["taxonomy"])

    def test_over_100_plat_106_evidence(self):
        issues = {i["key"]: i for i in self.r["estimation"]["over_100"]["issues"]}
        i = issues["PLAT-106"]
        self.assertEqual(i["estimate"], 2)
        self.assertEqual(i["actual"], 5)
        self.assertIn("planned", i["taxonomy"])

    def test_flow_active_count(self):
        self.assertEqual(self.r["flow"]["active"]["count"], 4)

    def test_flow_aging(self):
        self.assertEqual(self.r["flow"]["aging_2d"]["count"], 4)
        self.assertEqual(self.r["flow"]["aging_4d"]["count"], 2)
        self.assertEqual(self.r["flow"]["aging_7d"]["count"], 1)

    def test_flow_stale_unavailable(self):
        s = self.r["flow"]["stale"]
        self.assertTrue(s["unavailable"])
        self.assertIsNone(s["count"])

    def test_flow_blocked_issue(self):
        b = self.r["flow"]["blocked"]
        self.assertEqual(b["count"], 1)
        self.assertEqual(b["issues"][0]["key"], "PLAT-109")

    def test_flow_reopened_issue(self):
        ro = self.r["flow"]["reopened"]
        self.assertEqual(ro["count"], 1)
        self.assertEqual(ro["issues"][0]["key"], "PLAT-110")

    def test_taxonomy_counts(self):
        t = self.r["taxonomy"]
        self.assertEqual(t["planned"]["count"], 7)
        self.assertEqual(t["unplanned"]["count"], 3)
        self.assertEqual(t["incident"]["count"], 2)
        self.assertEqual(t["bug"]["count"], 3)
        self.assertEqual(t["chore"]["count"], 1)
        self.assertEqual(t["support"]["count"], 1)
        self.assertEqual(t["responsibility"]["count"], 1)

    def test_taxonomy_rates(self):
        t = self.r["taxonomy"]
        self.assertAlmostEqual(t["planned"]["percentage"], 0.7)
        self.assertAlmostEqual(t["unplanned"]["percentage"], 0.3)
        self.assertAlmostEqual(t["bug"]["percentage"], 0.3)

    def test_overlapping_taxonomy_plat_109(self):
        blocked_issues = {i["key"]: i for i in self.r["flow"]["blocked"]["issues"]}
        p109 = blocked_issues["PLAT-109"]
        self.assertIn("bug", p109["taxonomy"])
        self.assertIn("incident", p109["taxonomy"])
        self.assertIn("unplanned", p109["taxonomy"])

    def test_taxonomy_composition_does_not_sum_to_one(self):
        comp = self.r["delivery"]["incomplete"]["composition"]
        total = sum(
            c["percentage"] for c in comp.values()
            if c.get("percentage") is not None
        )
        self.assertGreater(total, 1.0)

    def test_intersection_incomplete_incident_composition(self):
        x = self.r["intersections"]["incomplete_by_taxonomy"]["incident"]["composition"]
        self.assertEqual(x["count"], 2)
        self.assertEqual(x["denominator"], 4)
        self.assertAlmostEqual(x["percentage"], 0.5)

    def test_intersection_incomplete_incident_category_rate(self):
        x = self.r["intersections"]["incomplete_by_taxonomy"]["incident"]["category_rate"]
        self.assertEqual(x["count"], 2)
        self.assertEqual(x["denominator"], 2)
        self.assertAlmostEqual(x["percentage"], 1.0)

    def test_intersection_incomplete_planned_composition(self):
        x = self.r["intersections"]["incomplete_by_taxonomy"]["planned"]["composition"]
        self.assertEqual(x["count"], 2)
        self.assertEqual(x["denominator"], 4)
        self.assertAlmostEqual(x["percentage"], 0.5)

    def test_intersection_incomplete_planned_category_rate(self):
        x = self.r["intersections"]["incomplete_by_taxonomy"]["planned"]["category_rate"]
        self.assertEqual(x["count"], 2)
        self.assertEqual(x["denominator"], 7)

    def test_friction_blocked_composition_incident(self):
        c = self.r["friction"]["blocked"]["composition"]["incident"]
        self.assertEqual(c["count"], 1)
        self.assertEqual(c["denominator"], 1)
        self.assertAlmostEqual(c["percentage"], 1.0)

    def test_friction_reopened_composition_bug(self):
        c = self.r["friction"]["reopened"]["composition"]["bug"]
        self.assertEqual(c["count"], 1)
        self.assertEqual(c["denominator"], 1)

    def test_availability_entries(self):
        avail = {a["metric"]: a for a in self.r["availability"]}
        self.assertIn("delivery.spillover", avail)
        self.assertIn("flow.stale", avail)
        self.assertTrue(avail["delivery.spillover"]["unavailable"])
        self.assertTrue(avail["flow.stale"]["unavailable"])

    def test_evidence_sorted_by_key(self):
        keys = [i["key"] for i in self.r["delivery"]["completed"]["issues"]]
        self.assertEqual(keys, sorted(keys))


class TestStrictThresholdBoundaries(unittest.TestCase):
    """Membership arithmetic at the exact estimation thresholds. The set files
    are supplied fixtures, so these checks prove the analyzer reproduces the
    supplied strict 'over' semantics (actual > k x estimate) and set nesting,
    not that Jira evaluates the queries."""

    BOUNDARIES = [
        ("BND-1", 8, 10),   # 10 == 8 * 1.25 exactly: within, not over-25
        ("BND-2", 2, 3),    # 3 == 2 * 1.5 exactly: over-25, not over-50
        ("BND-3", 5, 10),   # 10 == 5 * 2.0 exactly: over-50, not over-100
        ("BND-4", 2, 5),    # 5 > 2 * 2.0: over-100
    ]

    @classmethod
    def setUpClass(cls):
        def make(key, estimate, actual):
            return {
                "id": key,
                "self": "https://example.atlassian.net/rest/agile/1.0/issue/%s" % key,
                "key": key,
                "fields": {
                    "summary": "Boundary issue %s" % key,
                    "status": {"name": "Done", "statusCategory": {"key": "done", "name": "Done"}},
                    "priority": {"name": "Medium"},
                    "issuetype": {"name": "Story"},
                    "labels": [],
                    "customfield_10016": estimate,
                    "customfield_10028": actual,
                },
            }

        issues = [make(key, estimate, actual) for key, estimate, actual in cls.BOUNDARIES]
        by_key = {i["key"]: i for i in issues}
        sets = {
            "estimation/eligible.json": issues,
            "estimation/within-tolerance.json": [by_key["BND-1"]],
            "estimation/over-25.json": [by_key["BND-2"], by_key["BND-3"], by_key["BND-4"]],
            "estimation/over-50.json": [by_key["BND-3"], by_key["BND-4"]],
            "estimation/over-100.json": [by_key["BND-4"]],
        }
        cls.tmp = tempfile.mkdtemp()
        _make_fixture(cls.tmp, issues=issues, overrides=sets)
        output = os.path.join(cls.tmp, "out.json")
        analyze.analyze(cls.tmp, output)
        with open(output) as f:
            cls.r = json.load(f)

    def _keys(self, metric):
        return {i["key"] for i in self.r["estimation"][metric]["issues"]}

    def test_exact_1_25_boundary_is_within_not_over_25(self):
        self.assertEqual(self._keys("within_tolerance"), {"BND-1"})
        self.assertNotIn("BND-1", self._keys("over_25"))

    def test_exact_1_5_boundary_is_over_25_not_over_50(self):
        self.assertIn("BND-2", self._keys("over_25"))
        self.assertNotIn("BND-2", self._keys("over_50"))

    def test_exact_2_0_boundary_is_over_50_not_over_100(self):
        self.assertIn("BND-3", self._keys("over_50"))
        self.assertNotIn("BND-3", self._keys("over_100"))

    def test_only_ratio_above_two_is_over_100(self):
        self.assertEqual(self._keys("over_100"), {"BND-4"})

    def test_nested_sets(self):
        keys25 = self._keys("over_25")
        keys50 = self._keys("over_50")
        keys100 = self._keys("over_100")
        self.assertTrue(keys100.issubset(keys50))
        self.assertTrue(keys50.issubset(keys25))
        self.assertEqual(keys25, {"BND-2", "BND-3", "BND-4"})
        self.assertEqual(keys50, {"BND-3", "BND-4"})

    def test_within_disjoint_from_over(self):
        self.assertTrue(self._keys("within_tolerance").isdisjoint(self._keys("over_25")))

    def test_percentages_over_eligible_population(self):
        e = self.r["estimation"]
        self.assertEqual(e["eligible_count"], 4)
        self.assertAlmostEqual(e["within_tolerance"]["percentage"], 0.25)
        self.assertAlmostEqual(e["over_25"]["percentage"], 0.75)
        self.assertAlmostEqual(e["over_50"]["percentage"], 0.5)
        self.assertAlmostEqual(e["over_100"]["percentage"], 0.25)
        for metric in ("within_tolerance", "over_25", "over_50", "over_100"):
            self.assertEqual(e[metric]["denominator"], 4)

    def test_boundary_evidence_carries_values(self):
        e = self.r["estimation"]
        within = {i["key"]: i for i in e["within_tolerance"]["issues"]}
        self.assertEqual(within["BND-1"]["estimate"], 8)
        self.assertEqual(within["BND-1"]["actual"], 10)
        over50 = {i["key"]: i for i in e["over_50"]["issues"]}
        self.assertEqual(over50["BND-3"]["estimate"], 5)
        self.assertEqual(over50["BND-3"]["actual"], 10)


class TestEmptySprint(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        _make_fixture(cls.tmp, issues=[])
        output = os.path.join(cls.tmp, "out.json")
        analyze.analyze(cls.tmp, output)
        with open(output) as f:
            cls.r = json.load(f)

    def test_total_zero(self):
        self.assertEqual(self.r["delivery"]["total"], 0)

    def test_completed_zero_denominator_null_percentage(self):
        self.assertEqual(self.r["delivery"]["completed"]["count"], 0)
        self.assertIsNone(self.r["delivery"]["completed"]["percentage"])

    def test_estimation_eligible_count_zero(self):
        self.assertEqual(self.r["estimation"]["eligible_count"], 0)

    def test_estimation_over_25_null_percentage(self):
        o = self.r["estimation"]["over_25"]
        self.assertEqual(o["count"], 0)
        self.assertEqual(o["denominator"], 0)
        self.assertIsNone(o["percentage"])

    def test_taxonomy_null_percentage_on_zero_total(self):
        for name in ("planned", "unplanned", "incident", "bug"):
            with self.subTest(name=name):
                self.assertIsNone(self.r["taxonomy"][name]["percentage"])


class TestUnavailablePopulation(unittest.TestCase):

    def test_unavailable_has_reason_and_null_fields(self):
        r = analyze._metric(UNAVAIL, None, {}, {})
        self.assertTrue(r["unavailable"])
        self.assertIsNotNone(r["reason"])
        self.assertIsNone(r["count"])
        self.assertIsNone(r["denominator"])
        self.assertIsNone(r["percentage"])
        self.assertIsNone(r["issues"])

    def test_spillover_unavailable_in_fixture(self):
        tmp = tempfile.mkdtemp()
        _make_fixture(tmp, issues=[])
        output = os.path.join(tmp, "out.json")
        analyze.analyze(tmp, output)
        with open(output) as f:
            r = json.load(f)
        self.assertTrue(r["delivery"]["spillover"]["unavailable"])
        self.assertIsNone(r["delivery"]["spillover"]["count"])
        self.assertIsNotNone(r["delivery"]["spillover"]["reason"])


class TestMissingRequiredFile(unittest.TestCase):

    def test_missing_all_json_raises(self):
        tmp = tempfile.mkdtemp()
        os.makedirs(os.path.join(tmp, "delivery"))
        with open(os.path.join(tmp, "sprint.json"), "w") as f:
            json.dump(SPRINT_DATA, f)
        with self.assertRaises(FileNotFoundError):
            analyze.analyze(tmp, os.path.join(tmp, "out.json"))

    def test_missing_sprint_json_raises(self):
        tmp = tempfile.mkdtemp()
        with open(os.path.join(tmp, "all-issues.json"), "w") as f:
            json.dump([], f)
        with self.assertRaises(FileNotFoundError):
            analyze.analyze(tmp, os.path.join(tmp, "out.json"))

    def test_missing_population_file_raises(self):
        tmp = tempfile.mkdtemp()
        _make_fixture(tmp, issues=[])
        os.remove(os.path.join(tmp, "delivery", "completed.json"))
        with self.assertRaises(FileNotFoundError):
            analyze.analyze(tmp, os.path.join(tmp, "out.json"))


class TestOutOfBoundsKey(unittest.TestCase):

    def test_key_not_in_all_raises(self):
        tmp = tempfile.mkdtemp()
        issues = [dict(ISSUE)]
        outsider = {
            "id": "999",
            "self": "https://example.atlassian.net/rest/agile/1.0/issue/999",
            "key": "TEST-999",
            "fields": dict(ISSUE["fields"]),
        }
        _make_fixture(tmp, issues=issues, overrides={
            "delivery/completed.json": [outsider],
        })
        with self.assertRaises(ValueError):
            analyze.analyze(tmp, os.path.join(tmp, "out.json"))


class TestDeduplication(unittest.TestCase):

    def test_dedup_removes_duplicates(self):
        duped = [dict(ISSUE), dict(ISSUE)]
        result = analyze._dedup(duped)
        self.assertEqual(len(result), 1)

    def test_dedup_preserves_first_occurrence(self):
        a = {**ISSUE, "key": "A-1", "fields": {**ISSUE["fields"], "summary": "first"}}
        b = {**ISSUE, "key": "A-1", "fields": {**ISSUE["fields"], "summary": "second"}}
        result = analyze._dedup([a, b])
        self.assertEqual(result[0]["fields"]["summary"], "first")

    def test_dedup_preserves_distinct_keys(self):
        a = {**ISSUE, "key": "A-1"}
        b = {**ISSUE, "key": "A-2"}
        result = analyze._dedup([a, b])
        self.assertEqual(len(result), 2)


class TestDeterministicReplay(unittest.TestCase):

    def test_same_input_produces_identical_output(self):
        out1 = os.path.join(tempfile.mkdtemp(), "a.json")
        out2 = os.path.join(tempfile.mkdtemp(), "b.json")
        analyze.analyze(FIXTURES, out1)
        analyze.analyze(FIXTURES, out2)
        with open(out1) as f:
            r1 = f.read()
        with open(out2) as f:
            r2 = f.read()
        self.assertEqual(r1, r2)


class TestSnapshotComparison(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp()
        output = os.path.join(tmp, "analysis.json")
        analyze.analyze(FIXTURES, output, snapshots_dir=SNAPSHOTS_DIR, history_dir=HISTORY_DIR)
        with open(output) as f:
            cls.r = json.load(f)

    def test_observation_kind_in_progress(self):
        self.assertEqual(self.r["observation_kind"], "in_progress")

    def test_scope_added_keys_exact(self):
        self.assertTrue(self.r["scope"]["available"])
        self.assertEqual(self.r["scope"]["added"]["keys"], ["PLAT-108", "PLAT-109", "PLAT-110"])
        self.assertEqual(self.r["scope"]["added"]["count"], 3)

    def test_scope_removed_keys_exact(self):
        self.assertEqual(self.r["scope"]["removed"]["keys"], ["PLAT-111", "PLAT-112"])
        self.assertEqual(self.r["scope"]["removed"]["count"], 2)

    def test_scope_added_evidence(self):
        issues = {i["key"]: i for i in self.r["scope"]["added"]["issues"]}
        self.assertEqual(issues["PLAT-108"]["summary"], "Resolve authentication service outage")
        self.assertEqual(issues["PLAT-110"]["summary"], "Handle payment gateway timeout errors")
        self.assertIn("unplanned", issues["PLAT-108"]["taxonomy"])
        self.assertIn("incident", issues["PLAT-108"]["taxonomy"])
        self.assertIn("planned", issues["PLAT-110"]["taxonomy"])

    def test_scope_removed_evidence_from_baseline_snapshot(self):
        issues = {i["key"]: i for i in self.r["scope"]["removed"]["issues"]}
        self.assertEqual(issues["PLAT-111"]["summary"], "Replace legacy caching layer")
        self.assertEqual(issues["PLAT-112"]["summary"], "Upgrade database client drivers")
        self.assertEqual(issues["PLAT-111"]["estimate"], 8)
        self.assertEqual(issues["PLAT-111"]["taxonomy"], ["planned"])

    def test_added_kept_separate_from_unplanned(self):
        self.assertEqual(self.r["scope"]["added_unplanned_keys"], ["PLAT-108", "PLAT-109"])
        self.assertEqual(self.r["scope"]["added_not_unplanned_keys"], ["PLAT-110"])
        # PLAT-104 is unplanned in Jira but was present at sprint start, so it
        # is not added-since-start: the two sets are independent.
        unplanned_keys = {i["key"] for i in self.r["taxonomy"]["unplanned"]["issues"]}
        self.assertIn("PLAT-104", unplanned_keys)
        self.assertNotIn("PLAT-104", self.r["scope"]["added"]["keys"])

    def test_removed_outside_current_population(self):
        removed = set(self.r["scope"]["removed"]["keys"])
        taxonomy_keys = set()
        for metric in self.r["taxonomy"].values():
            for i in (metric.get("issues") or []):
                taxonomy_keys.add(i["key"])
        self.assertTrue(removed.isdisjoint(taxonomy_keys))
        completed_keys = {i["key"] for i in self.r["delivery"]["completed"]["issues"]}
        self.assertTrue(removed.isdisjoint(completed_keys))

    def test_blocked_timeline_exact(self):
        obs = self.r["observations"]["blocked"]["observations"]
        self.assertEqual([o["observation_time"] for o in obs], [
            "2026-08-11T09:00:00Z", "2026-08-14T09:00:00Z", "2026-08-18T09:00:00Z",
        ])
        self.assertEqual([o["keys"] for o in obs], [[], ["PLAT-108"], ["PLAT-109"]])

    def test_active_timeline_exact(self):
        obs = self.r["observations"]["active"]["observations"]
        self.assertEqual([o["keys"] for o in obs], [
            ["PLAT-107"],
            ["PLAT-106", "PLAT-107", "PLAT-108", "PLAT-109", "PLAT-111", "PLAT-112"],
            ["PLAT-107", "PLAT-108", "PLAT-109", "PLAT-110"],
        ])

    def test_timeline_excludes_future_observations(self):
        obs = self.r["observations"]["blocked"]["observations"]
        self.assertNotIn("2026-08-22T09:00:00Z", [o["observation_time"] for o in obs])

    def test_blocked_timeline_evidence(self):
        middle = self.r["observations"]["blocked"]["observations"][1]
        self.assertEqual([i["key"] for i in middle["evidence"]], ["PLAT-108"])
        self.assertEqual(middle["evidence"][0]["summary"], "Resolve authentication service outage")

    def test_observations_limits(self):
        self.assertIn("exact transition times",
                      self.r["observations"]["blocked"]["limits"][0])
        self.assertIn("uninterrupted active duration",
                      self.r["observations"]["active"]["limits"][1])

    def test_history_ordered_by_sprint_date_not_numeric_id(self):
        history = self.r["history"]["metrics"]["flow.blocked"]["history"]
        # Sprint 41 has the numerically smaller ID (400 < 410) but started
        # later, so it must come second.
        self.assertEqual([h["sprint_id"] for h in history], [410, 400])
        self.assertEqual([h["sprint_name"] for h in history],
                         ["Platform Sprint 40", "Platform Sprint 41"])

    def test_history_excludes_latest_duplicate(self):
        excluded = self.r["history"]["excluded"]
        dup = [e for e in excluded if e["path"].endswith(os.path.join("latest", "analysis.json"))]
        self.assertEqual(len(dup), 1)
        self.assertIn("duplicate", dup[0]["reason"])
        history = self.r["history"]["metrics"]["flow.blocked"]["history"]
        self.assertEqual(len(history), 2)

    def test_history_excludes_current_sprint_rerun(self):
        rerun = [e for e in self.r["history"]["excluded"] if e.get("sprint_id") == 420]
        self.assertEqual(len(rerun), 1)
        self.assertEqual(rerun[0]["reason"], "current sprint rerun")

    def test_history_excludes_other_board(self):
        other = [e for e in self.r["history"]["excluded"] if e.get("board_id") == 99]
        self.assertEqual(len(other), 1)
        self.assertEqual(other[0]["reason"], "different board")

    def test_history_sources_are_dated(self):
        sources = self.r["history"]["sources"]
        self.assertEqual([s["sprint_name"] for s in sources],
                         ["Platform Sprint 40", "Platform Sprint 41"])
        for s in sources:
            self.assertIn("sprint_start", s)
            self.assertIn("observation_time", s)

    def test_trend_blocked_independently_calculated(self):
        m = self.r["history"]["metrics"]["flow.blocked"]
        self.assertEqual(m["current"], 0.1)
        self.assertEqual(m["previous"], 0.2)
        self.assertEqual([h["value"] for h in m["history"]], [0.1, 0.2])
        self.assertAlmostEqual(m["historical_average"], (0.1 + 0.2) / 2)

    def test_trend_incident_independently_calculated(self):
        m = self.r["history"]["metrics"]["taxonomy.incident"]
        self.assertEqual(m["current"], 0.2)
        self.assertEqual(m["previous"], 0.15)
        self.assertEqual([h["value"] for h in m["history"]], [0.1, 0.15])
        self.assertAlmostEqual(m["historical_average"], (0.1 + 0.15) / 2)

    def test_null_prior_skipped_from_average(self):
        m = self.r["history"]["metrics"]["estimation.over_100"]
        self.assertEqual([h["sprint_name"] for h in m["history"]], ["Platform Sprint 41"])
        self.assertEqual([h["value"] for h in m["history"]], [0.0])
        self.assertEqual(m["previous"], 0.0)
        self.assertEqual(m["historical_average"], 0.0)
        reasons = [e["reason"] for e in m["excluded"]]
        self.assertEqual(reasons, ["prior value null"])

    def test_all_null_priors_mean_empty_history_and_null_comparisons(self):
        m = self.r["history"]["metrics"]["flow.aging_7d"]
        self.assertEqual(m["history"], [])
        self.assertIsNone(m["previous"])
        self.assertIsNone(m["historical_average"])
        self.assertEqual(m["current"], 0.1)
        self.assertEqual(len(m["excluded"]), 2)

    def test_incompatible_definition_not_silently_compared(self):
        m = self.r["history"]["metrics"]["taxonomy.unplanned"]
        self.assertEqual([h["sprint_name"] for h in m["history"]], ["Platform Sprint 40"])
        self.assertEqual(m["previous"], 0.2)
        reasons = {e["sprint_name"]: e["reason"] for e in m["excluded"]}
        self.assertEqual(reasons["Platform Sprint 41"], "incompatible metric definition")

    def test_delivery_outcomes_not_compared_across_kinds(self):
        m = self.r["history"]["metrics"]["delivery.completed"]
        self.assertEqual(m["history"], [])
        self.assertIsNone(m["previous"])
        self.assertIsNone(m["historical_average"])
        self.assertEqual(m["current"], 0.6)
        for e in m["excluded"]:
            self.assertIn("observation kind mismatch", e["reason"])

    def test_flow_metrics_compare_across_kinds(self):
        m = self.r["history"]["metrics"]["flow.blocked"]
        self.assertEqual(len(m["history"]), 2)
        self.assertEqual(m["excluded"], [])

    def test_definitions_recorded(self):
        d = self.r["definitions"]
        self.assertEqual(d["flow.blocked"], {
            "numerator": "count(flow/blocked.json)",
            "denominator": "count(all-issues.json)",
            "unit": "fraction",
        })
        self.assertEqual(d["estimation.over_25"]["denominator"], "count(estimation/eligible.json)")
        self.assertEqual(d["delivery.completed"]["numerator"], "count(delivery/completed.json)")


class TestNoHistoryNoSnapshots(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp()
        output = os.path.join(tmp, "analysis.json")
        analyze.analyze(FIXTURES, output)
        with open(output) as f:
            cls.r = json.load(f)

    def test_scope_unavailable_without_start_snapshot(self):
        self.assertFalse(self.r["scope"]["available"])
        self.assertIn("scope change unavailable", self.r["scope"]["reason"])

    def test_history_empty_and_null_comparisons(self):
        m = self.r["history"]["metrics"]["delivery.completed"]
        self.assertEqual(m["history"], [])
        self.assertIsNone(m["previous"])
        self.assertIsNone(m["historical_average"])
        self.assertEqual(m["current"], 0.6)
        self.assertEqual(self.r["history"]["sources"], [])
        self.assertEqual(self.r["history"]["excluded"], [])

    def test_observations_current_only(self):
        obs = self.r["observations"]["blocked"]["observations"]
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0]["observation_time"], "2026-08-18T09:00:00Z")
        self.assertEqual(obs[0]["keys"], ["PLAT-109"])


class TestFinalSnapshot(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        tmp = tempfile.mkdtemp()
        output = os.path.join(tmp, "analysis.json")
        analyze.analyze(FINAL_SNAPSHOT, output, snapshots_dir=SNAPSHOTS_DIR, history_dir=HISTORY_DIR)
        with open(output) as f:
            cls.r = json.load(f)

    def test_observation_kind_final(self):
        self.assertEqual(self.r["observation_kind"], "final")

    def test_delivery_history_included_for_final(self):
        m = self.r["history"]["metrics"]["delivery.completed"]
        self.assertEqual([h["value"] for h in m["history"]], [0.8, 0.75])
        self.assertEqual(m["previous"], 0.75)
        self.assertAlmostEqual(m["historical_average"], (0.8 + 0.75) / 2)
        self.assertEqual(m["current"], 0.7)

    def test_final_blocked_timeline_ends_with_final(self):
        obs = self.r["observations"]["blocked"]["observations"]
        self.assertEqual([o["observation_time"] for o in obs], [
            "2026-08-11T09:00:00Z", "2026-08-14T09:00:00Z", "2026-08-22T09:00:00Z",
        ])
        self.assertEqual([o["keys"] for o in obs], [[], ["PLAT-108"], ["PLAT-109"]])
        self.assertEqual(obs[-1]["sprint_state"], "closed")

    def test_final_scope_matches_current(self):
        self.assertEqual(self.r["scope"]["added"]["keys"], ["PLAT-108", "PLAT-109", "PLAT-110"])
        self.assertEqual(self.r["scope"]["removed"]["keys"], ["PLAT-111", "PLAT-112"])

    def test_final_spillover_available(self):
        self.assertEqual(self.r["delivery"]["spillover"]["count"], 3)


class TestPublish(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.out = os.path.join(self.tmp, "analysis")
        self.analysis_file = os.path.join(self.tmp, "input.json")
        self.art = _write_analysis(self.analysis_file, 42, "2026-08-18T09:00:00Z",
                                   extra={"delivery": {"total": 10}})

    def _paths(self, sprint_id=None, obs=None):
        sprint_id = self.art["sprint"]["sprint_id"] if sprint_id is None else sprint_id
        obs = self.art["observation_time"] if obs is None else obs
        sprint_dir = os.path.join(self.out, "sprints", str(sprint_id))
        return (
            os.path.join(sprint_dir, "snapshots", "%s.json" % obs),
            os.path.join(sprint_dir, "analysis.json"),
            os.path.join(self.out, "latest", "analysis.json"),
        )

    def test_publishes_three_artifacts_with_same_content(self):
        r = _run_publish(self.analysis_file, self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        for path in self._paths():
            self.assertTrue(os.path.isfile(path), path)
            self.assertEqual(_read_json(path), self.art)

    def test_publishing_sprint_43_leaves_sprint_42_intact(self):
        self.assertEqual(_run_publish(self.analysis_file, self.out).returncode, 0)
        snap42, cur42, _ = self._paths()
        art43_file = os.path.join(self.tmp, "input43.json")
        art43 = _write_analysis(art43_file, 43, "2026-08-25T09:00:00Z",
                                extra={"delivery": {"total": 8}})
        r = _run_publish(art43_file, self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        snap43, cur43, latest = self._paths(43, "2026-08-25T09:00:00Z")
        self.assertEqual(_read_json(snap42), self.art)
        self.assertEqual(_read_json(cur42), self.art)
        self.assertEqual(_read_json(snap43), art43)
        self.assertEqual(_read_json(cur43), art43)
        self.assertEqual(_read_json(latest), art43)

    def test_identical_rerun_reuses_observation(self):
        self.assertEqual(_run_publish(self.analysis_file, self.out).returncode, 0)
        r = _run_publish(self.analysis_file, self.out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("reusing identical observation", r.stdout)
        for path in self._paths():
            self.assertEqual(_read_json(path), self.art)

    def test_differing_content_at_same_timestamp_fails_without_touching_files(self):
        self.assertEqual(_run_publish(self.analysis_file, self.out).returncode, 0)
        clash_file = os.path.join(self.tmp, "clash.json")
        clash = _write_analysis(clash_file, 42, "2026-08-18T09:00:00Z",
                                extra={"delivery": {"total": 99}})
        before = [_read_json(p) for p in self._paths()]
        r = _run_publish(clash_file, self.out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("different content", r.stderr)
        after = [_read_json(p) for p in self._paths()]
        self.assertEqual(before, after)
        self.assertNotIn(clash, after)

    def test_invalid_json_leaves_published_files_untouched(self):
        self.assertEqual(_run_publish(self.analysis_file, self.out).returncode, 0)
        bad = os.path.join(self.tmp, "bad.json")
        with open(bad, "w") as f:
            f.write("{not-valid-json")
        before = [_read_json(p) for p in self._paths()]
        r = _run_publish(bad, self.out)
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(before, [_read_json(p) for p in self._paths()])

    def test_incomplete_json_leaves_published_files_untouched(self):
        self.assertEqual(_run_publish(self.analysis_file, self.out).returncode, 0)
        before = [_read_json(p) for p in self._paths()]
        cases = [
            {},
            {"sprint": {"sprint_id": 42}},
            {"observation_time": "2026-08-18T09:00:00Z"},
            {"sprint": {}, "observation_time": "2026-08-18T09:00:00Z"},
            {"sprint": {"sprint_id": None}, "observation_time": "2026-08-18T09:00:00Z"},
        ]
        for content in cases:
            with self.subTest(content=content):
                incomplete = os.path.join(self.tmp, "incomplete.json")
                with open(incomplete, "w") as f:
                    json.dump(content, f)
                r = _run_publish(incomplete, self.out)
                self.assertNotEqual(r.returncode, 0)
                self.assertEqual(before, [_read_json(p) for p in self._paths()])

    def test_missing_analysis_file_fails_without_creating_output(self):
        r = _run_publish(os.path.join(self.tmp, "nope.json"), self.out)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(self.out))

    def test_historical_replay_separate_directory_does_not_move_latest_backward(self):
        self.assertEqual(_run_publish(self.analysis_file, self.out).returncode, 0)
        art43_file = os.path.join(self.tmp, "input43.json")
        art43 = _write_analysis(art43_file, 43, "2026-08-25T09:00:00Z",
                                extra={"delivery": {"total": 8}})
        self.assertEqual(_run_publish(art43_file, self.out).returncode, 0)
        replay_out = os.path.join(self.tmp, "replay")
        r = _run_publish(self.analysis_file, replay_out)
        self.assertEqual(r.returncode, 0, r.stderr)
        for path in (
            os.path.join(replay_out, "sprints", "42", "snapshots", "2026-08-18T09:00:00Z.json"),
            os.path.join(replay_out, "sprints", "42", "analysis.json"),
            os.path.join(replay_out, "latest", "analysis.json"),
        ):
            self.assertEqual(_read_json(path), self.art)
        # The main directory is untouched by the replay: latest stays at 43.
        snap42, cur42, latest = self._paths()
        self.assertEqual(_read_json(latest), art43)
        self.assertEqual(_read_json(snap42), self.art)
        self.assertEqual(_read_json(cur42), self.art)

    def test_out_of_order_publication_does_not_move_latest_backward(self):
        art43_file = os.path.join(self.tmp, "input43.json")
        art43 = _write_analysis(art43_file, 43, "2026-08-25T09:00:00Z",
                                extra={"delivery": {"total": 8}})
        self.assertEqual(_run_publish(art43_file, self.out).returncode, 0)
        cur43, latest = self._paths(43, "2026-08-25T09:00:00Z")[1:]
        r = _run_publish(self.analysis_file, self.out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("backward", r.stderr)
        self.assertEqual(_read_json(latest), art43)
        self.assertEqual(_read_json(cur43), art43)
        self.assertFalse(os.path.exists(os.path.join(self.out, "sprints", "42")))


class TestIntegratedCapturePublication(unittest.TestCase):
    """End to end through the shell ACLI stub, analysis, and publication."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        sprints = os.path.join(self.tmp, "sprints.json")
        with open(sprints, "w") as f:
            json.dump([{
                "id": 420, "name": "Sprint 42", "state": "active",
                "startDate": "2026-08-11T00:00:00.000Z",
                "endDate": "2026-08-22T00:00:00.000Z",
            }], f)
        self.env = os.environ.copy()
        self.env.pop("SPRINT_ID", None)
        self.env.update({
            "JIRA_BOARD_ID": "42",
            "ACLI": STUB,
            "STUB_LOG": os.path.join(self.tmp, "stub.log"),
            "STUB_SPRINTS_FILE": sprints,
            "STUB_ISSUES_FILE": os.path.join(FIXTURES, "all-issues.json"),
        })

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)
        # acquire.sh writes run directories inside the experiment; remove them.
        shutil.rmtree(os.path.join(EXPERIMENT_DIR, "runs"), ignore_errors=True)

    def _acquire(self, extra_env=None):
        env = dict(self.env)
        env.update(extra_env or {})
        return subprocess.run(["bash", ACQUIRE], capture_output=True, text=True, env=env)

    def test_acquire_analyze_publish_produces_all_three_artifacts(self):
        r = self._acquire()
        self.assertEqual(r.returncode, 0, r.stderr)
        run_dir = r.stdout.strip()
        sprint = _read_json(os.path.join(run_dir, "sprint.json"))
        analysis_file = os.path.join(self.tmp, "analysis.json")
        analyze.analyze(run_dir, analysis_file)
        expected = _read_json(analysis_file)
        out = os.path.join(self.tmp, "published")
        pub = _run_publish(analysis_file, out)
        self.assertEqual(pub.returncode, 0, pub.stderr)
        sprint_id = str(sprint["sprint_id"])
        obs = sprint["observation_time"]
        for path in (
            os.path.join(out, "sprints", sprint_id, "snapshots", "%s.json" % obs),
            os.path.join(out, "sprints", sprint_id, "analysis.json"),
            os.path.join(out, "latest", "analysis.json"),
        ):
            self.assertTrue(os.path.isfile(path), path)
            self.assertEqual(_read_json(path), expected)
        self.assertEqual(expected["sprint"]["sprint_id"], 420)
        self.assertEqual(expected["delivery"]["total"], 10)

    def test_failed_acquisition_leaves_published_files_untouched(self):
        out = os.path.join(self.tmp, "published")
        os.makedirs(os.path.join(out, "latest"))
        sentinel = os.path.join(out, "latest", "analysis.json")
        with open(sentinel, "w") as f:
            json.dump({"sentinel": True}, f)
        r = self._acquire({"STUB_FAIL_ON": "list-workitems"})
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(_read_json(sentinel), {"sentinel": True})
        # The partial run directory was removed; no run survives to analyze.
        runs = os.path.join(EXPERIMENT_DIR, "runs")
        self.assertEqual(os.listdir(runs) if os.path.isdir(runs) else [], [])

    def test_failed_analysis_leaves_published_files_untouched(self):
        r = self._acquire()
        self.assertEqual(r.returncode, 0, r.stderr)
        run_dir = r.stdout.strip()
        os.remove(os.path.join(run_dir, "delivery", "completed.json"))
        analysis_file = os.path.join(self.tmp, "analysis.json")
        with self.assertRaises(FileNotFoundError):
            analyze.analyze(run_dir, analysis_file)
        self.assertFalse(os.path.exists(analysis_file))
        out = os.path.join(self.tmp, "published")
        pub = _run_publish(analysis_file, out)
        self.assertNotEqual(pub.returncode, 0)
        self.assertFalse(os.path.exists(out))
