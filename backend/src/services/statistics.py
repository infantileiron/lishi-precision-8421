import hashlib,json
from src.services.ewma import ewma_series
from src.services.capability import capability_by_segment
from src.services.specs import apply_segment,ensure_sample_coverage,normalize_segments

def analyze(rows,baseline,study):
 monitoring=sorted([r for r in rows if r['machine']==baseline['machine'] and study['monitoring_start']<=r['sequence']<=study['monitoring_end']],key=lambda r:r['sequence'])
 segments=normalize_segments(study)
 ensure_sample_coverage(segments,[r['sequence'] for r in monitoring])
 series=ewma_series(monitoring,baseline['mean'],baseline['sigma'],study['smoothing'],study['control_width'])
 for row in series:apply_segment(row,segments)
 cap=capability_by_segment(series,segments,baseline['sigma'])
 alarms=sum(r['out_of_control'] for r in series)
 for segment in cap['segments']:
  segment['capability_interpretation_allowed']=alarms==0
 return {'series':series,'baseline':baseline,'study':study,'spec_segments':segments,'machine':baseline['machine'],'control_signals':alarms,'first_signal':next((r['sequence'] for r in series if r['out_of_control']),None),'capability':cap,'capability_interpretation_allowed':alarms==0,'checksum':hashlib.sha256(json.dumps({'rows':rows,'baseline':baseline,'study':study,'segments':segments},sort_keys=True).encode()).hexdigest(),'limitations':['数据为模拟单值尺寸，EWMA每次使用一个观测，不再除以sqrt(n)','基线均值和样本标准差ddof=1在整个监控区间固定，Z0=基线均值；t为监控区间第t个观测','控制界限随t变化，反映稳定过程的波动；规格界限来自各观测序号区段的工程规格版本，两者不得混用','工程规格按观测序号分段，各段分别判定越界与计算Cp/Cpk；总超规格率按实际样本汇总，不合并不同版本的Cp/Cpk','Cp使用固定基线sigma；Cpk使用该段监控均值和固定基线sigma，仅在过程稳定且近正态等假设下解释','存在EWMA信号时能力数值仅作描述诊断，不作能力合格结论；实测超规格率直接计数，不做正态尾概率替代']}
