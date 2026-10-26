"""Loss-minimizing OOXML geometry conversion and rendered visual conversion."""
from __future__ import annotations
import argparse
import json
import posixpath
import shutil
import subprocess
import tempfile
from pathlib import Path
from zipfile import ZipFile, BadZipFile
from lxml import etree as E
import fitz
from PIL import Image

NS = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
FACTOR = 4 / 3

class ConversionError(ValueError):
    pass

def xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ConversionError('XML entity declarations are not supported.')
    return E.fromstring(data, E.XMLParser(resolve_entities=False, no_network=True))

def serialized(root):
    return E.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)

def read_package(path):
    try:
        with ZipFile(path) as z:
            infos = z.infolist()
            names = [i.filename for i in infos]
            if len(infos) > 20000 or sum(i.file_size for i in infos) > 400*1024**2:
                raise ConversionError('Presentation is too large (400 MB expanded / 20,000 parts limit).')
            if len(names) != len(set(names)):
                raise ConversionError('Duplicate package parts are not supported.')
            if any(n.startswith('/') or '..' in n.split('/') for n in names):
                raise ConversionError('Unsafe package paths.')
            parts = {i.filename:z.read(i) for i in infos}
    except (BadZipFile, RuntimeError) as exc:
        raise ConversionError('Use an unencrypted .pptx presentation.') from exc
    if 'ppt/presentation.xml' not in parts:
        raise ConversionError('This file is not a PowerPoint OOXML presentation.')
    return parts

def inspect(parts):
    root = xml(parts['ppt/presentation.xml'])
    size = root.find('p:sldSz',NS)
    if size is None:
        raise ConversionError('Missing slide dimensions.')
    w,h = int(size.get('cx')),int(size.get('cy'))
    if w <= 0 or h <= 0:
        raise ConversionError('Invalid slide dimensions.')
    ratio=w/h
    kind = '16:9' if abs(ratio-16/9)<0.002 else '4:3' if abs(ratio-4/3)<0.002 else 'other'
    rels = xml(parts['ppt/_rels/presentation.xml.rels'])
    targets = {r.get('Id'):posixpath.normpath(posixpath.join('ppt',r.get('Target'))) for r in rels if r.get('TargetMode')!='External'}
    slides = [targets[s.get('{'+NS['r']+'}id')] for s in root.findall('p:sldIdLst/p:sldId',NS)]
    if not slides:
        raise ConversionError('The presentation has no slides.')
    warnings=[]
    for n,b in parts.items():
        if not n.endswith('.xml') or not n.startswith('ppt/'):
            continue
        x=xml(b)
        if x.xpath('//*[@rot and @rot!="0"]'):
            warnings.append('Rotated objects: editable geometry cannot exactly reproduce an anisotropic stretch of a rotation.')
        if '/diagrams/' in n or b'<dgm:' in b:
            warnings.append('SmartArt may regenerate its internal layout; use Visual match for appearance fidelity.')
        if b'<p:oleObj' in b or b'<p:video' in b or b'<p:audio' in b:
            warnings.append('Embedded or interactive media needs manual review; visual mode captures only its static rendering.')
    return dict(width=w,height=h,ratio=kind,slides=slides,warnings=list(dict.fromkeys(warnings)))

