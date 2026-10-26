import unittest
from fastapi.testclient import TestClient
from app import app

class ApiTests(unittest.TestCase):
    def setUp(self):self.client=TestClient(app)
    def test_legacy_ppt_explains_migration(self):
        response=self.client.post('/api/convert',files={'file':('lesson.ppt',b'legacy')})
        self.assertEqual(response.status_code,400)
        self.assertIn('Save As .pptx',response.json()['detail'])
    def test_invalid_zip_rejected(self):
        response=self.client.post('/api/convert',files={'file':('lesson.pptx',b'not a presentation')})
        self.assertEqual(response.status_code,400)
        self.assertIn('unencrypted',response.json()['detail'])
    def test_assets_are_restricted(self):
        for path in ['/api/jobs/'+'a'*32+'/original.pptx','/api/jobs/invalid/report.json','/api/jobs/'+'a'*32+'/preview/other/1']:
            self.assertEqual(self.client.get(path).status_code,404)

if __name__=='__main__':unittest.main()
