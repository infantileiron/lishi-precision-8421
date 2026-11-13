import random
from src.utils import repository as repo
from src.utils.identity import now
from src.utils.security import hash_password
from src.services.ewma import baseline_statistics
from src.services.statistics import analyze
from src.services.specs import normalize_segments

def demo_rows():
 rng=random.Random(2207);rows=[]
 for machine in ['LS-01','LS-02','LS-03']:
  for seq in range(1,201):
   drift=.032 if machine=='LS-01' and seq>=135 else .008 if machine=='LS-02' and seq>=155 else 0
   rows.append({'sample_id':f'{machine}-{seq:03d}','machine':machine,'sequence':seq,'value':round(20+rng.gauss(0,.009)+drift,5)})
 return rows

def seed():
 repo.init_db()
 for role,name in [('admin','质量复核工程师'),('analyst','计量分析员'),('viewer','工艺观察员')]:
  email=f'{role}@lishi.test';repo.put('users',{'id':email,'email':email,'name':name,'role':role,'password_hash':hash_password('Gauge2026!')},insert_only=True)
 rows=demo_rows();repo.put('datasets',{'id':'ds-shaft','name':'11月轴径单值测量 · 600次','source':'shaft_diameter_202611.csv','rows':rows,'created_at':now()},insert_only=True)
 values=[r['value'] for r in rows if r['machine']=='LS-01' and r['sequence']<=60];mu,sigma=baseline_statistics(values)
 baseline={'id':'baseline-ls01','name':'LS-01稳定基线 001—060','dataset_id':'ds-shaft','machine':'LS-01','start':1,'end':60,'values':values,'mean':mu,'sigma':sigma,'created_at':now()};repo.put('baselines',baseline,insert_only=True)
 study={'id':'study-ewma','name':'LS-01 秋季尺寸漂移复核','baseline_id':'baseline-ls01','monitoring_start':61,'monitoring_end':200,'smoothing':.2,'control_width':3,'lsl':19.95,'usl':20.05,'created_at':now()};repo.put('studies',study,insert_only=True)
 # Segmented study: specs changed mid-monitoring. Segment 61—132 keeps the
 # original 19.95—20.05 tolerance, 133—200 tightens to 19.97—20.03.
 segmented={'id':'study-ewma-segmented','name':'LS-01 分段规格漂移复核','baseline_id':'baseline-ls01','monitoring_start':61,'monitoring_end':200,'smoothing':.2,'control_width':3,'lsl':19.95,'usl':20.05,'spec_revision':2,'revised_at':now(),'revised_by':'admin@lishi.test','created_at':now(),'spec_segments':[{'id':'study-ewma-segmented-spec-1','version':'SPEC-A','revision':1,'start':61,'end':132,'lsl':19.95,'usl':20.05,'note':'图纸版本A'},{'id':'study-ewma-segmented-spec-2','version':'SPEC-B','revision':1,'start':133,'end':200,'lsl':19.97,'usl':20.03,'note':'图纸改版B，收紧公差'}]};repo.put('studies',segmented,insert_only=True)
 segments=normalize_segments(segmented)
 initial=[dict(segments[0],end=200)]
 repo.put('study_revisions',{'id':'revision-segmented-1','study_id':'study-ewma-segmented','revision':1,'spec_segments':initial,'previous_spec_segments':[],'comment':'初始规格 SPEC-A 覆盖全段','actor':'admin@lishi.test','created_at':now()},insert_only=True)
 repo.put('study_revisions',{'id':'revision-segmented-2','study_id':'study-ewma-segmented','revision':2,'spec_segments':segments,'previous_spec_segments':initial,'comment':'观测序号133起切换SPEC-B并收紧规格','actor':'admin@lishi.test','created_at':now()},insert_only=True)
 repo.put('runs',{'id':'run-baseline','study_id':'study-ewma','status':'completed','result':analyze(rows,baseline,study),'error':'','created_at':now()},insert_only=True)
 repo.put('reviews',{'id':'review-baseline','run_id':'run-baseline','comment':'EWMA信号与规格越界已分开记录；漂移期间能力指数仅描述诊断。','status':'approved','reviewer':'admin@lishi.test','created_at':now()},insert_only=True)
 repo.put('reports',{'id':'report-baseline','run_id':'run-baseline','review_id':'review-baseline','title':'LS-01尺寸漂移复核档案','created_at':now()},insert_only=True)
 repo.put('runs',{'id':'run-segmented','study_id':'study-ewma-segmented','status':'completed','study_snapshot':segmented,'result':analyze(rows,baseline,segmented),'error':'','created_at':now()},insert_only=True)
 return {t:len(repo.all_rows(t)) for t in ('users','datasets','baselines','studies','study_revisions','runs','reviews','reports')}
