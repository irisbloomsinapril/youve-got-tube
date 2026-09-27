import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import ygt_engine as e

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.folder=Path(self.tmp.name)
        self.location=patch.object(e,'engine_dir',return_value=self.folder)
        self.location.start()
        e._CHECKED=False
        self.target=self.folder/('yt-dlp.exe' if os.name=='nt' else 'yt-dlp')
    def tearDown(self):
        self.location.stop()
        self.tmp.cleanup()
    def test_offline_existing_preserved(self):
        self.target.write_text('existing')
        messages=[]
        with patch.object(e,'_read',side_effect=OSError('offline')):
            self.assertEqual(e.ensure_engine(messages.append),str(self.target))
        self.assertEqual(self.target.read_text(),'existing')
        self.assertIn('기존',messages[-1])
    def test_first_install_can_retry(self):
        with patch.object(e,'_read',side_effect=OSError('offline')):
            with self.assertRaisesRegex(RuntimeError,'최초 설치 실패'):
                e.ensure_engine()
        self.assertFalse(e._CHECKED)
    def test_new_session_checks_even_with_recent_stamp(self):
        self.target.write_text('existing')
        (self.folder/'last-check').touch()
        with patch.object(e,'_read',side_effect=OSError('offline')) as read:
            e.ensure_engine()
            self.assertEqual(read.call_count,1)
            e.ensure_engine()
            self.assertEqual(read.call_count,1)
            e.ensure_engine(force=True)
            self.assertEqual(read.call_count,2)
    def release(self):
        return json.dumps({'tag_name':'new','assets':[{'name':n,'browser_download_url':'https://github.com/yt-dlp/yt-dlp/releases/download/new/'+n} for n in ('yt-dlp_macos','SHA2-256SUMS')]}).encode()
    def test_checksum_failure_keeps_old_binary(self):
        self.target.write_text('existing')
        with patch.object(e,'_asset_name',return_value='yt-dlp_macos'),patch.object(e,'_read',side_effect=[self.release(),b'bad  yt-dlp_macos']),patch.object(e,'_run',return_value=subprocess.CompletedProcess([],0,'old','')),patch.object(e.urllib.request,'urlopen',return_value=io.BytesIO(b'corrupt')):
            e.ensure_engine()
        self.assertEqual(self.target.read_text(),'existing')
        self.assertEqual(list(self.folder.iterdir()),[self.target])
    def test_verified_update_replaces_binary(self):
        self.target.write_text('existing')
        payload=b'new executable'
        checksum=(hashlib.sha256(payload).hexdigest()+'  yt-dlp_macos').encode()
        with patch.object(e,'_asset_name',return_value='yt-dlp_macos'),patch.object(e,'_read',side_effect=[self.release(),checksum]),patch.object(e,'_run',side_effect=[subprocess.CompletedProcess([],0,'old',''),subprocess.CompletedProcess([],0,'new','')]),patch.object(e.urllib.request,'urlopen',return_value=io.BytesIO(payload)):
            e.ensure_engine()
        self.assertEqual(self.target.read_bytes(),payload)
        self.assertTrue((self.folder/'last-check').exists())
    def test_failed_execution_keeps_old_binary(self):
        self.target.write_text('existing')
        checksum=(hashlib.sha256(b'new').hexdigest()+'  yt-dlp_macos').encode()
        with patch.object(e,'_asset_name',return_value='yt-dlp_macos'),patch.object(e,'_read',side_effect=[self.release(),checksum]),patch.object(e,'_run',side_effect=[subprocess.CompletedProcess([],0,'old',''),subprocess.CompletedProcess([],1,'','bad binary')]),patch.object(e.urllib.request,'urlopen',return_value=io.BytesIO(b'new')):
            e.ensure_engine()
        self.assertEqual(self.target.read_text(),'existing')
    def test_options_preserve_paths_and_formats(self):
        with patch.object(e,'ensure_engine',return_value='/engine'),patch.object(e,'_runtime_args',return_value=[]):
            args=e.YoutubeDL({'format':'137+140','outtmpl':'/a b/%(title)s.%(ext)s','noplaylist':False,'writesubtitles':True,'writeautomaticsub':True,'subtitleslangs':['ko','en'],'writethumbnail':True,'postprocessors':[{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':'192'},{'key':'EmbedThumbnail'}]})._args()
        for token in ('--yes-playlist','137+140','/a b/%(title)s.%(ext)s','--write-subs','--write-auto-subs','ko,en','--write-thumbnail','--embed-thumbnail','192K'):
            self.assertIn(token,args)
    def test_progress_and_failure_reach_gui(self):
        p=MagicMock()
        p.stdout=io.StringIO('YGT_PROGRESS:{"status":"downloading","downloaded_bytes":100}\nERROR: HTTP Error 403\n')
        p.wait.return_value=1
        p.__enter__.return_value=p
        hooks=[]
        with patch.object(e.YoutubeDL,'_args',return_value=['/engine']),patch.object(e.subprocess,'Popen',return_value=p):
            with self.assertRaisesRegex(RuntimeError,'403'):
                e.YoutubeDL({'progress_hooks':[hooks.append]}).download(['https://example.org'])
        self.assertEqual(hooks[0]['downloaded_bytes'],100)
    def test_metadata_error_not_treated_as_success(self):
        with patch.object(e.YoutubeDL,'_args',return_value=['/engine']),patch.object(e,'_run',return_value=subprocess.CompletedProcess([],1,'','server error')):
            with self.assertRaisesRegex(RuntimeError,'server error'):
                e.YoutubeDL().extract_info('https://example.org')

if __name__=='__main__':unittest.main()
