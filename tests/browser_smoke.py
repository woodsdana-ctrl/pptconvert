"""Optional browser check: requires Playwright and system Chromium; start app first."""
import os
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b=p.chromium.launch(headless=True,executable_path='/usr/bin/chromium',args=['--no-sandbox'])
    page=b.new_page(viewport={'width':1440,'height':1100},device_scale_factor=1)
    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(os.environ.get('SLIDESTRETCH_URL','http://127.0.0.1:8000'))
    page.screenshot(path='artifacts/app-before-upload.png',full_page=True)
    page.locator('#file').set_input_files('artifacts/representative-4x3.pptx')
    page.locator('#submit').click()
    page.locator('#download').wait_for(state='visible',timeout=120000)
    page.wait_for_function("document.getElementById('after').complete && document.getElementById('after').naturalWidth > 0")
    assert '3 slides converted' in page.locator('#status').inner_text()
    assert page.locator('#before').evaluate('(e)=>e.naturalWidth')==1600
    page.screenshot(path='artifacts/app-editable-preview.png',full_page=True)
    with page.expect_download() as download:
        page.locator('#download').click()
    download.value.save_as('artifacts/representative-editable.pptx')
    page.locator('#next').click();assert 'Slide 2 of 3' in page.locator('#counter').inner_text()
    page.locator('input[value="visual"]').check()
    page.locator('#submit').click()
    page.locator('#download').wait_for(state='visible',timeout=120000)
    page.wait_for_function("document.getElementById('after').complete && document.getElementById('after').naturalWidth > 0")
    assert page.locator('#preview-tag').inner_text()=='VISUAL MATCH'
    with page.expect_download() as download:
        page.locator('#download').click()
    download.value.save_as('artifacts/representative-visual.pptx')
    page.screenshot(path='artifacts/app-visual-preview.png',full_page=True)
    assert not errors,errors
    page.set_viewport_size({'width':390,'height':844})
    page.screenshot(path='artifacts/app-mobile.png',full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    print('Browser checks passed: upload, editable preview/download, slide navigation, visual preview/download, mobile layout, no JavaScript errors.')
    b.close()
