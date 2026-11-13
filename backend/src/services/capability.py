import math,statistics

def capability(values,lsl,usl,sigma):
 if not values or any(not math.isfinite(v) for v in values) or not all(math.isfinite(x) for x in (lsl,usl,sigma)) or lsl>=usl or sigma<=0:raise ValueError('规格上下限、样本或基线sigma无效')
 mean=statistics.mean(values);outside=sum(v<lsl or v>usl for v in values)
 return {'mean':mean,'sigma_used':sigma,'cp':(usl-lsl)/(6*sigma),'cpk':min(usl-mean,mean-lsl)/(3*sigma),'below_lsl':sum(v<lsl for v in values),'above_usl':sum(v>usl for v in values),'outside_count':outside,'sample_count':len(values),'outside_rate':outside/len(values),'observed_sd':statistics.stdev(values) if len(values)>1 else None,'lsl':lsl,'usl':usl,'spec_width':usl-lsl}


def capability_by_segment(values,segments,sigma):
 """Capability is computed per spec segment so versions are never mixed.

 Pooling the segment counts would combine different spec limits into one
 Cpk; therefore only the observed over-spec counts are pooled at the end.
 """
 grouped={segment['id']:[] for segment in segments}
 for item in values:
  segment_id=item['spec_segment_id']
  if segment_id not in grouped:raise ValueError(f"样本序号 {item['sequence']} 未被任何工程规格分段覆盖")
  grouped[segment_id].append(item)
 segment_rows=[]
 for segment in segments:
  items=grouped[segment['id']]
  base={'id':segment['id'],'version':segment['version'],'revision':segment['revision'],'start':segment['start'],'end':segment['end'],'lsl':segment['lsl'],'usl':segment['usl'],'capability_interpretation_allowed':False}
  if not items:
   # A coverage-complete partition can still have an observation-free slice if
   # the dataset skips sequence numbers. Its capability is undefined, so report
   # it as empty rather than fail the whole run or borrow another version's data.
   segment_rows.append(base|{'sample_count':0,'mean':None,'sigma_used':sigma,'cp':None,'cpk':None,'below_lsl':0,'above_usl':0,'outside_count':0,'outside_rate':0,'observed_sd':None})
   continue
  stats=capability([item['value'] for item in items],segment['lsl'],segment['usl'],sigma)
  segment_rows.append(base|{'sample_count':stats['sample_count'],'mean':stats['mean'],'sigma_used':stats['sigma_used'],'cp':stats['cp'],'cpk':stats['cpk'],'below_lsl':stats['below_lsl'],'above_usl':stats['above_usl'],'outside_count':stats['outside_count'],'outside_rate':stats['outside_rate'],'observed_sd':stats['observed_sd']})
 total_samples=sum(row['sample_count'] for row in segment_rows)
 total_outside=sum(row['outside_count'] for row in segment_rows)
 return {'segments':segment_rows,'sample_count':total_samples,'outside_count':total_outside,'outside_rate':total_outside/total_samples,'segment_count':len(segment_rows),'spec_versions':[row['version'] for row in segment_rows]}
