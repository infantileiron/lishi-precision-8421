import io, json, os, pathlib, unittest

_DB = pathlib.Path("/tmp/quality-watch-http.sqlite")
_DB.unlink(missing_ok=True)
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/quality-watch-http.sqlite")
os.environ.setdefault("TASK_MODE", "inline")
os.environ.setdefault("SEED_DEMO", "true")
os.environ.setdefault("ARTIFACT_DIR", "/tmp/quality-watch-http-artifacts")

from fastapi.testclient import TestClient
from src.main import app
from src.services.seed import demo_rows


def csv_text():
 out = io.StringIO()
 out.write("sample_id,machine,sequence,value\n")
 for row in demo_rows():
  if row["machine"] == "LS-01":
   out.write(f"{row['sample_id']},LS-01,{row['sequence']},{row['value']}\n")
 return out.getvalue()


class HttpFlowTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.client = TestClient(app)
  cls.client.__enter__()

 @classmethod
 def tearDownClass(cls):
  cls.client.__exit__(None, None, None)

 def auth(self, email):
  res = self.client.post("/auth/login", json={"email": email, "password": "Gauge2026!"})
  self.assertEqual(res.status_code, 200, res.text)
  return {"Authorization": "Bearer " + res.json()["access_token"]}

 def make_study(self, segments):
  ds = self.client.post("/datasets", json={"name": "HTTP规格分段测试", "csv_text": csv_text()}, headers=self.auth("analyst@lishi.test"))
  baseline = self.client.post("/baselines", json={"name": "基线", "dataset_id": ds.json()["id"], "machine": "LS-01", "start": 1, "end": 60}, headers=self.auth("analyst@lishi.test"))
  study = self.client.post("/studies", json={"name": "分段方案", "baseline_id": baseline.json()["id"], "monitoring_start": 61, "monitoring_end": 200, "smoothing": .2, "control_width": 3, "spec_segments": segments}, headers=self.auth("analyst@lishi.test"))
  return study

 def test_segmented_study_run_report_and_csv(self):
  segments = [{"version": "SPEC-A", "revision": 1, "start": 61, "end": 135, "lsl": 19.95, "usl": 20.05},
              {"version": "SPEC-B", "revision": 2, "start": 136, "end": 200, "lsl": 19.90, "usl": 20.10}]
  study = self.make_study(segments)
  self.assertEqual(study.status_code, 201, study.text)
  study_id = study.json()["id"]
  run = self.client.post("/runs", json={"study_id": study_id}, headers=self.auth("analyst@lishi.test"))
  self.assertEqual(run.status_code, 201, run.text)
  detail = self.client.get("/runs/" + run.json()["id"], headers=self.auth("viewer@lishi.test")).json()
  self.assertEqual(detail["status"], "completed", detail.get("error"))
  cap = detail["result"]["capability"]
  self.assertEqual(cap["segment_count"], 2)
  self.assertEqual(cap["spec_versions"], ["SPEC-A", "SPEC-B"])
  self.assertEqual(cap["sample_count"], 140)
  self.assertEqual(cap["outside_count"], sum(p["out_of_spec"] for p in detail["result"]["series"]))
  self.assertEqual(detail["result"]["series"][-1]["spec_version"], "SPEC-B")

  review = self.client.post("/reviews", json={"run_id": detail["id"], "comment": "分段规格与两类判据已核查。"}, headers=self.auth("analyst@lishi.test"))
  self.assertEqual(review.status_code, 201, review.text)
  decision = self.client.patch("/reviews/" + review.json()["id"], json={"status": "approved", "comment": "同意归档。"}, headers=self.auth("admin@lishi.test"))
  self.assertEqual(decision.status_code, 200, decision.text)
  report = self.client.post("/reports", json={"run_id": detail["id"], "review_id": review.json()["id"], "title": "分段规格报告"}, headers=self.auth("analyst@lishi.test"))
  self.assertEqual(report.status_code, 201, report.text)
  csv = self.client.get("/reports/" + report.json()["id"] + "/download", headers=self.auth("viewer@lishi.test"))
  self.assertEqual(csv.status_code, 200)
  text = csv.text.lstrip("﻿")
  self.assertIn("spec_version,spec_revision", text)
  self.assertIn("SPEC-A,1,61,135,19.95,20.05", text)
  self.assertIn("SPEC-B,2,136,200,19.9,20.1", text)
  # every data row carries its segment version
  data_rows = [line for line in text.splitlines() if line.startswith("LS-01-")]
  self.assertTrue(all(len(line.split(",")) == 13 for line in data_rows))
  self.assertTrue(any(line.endswith(",SPEC-A,1,False,False") or ",SPEC-A,1," in line for line in data_rows))
  self.assertTrue(any(",SPEC-B,2," in line for line in data_rows))

 def test_overlap_or_gap_rejected_on_create_and_run(self):
  for segments in (
   [{"version": "A", "start": 61, "end": 140, "lsl": 19.95, "usl": 20.05},
    {"version": "B", "start": 140, "end": 200, "lsl": 19.95, "usl": 20.05}],
   [{"version": "A", "start": 61, "end": 140, "lsl": 19.95, "usl": 20.05},
    {"version": "B", "start": 145, "end": 200, "lsl": 19.95, "usl": 20.05}],
   [{"version": "A", "start": 61, "end": 199, "lsl": 19.95, "usl": 20.05}],
  ):
   res = self.make_study(segments)
   self.assertEqual(res.status_code, 422, (segments, res.text))

 def test_revision_history_visible_and_history_preserved(self):
  segments = [{"version": "SPEC-A", "revision": 1, "start": 61, "end": 200, "lsl": 19.95, "usl": 20.05}]
  study = self.make_study(segments).json()
  run = self.client.post("/runs", json={"study_id": study["id"]}, headers=self.auth("analyst@lishi.test")).json()
  detail_before = self.client.get("/runs/" + run["id"], headers=self.auth("analyst@lishi.test")).json()
  before_caps = detail_before["result"]["capability"]["segments"][0]["cp"]

  revised = self.client.post("/studies/" + study["id"] + "/revisions", json={
   "comment": "观测序号133起改版SPEC-B",
   "spec_segments": [{"version": "SPEC-A", "revision": 1, "start": 61, "end": 132, "lsl": 19.95, "usl": 20.05},
                     {"version": "SPEC-B", "revision": 2, "start": 133, "end": 200, "lsl": 19.97, "usl": 20.03}]},
   headers=self.auth("analyst@lishi.test"))
  self.assertEqual(revised.status_code, 201, revised.text)
  history = self.client.get("/studies/" + study["id"] + "/revisions", headers=self.auth("viewer@lishi.test")).json()
  self.assertEqual([h["revision"] for h in history], [1, 2])
  self.assertEqual(len(history[0]["spec_segments"]), 1)
  self.assertEqual(len(history[-1]["previous_spec_segments"]), 1)
  self.assertEqual((history[-1]["previous_spec_segments"][0]["start"], history[-1]["previous_spec_segments"][0]["end"]), (61, 200))
  study_now = [s for s in self.client.get("/studies", headers=self.auth("viewer@lishi.test")).json() if s["id"] == study["id"]][0]
  self.assertEqual(study_now["spec_revision"], 2)

  # previously executed run keeps its original basis, even after the revision
  detail_after = self.client.get("/runs/" + run["id"], headers=self.auth("analyst@lishi.test")).json()
  self.assertEqual(detail_after["result"]["capability"]["segments"][0]["cp"], before_caps)
  self.assertEqual(detail_after["result"]["study"]["spec_segments"][0]["version"], "SPEC-A")
  self.assertEqual(len(detail_after["result"]["spec_segments"]), 1)

  new_run = self.client.post("/runs", json={"study_id": study["id"]}, headers=self.auth("analyst@lishi.test")).json()
  detail_new = self.client.get("/runs/" + new_run["id"], headers=self.auth("analyst@lishi.test")).json()
  self.assertEqual(detail_new["result"]["capability"]["segment_count"], 2)

 def test_legacy_seed_study_still_runs_single_spec(self):
  studies = self.client.get("/studies", headers=self.auth("viewer@lishi.test")).json()
  legacy = [s for s in studies if s["id"] == "study-ewma"][0]
  self.assertNotIn("spec_segments", legacy)
  run = self.client.post("/runs", json={"study_id": "study-ewma"}, headers=self.auth("analyst@lishi.test")).json()
  detail = self.client.get("/runs/" + run["id"], headers=self.auth("analyst@lishi.test")).json()
  self.assertEqual(detail["status"], "completed", detail.get("error"))
  cap = detail["result"]["capability"]
  self.assertEqual(cap["segment_count"], 1)
  self.assertEqual(cap["segments"][0]["lsl"], 19.95)
  self.assertEqual(cap["segments"][0]["usl"], 20.05)

 def test_legacy_approved_report_downloads_with_version(self):
  res = self.client.get("/reports/report-baseline/download", headers=self.auth("viewer@lishi.test"))
  self.assertEqual(res.status_code, 200)
  text = res.text.lstrip("﻿")
  self.assertIn("spec_version", text)
  self.assertIn("统一规格", text)


if __name__ == "__main__":
 unittest.main(verbosity=2)
