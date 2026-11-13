import math, os, pathlib, unittest

os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/quality-watch-unit.sqlite")
os.environ.setdefault("TASK_MODE", "inline")
_db = pathlib.Path("/tmp/quality-watch-unit.sqlite")
_db.unlink(missing_ok=True)

from src.utils import repository as repo
from src.services.ewma import baseline_statistics, ewma_series
from src.services.results import upgrade_result
from src.services.specs import apply_segment, ensure_sample_coverage, normalize_segments
from src.services.statistics import analyze


BASELINE = {"id": "b1", "machine": "LS-01", "mean": 20.0, "sigma": 0.009}


class SpecPartitionTests(unittest.TestCase):
 def test_legacy_single_spec_normalizes_to_one_segment(self):
  study = {"id": "s1", "monitoring_start": 61, "monitoring_end": 200, "lsl": 19.95, "usl": 20.05}
  segments = normalize_segments(study)
  self.assertEqual(len(segments), 1)
  self.assertEqual((segments[0]["start"], segments[0]["end"]), (61, 200))
  self.assertEqual((segments[0]["lsl"], segments[0]["usl"]), (19.95, 20.05))

 def test_overlapping_segments_rejected(self):
  study = {"id": "s2", "monitoring_start": 61, "monitoring_end": 200, "spec_segments": [
   {"version": "A", "start": 61, "end": 140, "lsl": 19.9, "usl": 20.1},
   {"version": "B", "start": 140, "end": 200, "lsl": 19.95, "usl": 20.05}]}
  with self.assertRaises(ValueError) as ctx: normalize_segments(study)
  self.assertIn("重叠", str(ctx.exception))

 def test_gap_in_coverage_rejected(self):
  study = {"id": "s3", "monitoring_start": 61, "monitoring_end": 200, "spec_segments": [
   {"version": "A", "start": 61, "end": 130, "lsl": 19.9, "usl": 20.1},
   {"version": "B", "start": 135, "end": 200, "lsl": 19.95, "usl": 20.05}]}
  with self.assertRaises(ValueError) as ctx: normalize_segments(study)
  self.assertIn("漏盖", str(ctx.exception))

 def test_partition_must_span_monitoring_interval(self):
  for segments in ([{"version": "A", "start": 61, "end": 199, "lsl": 19.9, "usl": 20.1}],
                   [{"version": "A", "start": 70, "end": 200, "lsl": 19.9, "usl": 20.1}]):
   with self.assertRaises(ValueError): normalize_segments({"monitoring_start": 61, "monitoring_end": 200, "spec_segments": segments})

 def test_invalid_segment_fields_rejected(self):
  for segment in ({"version": "", "start": 61, "end": 200, "lsl": 19.9, "usl": 20.1},
                  {"version": "A", "revision": 0, "start": 61, "end": 200, "lsl": 19.9, "usl": 20.1},
                  {"version": "A", "start": 61, "end": 200, "lsl": 20.1, "usl": 20.1},
                  {"version": "A", "start": 61, "end": 200, "lsl": float("nan"), "usl": 20.1}):
   with self.assertRaises(ValueError): normalize_segments({"monitoring_start": 61, "monitoring_end": 200, "spec_segments": [segment]})

 def test_uncovered_sample_rejected_before_calculation(self):
  segments = normalize_segments({"monitoring_start": 61, "monitoring_end": 200, "lsl": 19.9, "usl": 20.1})
  with self.assertRaises(ValueError): ensure_sample_coverage(segments, [60, 61])
  with self.assertRaises(ValueError): ensure_sample_coverage(segments, [61, 201])


