from src.models.entities import ControlStudy, StudyRevision
from src.utils import repository as repo
from src.utils.identity import new_id,now
from src.services.specs import normalize_segments


def list_studies():return repo.all_rows('studies')
def list_revisions(study_id):
 repo.get('studies',study_id)
 return sorted([r for r in repo.all_rows('study_revisions') if r['study_id']==study_id],key=lambda r:r['revision'])

def create(data,user=None):
 baseline=repo.get('baselines',data.baseline_id)
 if data.monitoring_start<=baseline['end']:raise ValueError('监控区间必须严格位于锁定基线之后，防止基线泄漏')
 if data.monitoring_start>data.monitoring_end:raise ValueError('监控起始序号不能大于结束序号')
 raw_segments=[s.model_dump() for s in data.spec_segments] if data.spec_segments else []
 if not raw_segments and data.lsl>=data.usl:raise ValueError('规格下限必须小于上限')
 candidate={'monitoring_start':data.monitoring_start,'monitoring_end':data.monitoring_end,'lsl':data.lsl,'usl':data.usl}
 if raw_segments:candidate['spec_segments']=raw_segments
 segments=normalize_segments(candidate)
 lsl,usl=data.lsl,data.usl
 if raw_segments:lsl,usl=segments[0]['lsl'],segments[0]['usl']
 actor=(user or {}).get('email','')
 study=ControlStudy(new_id('study'),data.name,data.baseline_id,data.monitoring_start,data.monitoring_end,data.smoothing,data.control_width,lsl,usl,raw_segments,1,now() if raw_segments else '',actor,now())
 saved=repo.put('studies',study)
 if raw_segments:
  repo.put('study_revisions',StudyRevision(new_id('revision'),saved['id'],1,segments,[],'初始规格分段',actor,now()),insert_only=True)
 return saved

def revise(id,data,user=None):
 study=repo.get('studies',id)
 actor=(user or {}).get('email','')
 current=normalize_segments(study)
 raw_segments=[s.model_dump() for s in data.spec_segments]
 segments=normalize_segments(dict(study)|{'spec_segments':raw_segments})
 history=[r for r in repo.all_rows('study_revisions') if r['study_id']==id]
 next_revision=max(int(study.get('spec_revision') or 0),max([r['revision'] for r in history],default=0),1)+1
 study['spec_segments']=raw_segments
 # Legacy lsl/usl stay in sync with the outer envelope for callers that still
 # read them; the segments themselves are the authoritative per-interval basis.
 study['lsl'],study['usl']=segments[0]['lsl'],segments[-1]['usl']
 study['spec_revision']=next_revision
 study['revised_at']=now();study['revised_by']=actor
 saved=repo.put('studies',study)
 repo.put('study_revisions',StudyRevision(new_id('revision'),id,next_revision,segments,current,data.comment,actor,now()),insert_only=True)
 return saved
