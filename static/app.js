const $=id=>document.getElementById(id);
let result=null,slide=1;
document.querySelectorAll('input[name="mode"]').forEach(input=>input.addEventListener('change',()=>document.querySelectorAll('.mode').forEach(label=>label.classList.toggle('selected',label.contains(document.querySelector('input[name="mode"]:checked'))))));
function fileChanged(){const file=$('file').files[0];$('filename').textContent=file?file.name:'Drop a PowerPoint here';$('filehint').textContent=file?`${(file.size/1024/1024).toFixed(1)} MB · Ready to convert`:'or click to browse · .pptx up to 60 MB';}
$('file').addEventListener('change',fileChanged);
['dragenter','dragover'].forEach(name=>$('drop').addEventListener(name,e=>{e.preventDefault();$('drop').classList.add('drag')}));
['dragleave','drop'].forEach(name=>$('drop').addEventListener(name,e=>{e.preventDefault();$('drop').classList.remove('drag')}));
$('drop').addEventListener('drop',e=>{if(e.dataTransfer.files.length){$('file').files=e.dataTransfer.files;fileChanged()}});
function showSlide(){if(!result||!result.preview_count)return;const base=`/api/jobs/${result.id}/preview`;$('before').src=`${base}/before/${slide}`;$('after').src=`${base}/after/${slide}`;$('counter').textContent=`Slide ${slide} of ${result.preview_count}`;$('prev').disabled=slide===1;$('next').disabled=slide===result.preview_count;}
$('prev').onclick=()=>{slide--;showSlide()};$('next').onclick=()=>{slide++;showSlide()};
$('form').addEventListener('submit',async e=>{e.preventDefault();const file=$('file').files[0];if(!file)return;if(file.size>60*1024*1024){$('status').textContent='Maximum file size is 60 MB.';return}
$('submit').disabled=true;$('submit').textContent='Converting & rendering…';$('status').textContent='Preparing your presentation. Rendering larger decks may take several minutes.';
$('results').hidden=true;$('placeholder').hidden=false;$('warnings').hidden=true;
try{const response=await fetch('/api/convert',{method:'POST',body:new FormData($('form'))});const data=await response.json();if(!response.ok)throw new Error(data.detail||'Conversion failed.');result=data;slide=1;$('placeholder').hidden=true;$('results').hidden=false;$('preview-tag').textContent=data.already_wide?'ALREADY 16:9':data.mode==='visual'?'VISUAL MATCH':'EDITABLE';$('download').href=`/api/jobs/${data.id}/widescreen.pptx`;$('report').href=`/api/jobs/${data.id}/report.json`;$('after-label').textContent=`${data.already_wide?'UNCHANGED':'CONVERTED'} · 16:9`;
const noPreview=!data.preview_count;document.querySelectorAll('#results figure, .slide-nav').forEach(el=>el.hidden=noPreview);showSlide();$('status').textContent=data.already_wide?'Already widescreen. Your file was copied without stretching.':`${data.slide_count} slide${data.slide_count===1?'':'s'} converted. Review the preview before downloading.`;
$('warning-list').replaceChildren(...data.warnings.map(w=>{const li=document.createElement('li');li.textContent=w;return li}));$('warnings').hidden=false;
}catch(error){$('status').textContent=error.message;$('preview-tag').textContent='ILLUSTRATION'}finally{$('submit').disabled=false;$('submit').innerHTML='Convert to widescreen <span aria-hidden="true">→</span>'}});