class SegmentedAnalysisTests(unittest.TestCase):
 SEGMENTS = [{"id": "sa", "version": "A", "revision": 1, "start": 61, "end": 132, "lsl": 19.95, "usl": 20.05},
             {"id": "sb", "version": "B", "revision": 2, "start": 133, "end": 200, "lsl": 20.00, "usl": 20.06}]
 STUDY = {"id": "s4", "monitoring_start": 61, "monitoring_end": 200, "smoothing": .2, "control_width": 3,
          "spec_segments": SEGMENTS, "lsl": 19.95, "usl": 20.05}

 def fixture(self):
  # 61—132 sit at 20.03 (inside A 19.95—20.05). 133—200 sit at 20.055: inside
  # B 20.00—20.06 but outside A, so reusing segment A's limit would raise 68 false alarms.
  return [{"sample_id": f"LS-01-{seq:03d}", "machine": "LS-01", "sequence": seq,
           "value": 20.03 if seq <= 132 else 20.055} for seq in range(1, 201)]

 def test_each_sample_judged_by_its_own_version(self):
  result = analyze(self.fixture(), BASELINE, self.STUDY)
  by_seq = {p["sequence"]: p for p in result["series"]}
  self.assertEqual(by_seq[132]["spec_version"], "A")
  self.assertEqual(by_seq[133]["spec_version"], "B")
  self.assertFalse(by_seq[132]["out_of_spec"])
  self.assertFalse(by_seq[133]["out_of_spec"])
  self.assertEqual(result["capability"]["outside_count"], 0)
  # the same values under one uniform limit would produce false alarms
  uniform = analyze(self.fixture(), BASELINE, {"id": "u", "monitoring_start": 61, "monitoring_end": 200, "smoothing": .2, "control_width": 3, "lsl": 19.95, "usl": 20.05})
  self.assertEqual(uniform["capability"]["outside_count"], 68)

 def test_spec_limits_per_segment_not_uniform(self):
  result = analyze(self.fixture(), BASELINE, self.STUDY)
  self.assertEqual(result["series"][-1]["lsl"], 20.00)
  self.assertEqual(result["series"][0]["lsl"], 19.95)

 def test_capability_computed_per_segment_without_mixing(self):
  result = analyze(self.fixture(), BASELINE, self.STUDY)
  caps = result["capability"]["segments"]
  self.assertEqual(len(caps), 2)
  for caps_row in caps:
   cp = (caps_row["usl"] - caps_row["lsl"]) / (6 * BASELINE["sigma"])
   self.assertTrue(math.isclose(caps_row["cp"], cp))
   cpk = min(caps_row["usl"] - caps_row["mean"], caps_row["mean"] - caps_row["lsl"]) / (3 * BASELINE["sigma"])
   self.assertTrue(math.isclose(caps_row["cpk"], cpk))
  # pooled totals come from actual samples, not from averaging the Cp/Cpk
  total = result["capability"]
  self.assertEqual(total["sample_count"], len(result["series"]))
  self.assertEqual(total["outside_count"], sum(p["out_of_spec"] for p in result["series"]))
  self.assertEqual(total["outside_rate"], total["outside_count"] / total["sample_count"])

 def test_pooled_rate_uses_actual_counts_from_each_segment(self):
  values = self.fixture()
  values[60]["value"] = 20.20  # sequence 61, outside A
  values[132]["value"] = 20.20  # sequence 133, outside B
  values[199]["value"] = 20.20  # sequence 200, outside B
  result = analyze(values, BASELINE, self.STUDY)
  caps = result["capability"]["segments"]
  self.assertEqual([row["outside_count"] for row in caps], [1, 2])
  self.assertEqual(result["capability"]["outside_count"], 3)
  self.assertAlmostEqual(result["capability"]["outside_rate"], 3 / 140)

 def test_empty_segment_has_no_capability_not_other_version(self):
  sparse = [r for r in self.fixture() if not 61 <= r["sequence"] <= 90]
  segments = [{"id": "sa", "version": "A", "revision": 1, "start": 61, "end": 90, "lsl": 19.95, "usl": 20.05},
              {"id": "sb", "version": "B", "revision": 1, "start": 91, "end": 200, "lsl": 19.95, "usl": 20.05}]
  result = analyze(sparse, BASELINE, {"id": "s5", "monitoring_start": 61, "monitoring_end": 200, "smoothing": .2, "control_width": 3, "spec_segments": segments})
  self.assertEqual(result["capability"]["segments"][0]["sample_count"], 0)
  self.assertIsNone(result["capability"]["segments"][0]["cp"])
  self.assertEqual(result["capability"]["sample_count"], len(result["series"]))

 def test_ewma_unchanged_by_segmentation(self):
  plain = analyze(self.fixture(), BASELINE, {"id": "s6", "monitoring_start": 61, "monitoring_end": 200, "smoothing": .2, "control_width": 3, "lsl": 19.95, "usl": 20.05})
  segmented = analyze(self.fixture(), BASELINE, self.STUDY)
  self.assertEqual([p["ewma"] for p in plain["series"]], [p["ewma"] for p in segmented["series"]])
  self.assertEqual([p["lcl"] for p in plain["series"]], [p["lcl"] for p in segmented["series"]])
  self.assertEqual(plain["control_signals"], segmented["control_signals"])

 def test_boundary_values_are_not_out_of_spec(self):
  series = ewma_series([{"sample_id": f"LS-01-{i:03d}", "machine": "LS-01", "sequence": i, "value": 20.0} for i in range(1, 4)], 20.0, .009)
  segments = [{"id": "s", "version": "A", "revision": 1, "start": 1, "end": 3, "lsl": 19.95, "usl": 20.05}]
  samples = [apply_segment(dict(s, value=v), segments) for s, v in zip(series, (19.95, 20.05, 20.051))]
  self.assertEqual([s["out_of_spec"] for s in samples], [False, False, True])


