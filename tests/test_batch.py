import io
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile
from fastapi.testclient import TestClient
import app as server
import batch
from converter import ConversionError,convert,inspect,read_package,serialized,write_package,xml,NS
from tests.fixtures import make_deck

class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.base=Path(cls.tmp.name)
        cls.original=make_deck(cls.base/'sample.pptx').read_bytes()
        convert(cls.base/'sample.pptx',cls.base/'wide.pptx')
        cls.wide=(cls.base/'wide.pptx').read_bytes()
        parts=read_package(cls.base/'sample.pptx');root=xml(parts['ppt/presentation.xml'])
        root.find('p:sldSz',NS).set('cx','6858000');parts['ppt/presentation.xml']=serialized(root)
        write_package(parts,cls.base/'square.pptx');cls.square=(cls.base/'square.pptx').read_bytes()
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def setUp(self):
        self.storage=tempfile.TemporaryDirectory();self.root=Path(self.storage.name)
        self.patch=patch.object(server,'DATA',self.root);self.patch.start()
        self.context=TestClient(server.app);self.client=self.context.__enter__()
    def tearDown(self):
        self.context.__exit__(None,None,None);self.patch.stop();self.storage.cleanup()
    def wait(self,ident):
        end=time.monotonic()+40
        while time.monotonic()<end:
            response=self.client.get('/api/batches/'+ident);response.raise_for_status();state=response.json()
            if state['status'] in ('completed','interrupted','failed'):return state
            time.sleep(.05)
        self.fail('Batch did not finish within 40 seconds.')
    def test_mixed_folder_preserves_paths_continues_and_exports_reports(self):
        files=[('Lessons/Science/same.pptx',self.original),('Lessons/Math/same.pptx',self.original),
               ('Lessons/wide.pptx',self.wide),('Lessons/square.pptx',self.square),
               ('Lessons/broken.pptx',b'broken'),('Lessons/old.ppt',b'legacy'),
               ('Lessons/~$lock.pptx',b'lock'),('Lessons/readme.txt',b'ignore')]
        response=self.client.post('/api/batches',json={'mode':'editable','files':[{'path':p,'size':len(b)} for p,b in files]})
        self.assertEqual(response.status_code,200,response.text);state=response.json();ident=state['id']
        self.assertEqual(state['counts']['skipped'],3)
        for i,(_,content) in enumerate(files):
            if state['entries'][i]['status']=='pending':
                r=self.client.post(f'/api/batches/{ident}/files/{i}',files={'file':('source.pptx',content)})
                self.assertEqual(r.status_code,200,r.text)
        self.assertEqual(self.client.post(f'/api/batches/{ident}/start').status_code,200)
        state=self.wait(ident);self.assertEqual(state['status'],'completed',state)
        self.assertEqual(state['counts'],dict(converted=2,unchanged=1,skipped=4,failed=1))
        self.assertEqual(state['done'],8)
        data=self.client.get(f'/api/batches/{ident}/download');self.assertEqual(data.status_code,200)
        with ZipFile(io.BytesIO(data.content)) as z:
            self.assertEqual(set(z.namelist()),{'batch-report.json','batch-report.csv',
                'presentations/Lessons/Science/same-widescreen.pptx','presentations/Lessons/Math/same-widescreen.pptx',
                'presentations/Lessons/wide-widescreen.pptx'})
            self.assertEqual(z.read('presentations/Lessons/wide-widescreen.pptx'),self.wide)
            self.assertEqual(json.loads(z.read('batch-report.json'))['counts'],state['counts'])
        entry=state['entries'][0]
        self.assertEqual(entry['preview_count'],1)
        preview=self.client.post(f'/api/batches/{ident}/items/0/preview');self.assertEqual(preview.json()['preview_count'],1)
        full=self.client.post(f'/api/batches/{ident}/items/0/preview?full=true')
        self.assertEqual(full.status_code,200,full.text);self.assertEqual(full.json()['preview_count'],3)
        self.assertEqual(self.client.get(f"/api/jobs/{entry['job_id']}/preview/after/3").status_code,200)
        original_path=self.root/entry['job_id']/'original.pptx'
        self.assertEqual(original_path.read_bytes(),self.original)
    def test_paths_limits_and_missing_uploads(self):
        for path in ['../outside.pptx','/absolute.pptx','Folder/../escape.pptx','C:/drive.pptx','Folder\\escape.pptx','Folder//file.pptx']:
            response=self.client.post('/api/batches',json={'files':[{'path':path,'size':1}]})
            self.assertEqual(response.status_code,400,path)
        response=self.client.post('/api/batches',json={'files':[{'path':'A.pptx','size':0},{'path':'a.pptx','size':0}]})
        self.assertEqual(response.status_code,400)
        with self.assertRaises(ConversionError):batch.new_batch([{'path':f'{i}.pptx','size':batch.MAX_FILE} for i in range(18)],'editable')
        response=self.client.post('/api/batches',json={'files':[{'path':'Big.pptx','size':batch.MAX_FILE+1},{'path':'Missing.pptx','size':3}]})
        ident=response.json()['id'];self.assertEqual(response.json()['entries'][0]['status'],'failed')
        self.assertEqual(self.client.get(f'/api/batches/{ident}/download').status_code,409)
        self.client.post(f'/api/batches/{ident}/start');state=self.wait(ident)
        self.assertEqual(state['counts']['failed'],2)
        self.assertEqual(self.client.get(f'/api/batches/{ident}/download').status_code,200)
    def test_incomplete_upload_does_not_poison_batch(self):
        response=self.client.post('/api/batches',json={'files':[{'path':'bad.pptx','size':10}]})
        ident=response.json()['id']
        r=self.client.post(f'/api/batches/{ident}/files/0',files={'file':('x.pptx',b'1')})
        self.assertEqual(r.status_code,400)
        self.client.post(f'/api/batches/{ident}/start')
        self.assertEqual(self.wait(ident)['entries'][0]['status'],'failed')
    def test_restart_reports_interruption_and_downloads_completed_results(self):
        folder=self.root/('a'*32);folder.mkdir()
        state=batch.new_batch([{'path':'one.pptx','size':1}],'editable');state.update(id='a'*32,status='running')
        state['entries'][0]['status']='converting';batch.save(folder,state)
        result=self.client.get('/api/batches/'+'a'*32).json()
        self.assertEqual(result['status'],'interrupted');self.assertEqual(result['counts']['failed'],1)
        self.assertEqual(self.client.get('/api/batches/'+'a'*32+'/download').status_code,200)

if __name__=='__main__':unittest.main()
