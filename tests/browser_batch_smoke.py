"""Optional real-browser folder upload check against a running local app."""
import io
import json
import os
import tempfile
from pathlib import Path
from zipfile import ZipFile
from playwright.sync_api import sync_playwright
from converter import convert
from tests.fixtures import make_deck

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp)/'Lessons';(root/'Science').mkdir(parents=True);(root/'Math').mkdir()
    source=make_deck(root/'Science/lesson.pptx')
    (root/'Math/lesson.pptx').write_bytes(source.read_bytes())
    convert(source,root/'wide.pptx')
    (root/'broken.pptx').write_bytes(b'broken')
    (root/'old.ppt').write_bytes(b'legacy')
    (root/'~$temp.pptx').write_bytes(b'lock')
    hashes={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        page=browser.new_page(viewport={'width':1440,'height':1100})
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(os.environ.get('SLIDESTRETCH_URL','http://127.0.0.1:8000'))
        page.locator('#folder-tab').click()
        page.locator('#folder').set_input_files(str(root))
        assert '7 files selected' in page.locator('#folder-summary').inner_text()
        for mode in ['editable','visual']:
            page.locator('#folder').set_input_files(str(root))
            page.locator(f'input[value="{mode}"]').check()
            page.locator('#submit').click()
            page.locator('#batch-download').wait_for(state='visible',timeout=180000)
            assert page.locator('#batch-heading').inner_text()=='Your folder is ready'
            assert '2 converted · 1 already widescreen · 3 skipped · 1 failed' in page.locator('#batch-counts').inner_text()
            with page.expect_download() as info:page.locator('#batch-download').click()
            dest=Path('artifacts')/f'browser-folder-{mode}.zip';info.value.save_as(str(dest))
            with ZipFile(dest) as z:
                assert 'presentations/Lessons/Science/lesson-widescreen.pptx' in z.namelist()
                assert 'presentations/Lessons/Math/lesson-widescreen.pptx' in z.namelist()
                assert z.read('presentations/Lessons/wide-widescreen.pptx')==hashes['wide.pptx']
                report=json.loads(z.read('batch-report.json'))
                good_index=next(i for i,e in enumerate(report['entries']) if e['status']=='converted')
            page.locator(f'#batch-row-{good_index} button').click()
            page.locator('#full-preview').wait_for(state='visible',timeout=60000)
            assert page.locator('#counter').inner_text()=='Slide 1 of 1'
            page.locator('#full-preview').click()
            page.wait_for_function("document.getElementById('counter').textContent === 'Slide 1 of 3'",timeout=60000)
            page.locator('#next').click()
            assert page.locator('#counter').inner_text()=='Slide 2 of 3'
            page.screenshot(path=f'artifacts/app-folder-{mode}.png',full_page=True)
            page.reload()
            page.locator('#batch-download').wait_for(state='visible',timeout=10000)
            assert '2 converted' in page.locator('#batch-counts').inner_text()
        page.set_viewport_size({'width':390,'height':844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert not errors,errors
        browser.close()
    for rel,data in hashes.items():assert (root/rel).read_bytes()==data
    print('Folder browser checks passed in editable and visual modes: folder picker, nested paths, mixed outcomes, ZIP, first/full previews, navigation, refresh recovery, original preservation, mobile bounds, no JavaScript errors.')
