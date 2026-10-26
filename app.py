"""Single-upload local development app. Bind to localhost on trusted machines."""
import asyncio
import json
import shutil
import time
import uuid
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
    for old in DATA.iterdir():
        if old.is_dir() and time.time()-old.stat().st_mtime>86400:
            shutil.rmtree(old,ignore_errors=True)
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
