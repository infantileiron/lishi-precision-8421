from src.models.entities import ControlRun
from src.utils import repository as repo
from src.utils.identity import new_id, now
from src.services.statistics import analyze
from src.services.specs import normalize_segments
from src.config.settings import TASK_MODE, REDIS_URL, ARTIFACT_DIR
from src.services.results import upgrade_result
import json
def list_runs():
    return [dict(r)|{'result':upgrade_result(r.get('result') or {})} for r in repo.all_rows("runs")]
def execute(id):
    run=repo.get("runs",id)
    if run["status"] in ("running","completed"): return run
    run["status"]="running"; repo.put("runs",run)
    try:
        # Runs always execute against the study snapshot captured at submission,
        # so a later spec revision cannot rewrite historical results or reports.
        exp=run.get("study_snapshot") or repo.get("studies",run["study_id"])
        baseline=repo.get("baselines",exp["baseline_id"])
        dataset=repo.get("datasets",baseline["dataset_id"])
        run["result"]=analyze(dataset["rows"],baseline,exp)
        ARTIFACT_DIR.mkdir(parents=True,exist_ok=True)
        (ARTIFACT_DIR / (id+".json")).write_text(json.dumps(run["result"],ensure_ascii=False))
        run["status"]="completed"
    except Exception as exc:
        run["status"]="failed"; run["error"]=str(exc)
    return repo.put("runs",run)
def create(data):
    study=repo.get("studies",data.study_id)
    # Reject overlapping gaps before queueing so the error is returned to the submitter.
    normalize_segments(study)
    if sum(r["status"] in ("queued","running") for r in repo.all_rows("runs"))>=10: raise ValueError("运行队列已满，请等待已有任务完成")
    snapshot=json.loads(json.dumps(study,ensure_ascii=False))
    run=repo.put("runs",ControlRun(new_id("run"),data.study_id,study_snapshot=snapshot,created_at=now()))
    if TASK_MODE=="inline": return execute(run["id"])
    try:
        import redis
        redis.Redis.from_url(REDIS_URL).rpush("quality-watch:jobs",run["id"])
    except Exception:
        run["status"]="failed"; run["error"]="队列不可用，请恢复Redis后重新提交"
        repo.put("runs",run)
        raise ValueError(run["error"])
    return run

def detail(id):
    run=repo.get("runs",id)
    return dict(run)|{'result':upgrade_result(run.get('result') or {})}
