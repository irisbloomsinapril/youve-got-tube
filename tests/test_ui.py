"""Run on a desktop with YGT_UI_TESTS=1; no network or downloads."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

@unittest.skipUnless(os.environ.get('YGT_UI_TESTS')=='1','Requires a desktop session')
class DesktopTests(unittest.TestCase):
    def test_layout_scroll_and_download_routing(self):
        import app
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'YGT_ENGINE_DIR':tmp}),patch.object(app.DownloaderApp,'_check_updates'):
            root=app.DownloaderApp()
            try:
                root.geometry('800x560')
                root.update()
                page=root.download_page
                self.assertEqual(page.body.winfo_width(),page.canvas.winfo_width())
                self.assertLess(root.download_btn.winfo_rooty()+root.download_btn.winfo_height(),root.winfo_rooty()+root.winfo_height())
                self.assertEqual(str(root.download_btn['state']),'disabled')
                # A small delta over a label scrolls the body.
                page.canvas.yview_moveto(0)
                event=SimpleNamespace(widget=root.mode_banner,delta=-1,num=None,state=0)
                root._route_wheel(event)
                self.assertGreater(page.canvas.yview()[0],0)
                # Header and navigation have no Canvas ancestor: fall back to active page.
                for widget in (root.update_btn, root.nav, root.notebook):
                    page.canvas.yview_moveto(0)
                    widget.event_generate('<MouseWheel>', delta=-120)
                    root.update()
                    self.assertGreater(page.canvas.yview()[0], 0, str(widget))
                # Tk 9 high-resolution event packs signed Y in the low 16 bits.
                if root.tk.call('package', 'vcompare', root.tk.call('info', 'patchlevel'), '9.0') >= 0:
                    for widget in (root.update_btn, root.url_text, page.canvas):
                        page.canvas.yview_moveto(0)
                        widget.event_generate('<TouchpadScroll>', delta=65506)  # Y = -30
                        root.update()
                        self.assertGreater(page.canvas.yview()[0], 0, str(widget))
                # Text scrolls first; at its boundary the body receives the wheel.
                root.url_text.insert('1.0','\n'.join('https://example.org/'+str(i) for i in range(40)))
                root.update()
                root.url_text.yview_moveto(0)
                before=page.canvas.yview()
                event.widget=root.url_text
                root._route_wheel(event)
                self.assertGreater(root.url_text.yview()[0],0)
                self.assertEqual(page.canvas.yview(),before)
                root.url_text.yview_moveto(1)
                root._route_wheel(event)
                self.assertGreater(page.canvas.yview()[0],before[0])
                # Actual Tk event traverses our bindtag once, not the default Text binding.
                root.url_text.yview_moveto(0)
                root.url_text.event_generate('<MouseWheel>',delta=-1)
                root.update()
                self.assertGreater(root.url_text.yview()[0],0)
                # Main tab ignores stale advanced selections.
                root.url_text.delete('1.0','end')
                root.url_text.insert('1.0','https://example.org/video')
                root.update()
                root.fetched_url='https://example.org/video'
                root.combo_tree.insert('','end',iid='combo_0',values=('1080p',))
                root.combo_tree.selection_set('combo_0')
                root.update()
                with patch.object(root,'_begin_batch_download') as batch:
                    root._start_download()
                    batch.assert_called_once_with(['https://example.org/video'])
                root.notebook.select(root.detail_page)
                root.update()
                with patch.object(root,'_begin_precise_download') as precise:
                    root._start_download()
                    precise.assert_called_once_with('https://example.org/video','combo_0',is_combo=True)
                # Raw and recommended selections cannot both be active.
                root._toggle_advanced()
                root.tree.insert('','end',iid='140',values=('140',))
                root.tree.selection_set('140')
                root.update()
                self.assertFalse(root.combo_tree.selection())
                with patch.object(root,'_begin_precise_download') as precise:
                    root._start_download()
                    precise.assert_called_once_with('https://example.org/video',['140'],is_combo=False)
                root.engine_busy=True
                root._refresh_controls()
                self.assertEqual(str(root.download_btn['state']),'disabled')
                self.assertEqual(str(root.update_btn['state']),'disabled')
                root.engine_busy=False
                root.preset_var.set('720p 이하')
                root.codec_var.set('AV1 · 고효율')
                root._save_preferences()
                self.assertIn('720p',root._preferences_path().read_text())
                self.assertIn('AV1',root._preferences_path().read_text())
            finally:
                for timer in root.tk.call('after','info'):
                    root.after_cancel(timer)
                root.destroy()

if __name__=='__main__':unittest.main()
