"""Disk-backed batch bookkeeping. Source paths are labels, never local paths."""
import csv
import io
import json
import re
from pathlib import PurePosixPath
from zipfile import ZipFile, ZIP_DEFLATED
from converter import ConversionError, convert, inspect, read_package, render

MAX_FILES=1000
MAX_TOTAL=1024**3
MAX_FILE=60*1024**2
TERMINAL={'converted','unchanged','skipped','failed'}

def safe_path(value):
    if not isinstance(value,str) or not value or len(value)>1024:
        raise ConversionError('Invalid relative file path.')
    if '\\' in value or ':' in value or value.startswith('/') or any(ord(c)<32 for c in value):
        raise ConversionError('Folder paths must be relative, without drive names or control characters.')
    if any(c in ('','.','..') for c in value.split('/')):
        raise ConversionError('Folder paths cannot contain empty, dot, or parent components.')
    return value

def new_batch(files,mode):
    if mode not in ('editable','visual'):
        raise ConversionError('Choose editable or visual mode.')
    if not files or len(files)>MAX_FILES:
        raise ConversionError('Select between 1 and 1,000 files.')
    entries=[];seen=set();total=0
    for item in files:
        path=safe_path(item['path']);key=path.casefold()
        if key in seen:
            raise ConversionError('Duplicate file paths (including case-only differences) are not supported.')
        seen.add(key);size=item['size']
        if not isinstance(size,int) or size<0:
            raise ConversionError('Invalid file size.')
        name=PurePosixPath(path).name
        reason=None;status='pending'
        if name.startswith('~$'):
            reason='Temporary Office file.'
        elif not name.lower().endswith('.pptx'):
            reason='Save as .pptx in PowerPoint first.' if name.lower().endswith('.ppt') else 'Not a .pptx presentation.'
        elif size>MAX_FILE:
            reason='File exceeds the 60 MB limit.';status='failed'
        else:
            total+=size
        if reason and status!='failed':status='skipped'
        entries.append(dict(path=path,size=size,status=status,message=reason,warnings=[]))
    if total>MAX_TOTAL:
        raise ConversionError('Batch exceeds the 1 GB upload limit. Select a smaller folder.')
    return dict(mode=mode,status='uploading',current=None,entries=entries)

def save(folder,state):
    tmp=folder/'batch.pending'
    tmp.write_text(json.dumps(state,indent=2),encoding='utf-8')
    tmp.replace(folder/'batch.json')

def load(folder):
    return json.loads((folder/'batch.json').read_text(encoding='utf-8'))

def summarize(state):
    counts={s:sum(e['status']==s for e in state['entries']) for s in TERMINAL}
    return {**state,'counts':counts,'done':sum(counts.values()),'total':len(state['entries'])}

def process_item(folder,mode):
    source=folder/'original.pptx';dest=folder/'widescreen.pptx'
    info=inspect(read_package(source))
    if info['ratio']=='other':
        return {'skip_reason':f"Unsupported aspect ratio {info['width']/info['height']:.4f}:1; expected 4:3 or 16:9."}
    if len(info['slides'])>150:
        raise ConversionError('Maximum 150 slides per presentation in folder mode.')
    # Visual conversion requires all source images; editable conversion doesn't.
    images=None
    if mode=='visual' and info['ratio']=='4:3':
        images=render(source,folder/'before',width=1600)
    report=convert(source,dest,mode,images=images)
    try:
        if not images:render(source,folder/'before',width=1200,limit=1)
        render(dest,folder/'after',width=1600 if info['ratio']=='4:3' else 1200,limit=1)
        report['preview_count']=1
    except ConversionError as exc:
        report['preview_count']=0
        report['warnings'].append('Preview unavailable: '+str(exc))
    (folder/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report

def preview_item(folder,full=False):
    report=json.loads((folder/'report.json').read_text())
    if full and report.get('preview_count',0)!=report['slide_count']:
        before=render(folder/'original.pptx',folder/'before',width=1200)
        after=render(folder/'widescreen.pptx',folder/'after',width=1600 if report['source_ratio']=='4:3' else 1200)
        if len(before)!=report['slide_count'] or len(after)!=len(before):
            raise ConversionError('Preview slide count mismatch.')
        report['preview_count']=len(after)
        (folder/'report.json').write_text(json.dumps(report,indent=2))
    return report

def archive(folder,state,data_root):
    summary=summarize(state)
    csv_text=io.StringIO(newline='')
    writer=csv.writer(csv_text)
    writer.writerow(['source','status','output','message','warnings'])
    for item in state['entries']:
        # Prevent spreadsheet formula interpretation of user-supplied filenames.
        def cell(value):
            value=str(value or '')
            return "'"+value if value.lstrip().startswith(('=','+','-','@')) else value
        writer.writerow([cell(item.get(k)) for k in ('path','status','output','message')]+[cell('; '.join(item['warnings']))])
    pending=folder/'batch-outputs.pending'
    with ZipFile(pending,'w',compression=ZIP_DEFLATED) as z:
        z.writestr('batch-report.json',json.dumps(summary,indent=2))
        z.writestr('batch-report.csv',csv_text.getvalue())
        for item in state['entries']:
            if item['status'] in ('converted','unchanged'):
                z.write(data_root/item['job_id']/'widescreen.pptx',item['output'])
    pending.replace(folder/'batch-outputs.zip')
