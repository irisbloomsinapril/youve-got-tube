import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ygt_formats import selection, CODECS

class SelectorTests(unittest.TestCase):
    def test_each_branch_keeps_codec_and_height(self):
        for codec, pattern, container in [(CODECS[1], '^(avc1|h264)', 'mp4'), (CODECS[2], '^(av01|av1)', 'mp4'), (CODECS[3], '^(vp09|vp9)', 'webm')]:
            selector, ext=selection('1080p 이하',codec)
            self.assertEqual(ext,container)
            for branch in selector.split('/'):
                self.assertIn(pattern,branch)
                self.assertIn('[height<=1080]',branch)
    def test_audio_ignores_video_codec(self):
        self.assertEqual(selection('오디오만 (mp3)', CODECS[3]),('bestaudio/best','mp3'))
    def test_best_quality_has_no_height_limit(self):
        self.assertNotIn('height',selection('최고 화질',CODECS[1])[0])

@unittest.skipUnless(os.environ.get('YGT_TEST_ENGINE'),'Requires official yt-dlp executable')
class ActualEngineSelectionTests(unittest.TestCase):
    def fixture(self):
        formats=[]
        for name, codec, ext in [('h264','avc1.640028','mp4'),('av1','av01.0.08M.08','mp4'),('vp9','vp9','webm')]:
            for height in (720,1080,2160):
                formats.append({'format_id':f'{name}-{height}','vcodec':codec,'acodec':'none','height':height,'width':height*16//9,'fps':30,'tbr':height,'ext':ext,'url':f'https://example.invalid/{name}-{height}.{ext}'})
        for name,codec,ext in [('aac','mp4a.40.2','m4a'),('opus','opus','webm')]:
            formats.append({'format_id':'audio-'+name,'vcodec':'none','acodec':codec,'ext':ext,'abr':128,'url':f'https://example.invalid/{name}.{ext}'})
        return {'id':'codec-test','title':'Codec test','extractor':'generic','webpage_url':'https://example.invalid/test','formats':formats}
    def run_selector(self,fixture,codec):
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'info.json'
            file.write_text(json.dumps(fixture))
            return subprocess.run([os.environ['YGT_TEST_ENGINE'],'--ignore-config','--load-info-json',str(file),'--skip-download','--dump-single-json','--no-check-formats','-f',selection('1080p 이하',codec)[0]],capture_output=True,text=True,timeout=30)
    def test_actual_selection_for_all_codecs(self):
        for codec,expected,audio in [(CODECS[1],'h264-1080','audio-aac'),(CODECS[2],'av1-1080','audio-aac'),(CODECS[3],'vp9-1080','audio-opus')]:
            result=self.run_selector(self.fixture(),codec)
            self.assertEqual(result.returncode,0,result.stderr)
            info=json.loads(result.stdout)
            self.assertEqual([f['format_id'] for f in info['requested_formats']],[expected,audio])
    def test_absent_codec_fails_instead_of_falling_back(self):
        info=self.fixture()
        info['formats']=[f for f in info['formats'] if not f['format_id'].startswith('av1')]
        result=self.run_selector(info,CODECS[2])
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Requested format is not available',result.stderr)

if __name__=='__main__':unittest.main()
