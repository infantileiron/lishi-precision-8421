import csv,io
from fastapi import HTTPException
from src.models.entities import Report
from src.config.settings import ARTIFACT_DIR
from src.utils import repository as repo
from src.utils.identity import new_id,now
from src.services.results import upgrade_result

def safe_cell(value):return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value
def list_reports():return repo.all_rows('reports')
def create(data):
 run,review=repo.get('runs',data.run_id),repo.get('reviews',data.review_id)
 if review['status']!='approved' or review['run_id']!=run['id'] or run['status']!='completed':raise ValueError('报告必须引用该运行已通过的复核')
 report=repo.put('reports',Report(new_id('rpt'),data.run_id,data.review_id,data.title,now()));ARTIFACT_DIR.mkdir(parents=True,exist_ok=True);(ARTIFACT_DIR/(report['id']+'.csv')).write_text(download(report['id']),encoding='utf-8');return report
def download(id):
 report=repo.get('reports',id);run=repo.get('runs',report['run_id']);r=upgrade_result(run['result'])
 if repo.get('reviews',report['review_id'])['status']!='approved':raise HTTPException(403,'复核未通过')
 c=r['capability'];segments=r['capability']['segments']
 out=io.StringIO();w=csv.writer(out)
 # Report metadata keeps every spec version/revision so an approved report can
 # always be traced back to the exact basis it was computed under.
 w.writerow(['report','machine','spec_versions','segment_count','sample_count','outside_count','outside_rate','capability_assumptions_allowed','checksum'])
 w.writerow([safe_cell(report['title']),safe_cell(r['machine']),safe_cell(' | '.join(seg['version']+' r'+str(seg['revision']) for seg in segments)),c['segment_count'],c['sample_count'],c['outside_count'],c['outside_rate'],r['capability_interpretation_allowed'],r['checksum']])
 w.writerow([]);w.writerow(['spec_version','spec_revision','segment_start','segment_end','lsl','usl','cp','cpk','segment_sample_count','segment_outside_count','segment_outside_rate','capability_interpretation_allowed'])
 for seg in segments:w.writerow([safe_cell(seg['version']),seg['revision'],seg['start'],seg['end'],seg['lsl'],seg['usl'],seg['cp'],seg['cpk'],seg['sample_count'],seg['outside_count'],seg['outside_rate'],seg['capability_interpretation_allowed']])
 w.writerow([]);w.writerow(['sample_id','sequence','value_mm','ewma_mm','center','lcl','ucl','lsl','usl','spec_version','spec_revision','out_of_control','out_of_spec'])
 for p in r['series']:w.writerow([safe_cell(p['sample_id']),p['sequence'],p['value'],p['ewma'],p['center'],p['lcl'],p['ucl'],p['lsl'],p['usl'],safe_cell(p['spec_version']),p['spec_revision'],p['out_of_control'],p['out_of_spec']])
 return '﻿'+out.getvalue()
