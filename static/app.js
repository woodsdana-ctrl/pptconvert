const $=id=>document.getElementById(id);
let result=null,slide=1,uploadType='single',busy=false,currentBatch=null,pollTimer=null,selectedBatchIndex=null;
const terminal=new Set(['converted','unchanged','skipped','failed']);
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function api(url,options={}){
  const response=await fetch(url,options);
  const data=await response.json();
  if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'The request failed. Please try again.');
  return data;
}
function setType(type){
  if(busy)return;
  uploadType=type;
  $('drop').hidden=type!=='single';$('folder-picker').hidden=type!=='folder';
  $('file').required=type==='single';$('folder').required=type==='folder';
  $('single-tab').classList.toggle('active',type==='single');$('folder-tab').classList.toggle('active',type==='folder');
  resetButton();
}
function resetButton(){ $('submit').innerHTML=(uploadType==='folder'?'Convert folder':'Convert to widescreen')+' <span aria-hidden="true">→</span>'; }
function setBusy(value){
  busy=value;$('submit').disabled=value;
  document.querySelectorAll('#form input, .input-tabs button').forEach(el=>el.disabled=value);
  if(!value)resetButton();
}
$('single-tab').onclick=()=>setType('single');$('folder-tab').onclick=()=>setType('folder');
document.querySelectorAll('input[name="mode"]').forEach(input=>input.addEventListener('change',()=>document.querySelectorAll('.mode').forEach(label=>label.classList.toggle('selected',label.contains(document.querySelector('input[name="mode"]:checked'))))));
function fileChanged(){const file=$('file').files[0];$('filename').textContent=file?file.name:'Drop a PowerPoint here';$('filehint').textContent=file?`${(file.size/1024/1024).toFixed(1)} MB · Ready to convert`:'or click to browse · .pptx up to 60 MB';}
$('file').addEventListener('change',fileChanged);
$('folder').addEventListener('change',()=>{
  const files=Array.from($('folder').files);
  const decks=files.filter(f=>f.name.toLowerCase().endsWith('.pptx')&&!f.name.startsWith('~$'));
  $('folder-name').textContent=files.length?files[0].webkitRelativePath.split('/')[0]:'Choose a folder of presentations';
  $('folder-summary').textContent=`${files.length} files selected · ${decks.length} PowerPoint presentations · includes subfolders. Other files will be reported as skipped.`;
});
['dragenter','dragover'].forEach(name=>$('drop').addEventListener(name,e=>{e.preventDefault();if(!busy)$('drop').classList.add('drag')}));
['dragleave','drop'].forEach(name=>$('drop').addEventListener(name,e=>{e.preventDefault();$('drop').classList.remove('drag')}));
$('drop').addEventListener('drop',e=>{if(!busy&&e.dataTransfer.files.length){$('file').files=e.dataTransfer.files;fileChanged()}});
function showSlide(){if(!result||!result.preview_count)return;const base=`/api/jobs/${result.id}/preview`;$('before').src=`${base}/before/${slide}`;$('after').src=`${base}/after/${slide}`;$('counter').textContent=`Slide ${slide} of ${result.preview_count}`;$('prev').disabled=slide===1;$('next').disabled=slide===result.preview_count;}
$('prev').onclick=()=>{slide--;showSlide()};$('next').onclick=()=>{slide++;showSlide()};
function showResult(data,firstOnly=false){
  result=data;slide=1;$('placeholder').hidden=true;$('results').hidden=false;
  $('preview-tag').textContent=data.already_wide?'ALREADY 16:9':data.mode==='visual'?'VISUAL MATCH':'EDITABLE';
  $('download').href=`/api/jobs/${data.id}/widescreen.pptx`;$('report').href=`/api/jobs/${data.id}/report.json`;
  $('after-label').textContent=`${data.already_wide?'UNCHANGED':'CONVERTED'} · 16:9`;
  document.querySelectorAll('#results figure, .slide-nav').forEach(el=>el.hidden=!data.preview_count);
  $('full-preview').hidden=!firstOnly||data.slide_count<=data.preview_count;
  $('full-preview').disabled=false;$('full-preview').textContent='Preview all slides in this presentation';
  showSlide();
  $('warning-list').replaceChildren(...data.warnings.map(w=>{const li=document.createElement('li');li.textContent=w;return li}));$('warnings').hidden=false;
}
function rememberBatch(id){try{localStorage.setItem('slidestretch-batch',id)}catch{}}
function renderBatch(data){
  currentBatch=data;$('batch-results').hidden=false;
  $('batch-progress').max=data.total;$('batch-progress').value=data.done;
  const finished=['completed','interrupted','failed'].includes(data.status);
  $('batch-heading').textContent=data.status==='completed'?'Your folder is ready':data.status==='interrupted'?'Batch interrupted':data.status==='failed'?'Batch could not finish':'Converting your folder';
  $('batch-status').textContent=`${data.done} of ${data.total} files processed`+(data.current?` · ${data.current}`:'');
  $('batch-counts').textContent=`${data.counts.converted} converted · ${data.counts.unchanged} already widescreen · ${data.counts.skipped} skipped · ${data.counts.failed} failed`;
  $('batch-download').hidden=!['completed','interrupted'].includes(data.status);
  $('batch-download').href=`/api/batches/${data.id}/download`;
  $('batch-error').textContent=data.error|| (data.status==='interrupted'?'The server restarted. The ZIP contains completed results and an interruption report. Select the folder again to retry the remaining files.':'');
  // Update rows in place so polling never replaces a focused preview button.
  data.entries.forEach((entry,index)=>{
    let row=$(`batch-row-${index}`);
    if(!row){row=document.createElement('div');row.id=`batch-row-${index}`;row.className='batch-row';const label=document.createElement('div');label.className='batch-file';const path=document.createElement('strong');path.className='batch-path';const detail=document.createElement('span');detail.className='batch-detail';label.append(path,detail);const actions=document.createElement('div');actions.className='batch-actions';const badge=document.createElement('span');badge.className='batch-badge';const button=document.createElement('button');button.type='button';button.textContent='Preview';button.className='secondary';button.onclick=()=>openBatchPreview(index);actions.append(badge,button);row.append(label,actions);$('batch-list').append(row)}
    row.querySelector('.batch-path').textContent=entry.path;
    row.querySelector('.batch-detail').textContent=entry.message||(entry.warnings.length?entry.warnings.join(' '):entry.output||'');
    row.querySelector('.batch-badge').textContent=entry.status==='unchanged'?'Already 16:9':entry.status;
    row.querySelector('button').hidden=!['converted','unchanged'].includes(entry.status);
  });
  if(finished){setBusy(false);$('status').textContent='Folder processing finished. Review the per-file results below.'}
}
async function pollBatch(id){
  try{
    const data=await api(`/api/batches/${id}`);
    if(currentBatch&&currentBatch.id!==id)return;
    renderBatch(data);
    if(['queued','running'].includes(data.status))pollTimer=setTimeout(()=>pollBatch(id),1000);
  }catch(error){$('batch-error').textContent=`Progress connection interrupted: ${error.message} Retrying…`;pollTimer=setTimeout(()=>pollBatch(id),3000)}
}
async function openBatchPreview(index,full=false){
  const id=currentBatch?.id;if(!id)return;
  selectedBatchIndex=index;
  $('status').textContent=full?'Rendering all slides for this presentation…':'Opening the first-slide preview…';
  try{
    const data=await api(`/api/batches/${id}/items/${index}/preview?full=${full}`,{method:'POST'});
    if(currentBatch?.id!==id||selectedBatchIndex!==index)return;
    showResult(data,true);$('status').textContent=`Preview: ${currentBatch.entries[index].path}`;
    $('results').scrollIntoView({behavior:'smooth',block:'nearest'});
  }catch(error){$('status').textContent=error.message;$('full-preview').disabled=false}
}
$('full-preview').onclick=()=>{$('full-preview').disabled=true;openBatchPreview(selectedBatchIndex,true)};
async function convertFolder(mode){
  const files=Array.from($('folder').files);
  if(!files.length)throw new Error('Choose a folder first.');
  if(files.length>1000)throw new Error('Select a smaller folder: maximum 1,000 files including skipped files.');
  const metadata=files.map(f=>({path:f.webkitRelativePath||f.name,size:f.size}));
  const data=await api('/api/batches',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode,files:metadata})});
  rememberBatch(data.id);$('batch-list').replaceChildren();renderBatch(data);
  $('batch-heading').textContent='Uploading your folder';
  for(let i=0;i<files.length;i++){
    if(data.entries[i].status!=='pending')continue;
    $('status').textContent=`Uploading ${i+1} of ${files.length}: ${metadata[i].path}`;
    const body=new FormData();body.append('file',files[i]);
    try{await api(`/api/batches/${data.id}/files/${i}`,{method:'POST',body})}
    catch(error){$('batch-error').textContent=`${metadata[i].path}: ${error.message} Other files will continue.`}
  }
  await api(`/api/batches/${data.id}/start`,{method:'POST'});
  $('status').textContent='Folder uploaded. You may leave this page open to follow progress.';
  await pollBatch(data.id);
}
$('form').addEventListener('submit',async e=>{
  e.preventDefault();if(busy)return;
  const mode=document.querySelector('input[name="mode"]:checked').value;
  const file=$('file').files[0];
  if(uploadType==='single'&&(!file||file.size>60*1024*1024)){$('status').textContent='Choose a .pptx file up to 60 MB.';return}
  clearTimeout(pollTimer);setBusy(true);$('submit').textContent='Preparing conversion…';
  $('results').hidden=true;$('placeholder').hidden=false;$('warnings').hidden=true;
  $('batch-download').hidden=true;selectedBatchIndex=null;currentBatch=null;
  try{
    if(uploadType==='folder'){await convertFolder(mode);return}
    $('batch-results').hidden=true;currentBatch=null;selectedBatchIndex=null;
    const body=new FormData();body.append('file',file);body.append('mode',mode);
    $('status').textContent='Preparing your presentation. Rendering larger decks may take several minutes.';
    const data=await api('/api/convert',{method:'POST',body});showResult(data);
    $('status').textContent=data.already_wide?'Already widescreen. Your file was copied without stretching.':`${data.slide_count} slide${data.slide_count===1?'':'s'} converted. Review the preview before downloading.`;
    setBusy(false);
  }catch(error){$('status').textContent=error.message;$('preview-tag').textContent='ILLUSTRATION';setBusy(false)}
});
// A page refresh can reconnect to a running batch. Uploads need the selected
// browser File objects again, so an interrupted upload must be reselected.
(async()=>{
  let id;try{id=localStorage.getItem('slidestretch-batch')}catch{return}
  if(!id||!/^[a-f0-9]{32}$/.test(id))return;
  try{
    const data=await api(`/api/batches/${id}`);
    setType('folder');renderBatch(data);
    if(['queued','running'].includes(data.status)){setBusy(true);pollBatch(id)}
    else if(data.status==='uploading')$('status').textContent='Previous upload did not finish. Select the folder again to start a new batch.';
  }catch{/* Expired results do not block a fresh conversion. */}
})();