def scale_attr(el, attr):
    if el.get(attr) is not None:
        value=int(el.get(attr))
        # Exact rational arithmetic, including negative coordinates.
        el.set(attr,str((value*4+1)//3))

def scale_geometry(root):
    # Scale BOTH group coordinate systems and all child coordinates. ext/chExt
    # remains constant, so nested groups do not multiply the stretch again.
    for el in root.iter():
        if not isinstance(el.tag,str):
            continue
        q=E.QName(el)
        if q.namespace not in (NS['a'],NS['p']):
            continue
        tag=q.localname
        if tag in ('off','chOff'):
            scale_attr(el,'x')
        elif tag in ('ext','chExt'):
            scale_attr(el,'cx')
        elif tag=='gridCol':
            scale_attr(el,'w')
        elif tag=='bodyPr':
            # DrawingML's omitted left/right inset defaults are 91440 EMU.
            for attr in ('lIns','rIns'):
                if el.get(attr) is None:
                    el.set(attr,'91440')
                scale_attr(el,attr)
            scale_attr(el,'spcCol')
        elif tag=='tcPr':
            for attr in ('marL','marR'):
                if el.get(attr) is None:
                    el.set(attr,'91440')
                scale_attr(el,attr)
        elif tag.endswith('pPr') or (tag.startswith('lvl') and tag.endswith('pPr')):
            for attr in ('marL','marR','indent'):
                scale_attr(el,attr)
        elif tag=='tab':
            scale_attr(el,'pos')
    # Font sizes, character spacing, row heights, y/cy and normalized crop
    # percentages are deliberately untouched. Glyphs are NOT stretched.

def write_package(parts, destination):
    with ZipFile(destination,'w',compression=8) as z:
        for name,data in parts.items():
            z.writestr(name,data)

def render(source, output, width=1200):
    """Render with an isolated profile; never round-trip the editable output."""
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='ppt-render-') as tmp:
        tmp=Path(tmp)
        inbox=tmp/'input'; inbox.mkdir()
        safe=inbox/'deck.pptx'; shutil.copyfile(source,safe)
        out=tmp/'pdf'; out.mkdir()
        filter_spec='pdf:impress_pdf_Export:{"ExportHiddenSlides":{"type":"boolean","value":"true"}}'
        try:
            proc=subprocess.run(['soffice','-env:UserInstallation='+ (tmp/'profile').as_uri(),
                '--headless','--convert-to',filter_spec,'--outdir',str(out),str(safe)],
                capture_output=True,text=True,timeout=180)
        except (FileNotFoundError,subprocess.TimeoutExpired) as exc:
            raise ConversionError('Slide rendering requires LibreOffice and must finish within 180 seconds.') from exc
        pdf=out/'deck.pdf'
        if proc.returncode or not pdf.exists():
            raise ConversionError('LibreOffice could not render this presentation. Check that it opens correctly in PowerPoint.')
        shutil.copyfile(pdf, output/'render.pdf')
        pages=[]
        with fitz.open(pdf) as doc:
            if len(doc)>150:
                raise ConversionError('Preview and visual mode support up to 150 slides.')
            for i,page in enumerate(doc):
                path=output/f'{i+1}.png'
                page.get_pixmap(matrix=fitz.Matrix(width/page.rect.width,width/page.rect.width),alpha=False).save(path)
                pages.append(path)
        return pages

def flatten(parts, info, images):
    if len(images)!=len(info['slides']):
        raise ConversionError('Rendered slide count differs from the deck; refusing to mismatch slides.')
    types=xml(parts['[Content_Types].xml'])
    if not any(e.get('Extension')=='png' for e in types):
        E.SubElement(types,'{'+CT+'}Default',Extension='png',ContentType='image/png')
    parts['[Content_Types].xml']=serialized(types)
    w=(info['width']*4+1)//3; h=info['height']
    for index,(name,image) in enumerate(zip(info['slides'],images)):
        root=xml(parts[name]); root.set('showMasterSp','0'); root.set('showMasterPhAnim','0')
        tree=root.find('p:cSld/p:spTree',NS)
        if tree is None:
            raise ConversionError('Slide has no shape tree.')
        for child in list(tree):
            if child.tag not in ('{'+NS['p']+'}nvGrpSpPr','{'+NS['p']+'}grpSpPr'):
                tree.remove(child)
        for el in root.findall('p:timing',NS):
            root.remove(el)
        relname=posixpath.join(posixpath.dirname(name),'_rels',posixpath.basename(name)+'.rels')
        rels=xml(parts[relname]) if relname in parts else E.Element('{'+REL+'}Relationships')
        rid='rIdStretchImage'
        ids={r.get('Id') for r in rels}
        while rid in ids:
            rid+='x'
        media=f'ppt/media/stretch-{index+1}.png'
        while media in parts:
            media=media[:-4]+'x.png'
        with Image.open(image) as im:
            # Constant pixel height: stretch only horizontally.
            import io
            buf=io.BytesIO()
            im.resize((round(im.width*FACTOR),im.height),Image.Resampling.LANCZOS).save(buf,format='PNG')
            parts[media]=buf.getvalue()
        E.SubElement(rels,'{'+REL+'}Relationship',Id=rid,Type=NS['r']+'/image',Target=posixpath.relpath(media,posixpath.dirname(name)))
        pic=E.SubElement(tree,'{'+NS['p']+'}pic')
        nv=E.SubElement(pic,'{'+NS['p']+'}nvPicPr')
        E.SubElement(nv,'{'+NS['p']+'}cNvPr',id='2',name='Stretched slide image')
        E.SubElement(nv,'{'+NS['p']+'}cNvPicPr');E.SubElement(nv,'{'+NS['p']+'}nvPr')
        fill=E.SubElement(pic,'{'+NS['p']+'}blipFill')
        E.SubElement(fill,'{'+NS['a']+'}blip',{'{'+NS['r']+'}embed':rid})
        E.SubElement(E.SubElement(fill,'{'+NS['a']+'}stretch'),'{'+NS['a']+'}fillRect')
        sp=E.SubElement(pic,'{'+NS['p']+'}spPr');xf=E.SubElement(sp,'{'+NS['a']+'}xfrm')
        E.SubElement(xf,'{'+NS['a']+'}off',x='0',y='0');E.SubElement(xf,'{'+NS['a']+'}ext',cx=str(w),cy=str(h))
        E.SubElement(E.SubElement(sp,'{'+NS['a']+'}prstGeom',prst='rect'),'{'+NS['a']+'}avLst')
        parts[name]=serialized(root); parts[relname]=serialized(rels)

def convert(source, destination, mode='editable', images=None):
    source,destination=Path(source),Path(destination)
    if source.resolve()==destination.resolve():
        raise ConversionError('Choose a new output path; the original must remain unchanged.')
    if mode not in ('editable','visual'):
        raise ConversionError('Mode must be editable or visual.')
    parts=read_package(source); info=inspect(parts)
    report={k:v for k,v in info.items() if k!='slides'}
    report.update(mode=mode,slide_count=len(info['slides']),already_wide=info['ratio']=='16:9',
                  source_width=info['width'],source_height=info['height'],source_ratio=info['ratio'],
                  output_width=info['width'] if info['ratio']=='16:9' else (info['width']*4+1)//3,
                  output_height=info['height'],output_ratio='16:9')
    if info['ratio']=='other':
        raise ConversionError(f"Unsupported aspect ratio {info['width']/info['height']:.4f}; expected 4:3 or 16:9. No output written.")
    if info['ratio']=='16:9':
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,destination)
        report['warnings'].append('Already 16:9: copied unchanged, without stretching or flattening.')
        return report
    if mode=='editable':
        report['warnings'].append('Editable mode does not stretch glyphs. Automatic line breaks, alignment, charts and font substitution may change appearance. Explicit breaks and font sizes are retained.')
        for name in list(parts):
            if name.endswith('.xml') and name.startswith(('ppt/slides/','ppt/slideLayouts/','ppt/slideMasters/','ppt/drawings/')):
                root=xml(parts[name]); scale_geometry(root); parts[name]=serialized(root)
    else:
        report['warnings'].append('Visual match uses LibreOffice rendering, which may differ from PowerPoint. Visible content is a flat image: object editing, hyperlinks, media playback and animations are lost. Speaker notes and slide transitions are retained; legacy unused package parts may remain.')
        if images is None:
            with tempfile.TemporaryDirectory() as tmp:
                flatten(parts,info,render(source,tmp,width=1920))
        else:
            flatten(parts,info,images)
    root=xml(parts['ppt/presentation.xml']); size=root.find('p:sldSz',NS)
    size.set('cx',str((info['width']*4+1)//3));size.set('type','screen16x9')
    parts['ppt/presentation.xml']=serialized(root)
    # Write atomically so failures do not leave a partial presentation.
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=destination.parent,suffix='.pptx',delete=False) as tmp:
        pending=Path(tmp.name)
    try:
        write_package(parts,pending); pending.replace(destination)
    finally:
        pending.unlink(missing_ok=True)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source');parser.add_argument('destination');parser.add_argument('--mode',choices=['editable','visual'],default='editable')
    args=parser.parse_args()
    try:
        print(json.dumps(convert(args.source,args.destination,args.mode),indent=2))
    except ConversionError as exc:
        parser.exit(2,str(exc)+'\n')