class LegacyResultUpgradeTests(unittest.TestCase):
 OLD = {"series": [
  {"sample_id": "LS-01-061", "machine": "LS-01", "sequence": 61, "value": 20.0, "t": 1, "ewma": 20.0,
   "center": 20.0, "lcl": 19.9, "ucl": 20.1, "out_of_control": False, "out_of_spec": False},
  {"sample_id": "LS-01-135", "machine": "LS-01", "sequence": 135, "value": 20.04, "t": 2, "ewma": 20.0,
   "center": 20.0, "lcl": 19.9, "ucl": 20.1, "out_of_control": False, "out_of_spec": True}],
  "baseline": {"mean": 20.0, "sigma": .009}, "study": {"monitoring_start": 61, "monitoring_end": 200, "lsl": 19.95, "usl": 20.05},
  "machine": "LS-01", "control_signals": 0, "first_signal": None,
  "capability": {"mean": 20.02, "sigma_used": .009, "cp": 1.85, "cpk": .74, "outside_count": 1, "sample_count": 2, "outside_rate": .5, "lsl": 19.95, "usl": 20.05},
  "capability_interpretation_allowed": True, "checksum": "legacy", "limitations": []}

 def test_legacy_result_keeps_original_numbers(self):
  upgraded = upgrade_result(self.OLD)
  self.assertEqual(upgraded["capability"]["segments"][0]["cp"], 1.85)
  self.assertEqual(upgraded["capability"]["segments"][0]["outside_rate"], .5)
  self.assertEqual(upgraded["capability"]["outside_count"], 1)
  self.assertEqual(upgraded["checksum"], "legacy")
  self.assertNotIn("spec_segments", self.OLD)

 def test_legacy_result_gains_one_version_per_sample(self):
  upgraded = upgrade_result(self.OLD)
  self.assertEqual(len(upgraded["spec_segments"]), 1)
  self.assertTrue(all(p["spec_version"] and p["spec_revision"] == 1 for p in upgraded["series"]))
  self.assertEqual([p["out_of_spec"] for p in upgraded["series"]], [False, True])


class StudyRevisionTests(unittest.TestCase):
 def setUp(self):
  repo.init_db()
  rows = [{"sample_id": f"LS-01-{i:03d}", "machine": "LS-01", "sequence": i, "value": 20.0} for i in range(1, 21)]
  repo.put("datasets", {"id": "ds", "name": "t", "source": "t.csv", "rows": rows})
  mu, sigma = baseline_statistics([20.0, 20.001, 19.999, 20.0, 20.0])
  repo.put("baselines", {"id": "b", "name": "b", "dataset_id": "ds", "machine": "LS-01", "start": 1, "end": 10, "values": [], "mean": mu, "sigma": sigma})
  repo.put("studies", {"id": "st", "name": "st", "baseline_id": "b", "monitoring_start": 11, "monitoring_end": 20,
                       "smoothing": .2, "control_width": 3, "lsl": 19.95, "usl": 20.05})

 def test_revision_is_immutable_history(self):
  from src.schemas.entities import StudyRevisionInput
  from src.services import study as service
  service.revise("st", StudyRevisionInput(comment="改版", spec_segments=[
   {"version": "A", "start": 11, "end": 15, "lsl": 19.9, "usl": 20.1},
   {"version": "B", "start": 16, "end": 20, "lsl": 19.95, "usl": 20.05}]), {"email": "analyst@lishi.test"})
  revisions = service.list_revisions("st")
  self.assertEqual(len(revisions), 1)
  self.assertEqual(revisions[0]["revision"], 2)
  # previous basis recorded as a legacy single segment
  self.assertEqual(len(revisions[0]["previous_spec_segments"]), 1)
  self.assertEqual((revisions[0]["previous_spec_segments"][0]["start"], revisions[0]["previous_spec_segments"][0]["end"]), (11, 20))
  study = repo.get("studies", "st")
  self.assertEqual(study["spec_revision"], 2)
  self.assertEqual(study["revised_by"], "analyst@lishi.test")

 def test_invalid_revision_leaves_study_untouched(self):
  from src.schemas.entities import StudyRevisionInput
  from src.services import study as service
  before = dict(repo.get("studies", "st"))
  with self.assertRaises(ValueError):
   service.revise("st", StudyRevisionInput(comment="坏分段", spec_segments=[
    {"version": "A", "start": 11, "end": 15, "lsl": 19.9, "usl": 20.1},
    {"version": "B", "start": 14, "end": 20, "lsl": 19.95, "usl": 20.05}]), {"email": "analyst@lishi.test"})
  self.assertEqual(repo.get("studies", "st"), before)
  self.assertEqual(service.list_revisions("st"), [])


if __name__ == "__main__":
 unittest.main(verbosity=2)
