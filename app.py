"""Single-upload local development app. Bind to localhost on trusted machines."""
import asyncio
import json
import shutil
import time
import uuid
from pathlib import PurePosixPath
from pydantic import BaseModel, Field
import batch
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from converter import ConversionError, convert, inspect, read_package, render

BASE=Path(__file__).resolve().parent
DATA=BASE/'.runtime'; DATA.mkdir(exist_ok=True)
app=FastAPI(title='SlideStretch')
app.mount('/static',StaticFiles(directory=BASE/'static'),name='static')
lock=asyncio.Semaphore(1)
TASKS={}

def cleanup_expired():
    protected=set(TASKS)
    for ident in TASKS:
        try:
            state=batch.load(DATA/ident)
            protected.update(e['job_id'] for e in state['entries'] if e.get('job_id'))
        except (OSError,ValueError,KeyError):
            continue
    for old in DATA.iterdir():
        if old.name not in protected and old.is_dir() and time.time()-old.stat().st_mtime>86400:
            shutil.rmtree(old,ignore_errors=True)

@app.get('/')
def home():
    return FileResponse(BASE/'static/index.html')

def process(folder,mode):
    source=folder/'original.pptx'; output=folder/'widescreen.pptx'
    info=inspect(read_package(source))
    if info['ratio']=='other':
        raise ConversionError(f"This deck is {info['width']/info['height']:.4f}:1. Only 4:3 and already-wide 16:9 decks are supported.")
    if len(info['slides'])>150:
        raise ConversionError('The preview supports up to 150 slides. Use a smaller deck.')
    preview_error=None
    try:
        before=render(source,folder/'before',width=1600)
    except ConversionError as exc:
        if mode=='visual' and info['ratio']!='16:9':
            raise
        before=[];preview_error=str(exc)
    report=convert(source,output,mode,images=before or None)
    try:
        after=render(output,folder/'after',width=round(1600*4/3) if info['ratio']=='4:3' else 1600) if before else []
        if len(before)!=len(info['slides']) or len(after)!=len(before):
            raise ConversionError('Preview slide count mismatch; do not rely on these previews.')
    except ConversionError as exc:
        after=[];preview_error=str(exc)
    if preview_error:
        report['warnings'].append('Preview unavailable: '+preview_error)
    report['preview_count']=len(after)
    report['preview_renderer']='LibreOffice (installed fonts); verify important decks in PowerPoint.'
    (folder/'report.json').write_text(json.dumps(report,indent=2))
    return report

@app.post('/api/convert')
async def upload(file:UploadFile=File(...),mode:str=Form('editable')):
    if mode not in ('editable','visual'):
        raise HTTPException(400,'Choose editable or visual mode.')
    if not file.filename or not file.filename.lower().endswith('.pptx'):
        raise HTTPException(400,'Upload a .pptx file. Open older .ppt files in PowerPoint and Save As .pptx first.')
    # Retain results for one day, cleaning on subsequent uploads. No original
    # filename is used as a filesystem path. Never serve arbitrary job files.
    cleanup_expired()
    ident=uuid.uuid4().hex;folder=DATA/ident;folder.mkdir()
    try:
        size=0
        with (folder/'original.pptx').open('wb') as out:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>60*1024**2:
                    raise ConversionError('Maximum upload size is 60 MB.')
                out.write(chunk)
        async with lock:
            report=await run_in_threadpool(process,folder,mode)
        return {'id':ident,**report}
    except (ConversionError,ValueError,KeyError) as exc:
        shutil.rmtree(folder,ignore_errors=True)
        raise HTTPException(400,str(exc)) from exc
    except Exception as exc:
        shutil.rmtree(folder,ignore_errors=True)
        raise HTTPException(500,'Conversion failed. Check that the file opens in PowerPoint and try a smaller deck.') from exc
    finally:
        await file.close()

@app.get('/api/jobs/{ident}/{asset}')
def asset(ident:str,asset:str):
    if len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident):
        raise HTTPException(404)
    allowed={'widescreen.pptx','report.json'}
    if asset not in allowed:
        raise HTTPException(404)
    path=DATA/ident/asset
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path,filename=asset)

@app.get('/api/jobs/{ident}/preview/{side}/{slide}')
def preview(ident:str,side:str,slide:int):
    if len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident) or side not in ('before','after') or not 1<=slide<=150:
        raise HTTPException(404)
    path=DATA/ident/side/f'{slide}.png'
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path)


# Background jobs are retained while active. Batch metadata and results live on
# disk, and interrupted work is reported explicitly after a process restart.
class BatchFile(BaseModel):
    path: str
    size: int = Field(ge=0)

class BatchRequest(BaseModel):
    mode: str = 'editable'
    files: list[BatchFile] = Field(min_length=1,max_length=1000)

def batch_folder(ident):
    if len(ident)!=32 or any(c not in '0123456789abcdef' for c in ident):
        raise HTTPException(404,'Batch not found.')
    folder=DATA/ident
    if not (folder/'batch.json').is_file():
        raise HTTPException(404,'Batch not found or expired.')
    return folder

@app.post('/api/batches')
async def create_batch(request:BatchRequest):
    cleanup_expired()
    try:
        state=batch.new_batch([f.model_dump() for f in request.files],request.mode)
    except (ConversionError,KeyError) as exc:
        raise HTTPException(400,str(exc)) from exc
    ident=uuid.uuid4().hex;folder=DATA/ident;folder.mkdir()
    state['id']=ident;batch.save(folder,state)
    return batch.summarize(state)

