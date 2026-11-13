from src.services.specs import DEFAULT_LEGACY_VERSION,normalize_segments,segment_for_sequence


def upgrade_result(result):
 """Present legacy (single-spec) results in the segmented shape.

 Stored payloads from before the upgrade are never rewritten; this adapter
 only fills in per-segment fields at read time so historical runs and
 approved reports keep their original numbers while the UI/CSV can show a
 version for every segment.
 """
 if not isinstance(result,dict) or not result.get('series'):return result
 study=result.get('study') or {}
 try:
  segments=result.get('spec_segments') or normalize_segments(study)
 except ValueError:
  lsl=result.get('capability',{}).get('lsl',study.get('lsl'))
  usl=result.get('capability',{}).get('usl',study.get('usl'))
  segments=[{'id':'legacy-spec','version':DEFAULT_LEGACY_VERSION,'revision':1,'start':study.get('monitoring_start'),'end':study.get('monitoring_end'),'lsl':lsl,'usl':usl,'note':''}]
 upgraded=dict(result);upgraded['spec_segments']=segments
 series=[]
 for point in result['series']:
  item=dict(point)
  if not item.get('spec_version'):
   segment=segment_for_sequence(segments,item.get('sequence')) or segments[0]
   item['spec_segment_id']=segment['id'];item['spec_version']=segment['version'];item['spec_revision']=segment['revision']
   item['lsl']=segment['lsl'];item['usl']=segment['usl']
   if 'out_of_spec' not in item:
    item['out_of_spec']=item['value']<segment['lsl'] or item['value']>segment['usl']
  series.append(item)
 upgraded['series']=series
 cap=dict(result.get('capability') or {})
 if not cap.get('segments'):
  total=cap.get('sample_count') or len(series)
  outside=cap.get('outside_count',sum(p['out_of_spec'] for p in series))
  allowance=result.get('capability_interpretation_allowed',True)
  cap={'segments':[{'id':segments[0]['id'],'version':segments[0]['version'],'revision':segments[0]['revision'],'start':segments[0]['start'],'end':segments[0]['end'],'lsl':segments[0]['lsl'],'usl':segments[0]['usl'],'sample_count':total,'mean':cap.get('mean'),'sigma_used':cap.get('sigma_used'),'cp':cap.get('cp'),'cpk':cap.get('cpk'),'below_lsl':cap.get('below_lsl',sum(p['value']<segments[0]['lsl'] for p in series)),'above_usl':cap.get('above_usl',sum(p['value']>segments[0]['usl'] for p in series)),'outside_count':outside,'outside_rate':(outside/total) if total else 0,'observed_sd':cap.get('observed_sd'),'capability_interpretation_allowed':allowance}],'sample_count':total,'outside_count':outside,'outside_rate':(outside/total) if total else 0,'segment_count':1,'spec_versions':[segments[0]['version']]}
 upgraded['capability']=cap
 return upgraded