@app.post('/api/batches/{ident}/files/{index}')
async def upload_batch_file(ident:str,index:int,file:UploadFile=File(...)):
    folder=batch_folder(ident);state=batch.load(folder)
    if state['status']!='uploading' or not 0<=index<len(state['entries']):
        await file.close();raise HTTPException(409,'Batch is not accepting this file.')
    entry=state['entries'][index]
    if entry['status']!='pending':
        await file.close();raise HTTPException(409,'File was already uploaded or skipped.')
    job_id=uuid.uuid4().hex;job=DATA/job_id;job.mkdir()
    try:
        size=0
        with (job/'original.pptx').open('wb') as out:
            while chunk:=await file.read(1024*1024):
                size+=len(chunk)
                if size>batch.MAX_FILE or size>entry['size']:
                    raise ConversionError('Upload exceeds its declared size or the 60 MB limit.')
                out.write(chunk)
        if size!=entry['size']:
            raise ConversionError('Upload was incomplete; file size did not match.')
        # Reload after awaited I/O so concurrent requests cannot erase other entries.
        state=batch.load(folder)
        if state['status']!='uploading' or state['entries'][index]['status']!='pending':
            raise ConversionError('Batch changed during upload.')
        state['entries'][index].update(status='queued',job_id=job_id)
        batch.save(folder,state)
        return {'status':'queued'}
    except Exception as exc:
        shutil.rmtree(job,ignore_errors=True)
        state=batch.load(folder)
        if state['status']=='uploading' and state['entries'][index]['status']=='pending':
            state['entries'][index].update(status='failed',message=str(exc) if isinstance(exc,ConversionError) else 'Upload failed.')
            batch.save(folder,state)
        raise HTTPException(400,'Upload failed: '+str(exc) if isinstance(exc,ConversionError) else 'Upload failed.') from exc
    finally:
        await file.close()

async def run_batch(folder):
    state=batch.load(folder)
    try:
        state['status']='running';batch.save(folder,state)
        for index in range(len(state['entries'])):
            entry=state['entries'][index]
            if entry['status']!='queued':continue
            state['current']=entry['path'];entry['status']='converting';batch.save(folder,state)
            try:
                async with lock:
                    report=await run_in_threadpool(batch.process_item,DATA/entry['job_id'],state['mode'])
                if report.get('skip_reason'):
                    entry.update(status='skipped',message=report['skip_reason'])
                    batch.save(folder,state)
                    continue
                path=PurePosixPath(entry['path'])
                output=str(PurePosixPath('presentations')/path.parent/(path.stem+'-widescreen.pptx'))
                entry.update(status='unchanged' if report['already_wide'] else 'converted',output=output,
                             warnings=report['warnings'],slide_count=report['slide_count'],preview_count=report['preview_count'])
            except Exception as exc:
                entry.update(status='failed',message=str(exc) if isinstance(exc,(ConversionError,ValueError,KeyError)) else 'Conversion failed; check this file in PowerPoint.')
            batch.save(folder,state)
        state.update(status='completed',current=None)
        # Publish the final state only after the downloadable archive exists.
        await run_in_threadpool(batch.archive,folder,state,DATA)
        batch.save(folder,state)
    except Exception:
        state.update(status='failed',current=None,error='Could not finish the ZIP. Completed individual files may still be downloaded.')
        batch.save(folder,state)
    finally:
        TASKS.pop(state['id'],None)

@app.post('/api/batches/{ident}/start')
async def start_batch(ident:str):
    folder=batch_folder(ident);state=batch.load(folder)
    if state['status']!='uploading':
        raise HTTPException(409,'Batch was already started.')
    for entry in state['entries']:
        if entry['status']=='pending':entry.update(status='failed',message='File was not uploaded.')
    state['status']='queued';batch.save(folder,state)
    TASKS[ident]=asyncio.create_task(run_batch(folder))
    return batch.summarize(state)

@app.get('/api/batches/{ident}')
async def batch_status(ident:str):
    folder=batch_folder(ident);state=batch.load(folder)
    if state['status'] in ('queued','running') and ident not in TASKS:
        for entry in state['entries']:
            if entry['status'] not in batch.TERMINAL:
                entry.update(status='failed',message='Interrupted by a server restart. Select the folder again to retry.')
        state.update(status='interrupted',current=None)
        await run_in_threadpool(batch.archive,folder,state,DATA)
        batch.save(folder,state)
    return batch.summarize(state)

@app.get('/api/batches/{ident}/download')
def download_batch(ident:str):
    folder=batch_folder(ident);state=batch.load(folder)
    path=folder/'batch-outputs.zip'
    if state['status'] not in ('completed','interrupted') or not path.is_file():
        raise HTTPException(409,'The ZIP is not ready.')
    return FileResponse(path,filename='SlideStretch-widescreen.zip')

@app.post('/api/batches/{ident}/items/{index}/preview')
async def batch_preview(ident:str,index:int,full:bool=False):
    folder=batch_folder(ident);state=batch.load(folder)
    if not 0<=index<len(state['entries']) or state['entries'][index]['status'] not in ('converted','unchanged'):
        raise HTTPException(404,'Converted presentation not found.')
    entry=state['entries'][index]
    try:
        async with lock:
            report=await run_in_threadpool(batch.preview_item,DATA/entry['job_id'],full)
    except ConversionError as exc:
        raise HTTPException(400,str(exc)) from exc
    return {'id':entry['job_id'],**report}
