import json
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
import unittest
import wave
from pathlib import Path
from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest
from app import QApplication, Window, QMediaPlayer
from library import Library

APP = QApplication.instance() or QApplication([])


class Features(unittest.TestCase):
    def test_full_preview_search_and_location(self):
        from transcript_preview import TranscriptPreview
        from PySide6.QtCore import QUrl
        preview = TranscriptPreview(self.rows, 'Test', self.w)
        preview.locate.connect(self.w.locate_sentence)
        self.assertIn('secret first sentence', preview.browser.toPlainText())
        preview.search.setText('secret')
        self.assertEqual(preview.browser.textCursor().selectedText(), 'secret')
        first = preview.browser.textCursor().position()
        preview.find_match()
        self.assertGreater(preview.browser.textCursor().position(), first)
        preview.find_match()
        self.assertEqual(preview.browser.textCursor().position(), first)
        preview.search.setText('missing')
        self.assertIn('没有匹配', preview.result.text())
        self.w.search.setText('first')
        preview.open_sentence(QUrl('sentence:1'))
        self.assertFalse(self.w.list.item(1).isHidden())
        self.assertEqual(self.w.active, 1)
        self.assertEqual(self.w.player.position(), 700)
        self.assertNotIn('secret', self.w.cards[1].answer.text())
        self.assertNotEqual(self.w.player.playbackState(), QMediaPlayer.PlayingState)
        preview.play.setChecked(True)
        preview.open_sentence(QUrl('sentence:0'))
        self.assertEqual(self.w.player.playbackState(), QMediaPlayer.PlayingState)
        preview.close()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root = Path(self.temp.name)
        self.audio = self.root / 'lesson.wav'
        with wave.open(str(self.audio), 'wb') as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(16000)
            out.writeframes(b'\0\0' * 64000)
        self.rows = [dict(start=.1, end=.6, text='secret first sentence'), dict(start=.7, end=3, text='secret second sentence')]
        self.w = Window(self.root / 'history')
        self.w.output.setVolume(0)
        self.w.show()
        self.w.load_audio(str(self.audio))
        QTest.qWait(300)
        self.w.completed(self.rows)

    def tearDown(self):
        self.w.close()
        self.w.player.setSource('')
        self.w.deleteLater()
        QTest.qWait(100)
        self.temp.cleanup()

    def test_continuous_mask_and_reveal(self):
        self.w.mode.setCurrentIndex(1)
        self.w.cards[0].play.click()
        QTest.qWait(1650)
        self.assertEqual(self.w.player.playbackState(), QMediaPlayer.PlayingState)
        self.assertGreater(self.w.player.position(), 650)
        self.assertEqual(self.w.active, 1)
        self.assertNotIn('secret', self.w.now.text())
        self.assertNotIn('secret', self.w.cards[1].answer.text())
        self.w.cards[1].reveal.click()
        self.assertEqual(self.w.cards[1].answer.text(), self.rows[1]['text'])
        self.w.cards[1].reveal.click()
        self.assertNotIn('secret', self.w.cards[1].answer.text())

    def test_slider_click_drag_and_pause(self):
        slider = self.w.slider
        QTest.mouseClick(slider, Qt.LeftButton, pos=QPoint(slider.width() // 2, 10))
        QTest.qWait(100)
        self.assertTrue(1700 < self.w.player.position() < 2300)
        self.assertNotEqual(self.w.player.playbackState(), QMediaPlayer.PlayingState)
        self.w.play_row(0)
        QTest.qWait(100)
        QTest.mousePress(slider, Qt.LeftButton, pos=QPoint(20, 10))
        QTest.mouseMove(slider, QPoint(slider.width() * 3 // 4, 10))
        QTest.mouseRelease(slider, Qt.LeftButton, pos=QPoint(slider.width() * 3 // 4, 10))
        self.assertTrue(2700 < self.w.player.position() < 3500, self.w.player.position())
        QTest.qWait(700)
        self.assertGreater(self.w.player.position(), 2700)
        self.assertEqual(self.w.mode.currentIndex(), 1)
        self.assertEqual(self.w.player.playbackState(), QMediaPlayer.PlayingState)

    def test_history_restart_and_missing_audio(self):
        self.w.seek(1500)
        self.w.save_current()
        record = Library(self.root / 'history').entries()[0]
        self.assertEqual(len(record['sentences']), 2)
        self.assertEqual(record['position'], 1500)
        other = Window(self.root / 'history')
        try:
            other.open_history(other.history.item(0))
            QTest.qWait(300)
            self.assertEqual(other.rows, self.rows)
            self.assertEqual(other.player.position(), 1500)
            self.assertNotIn('secret', other.cards[0].answer.text())
            missing = dict(record, path=str(self.root / 'missing.wav'))
            other.load_audio(missing['path'], missing)
            self.assertEqual(other.rows, self.rows)
            self.assertFalse(other.play_btn.isEnabled())
            self.assertTrue(other.export_btn.isEnabled())
        finally:
            other.close()
            other.player.setSource('')
            other.deleteLater()
            QTest.qWait(100)

    def test_legacy_import_and_changed_audio(self):
        stat = self.audio.stat()
        sidecar = Path(str(self.audio) + '.kotoba.json')
        sidecar.write_text(json.dumps(dict(size=stat.st_size, mtime=stat.st_mtime_ns, sentences=self.rows)), encoding='utf-8')
        library = Library(self.root / 'legacy')
        library.import_sidecar(sidecar)
        self.assertEqual(library.entries()[0]['sentences'], self.rows)
        self.audio.touch()
        self.assertFalse(library.matches(library.entries()[0], self.audio))

    def test_favorite_categories_and_rename_survive_progress_save(self):
        path = str(self.audio)
        group = self.w.library.set_category('日语听力')
        self.w.refresh_categories()
        self.w.apply_metadata(path, title='第七课', favorite=True, category=group)
        self.assertEqual(self.w.file_label.text(), '第七课')
        self.w.category_filter.setCurrentIndex(self.w.category_filter.findData(group))
        self.assertFalse(self.w.history.item(0).isHidden())
        self.w.history_search.setText('第七课')
        self.assertFalse(self.w.history.item(0).isHidden())
        stale = dict(self.w.record)
        self.w.library.set_category('每日练习', group)
        self.w.library.delete_category(group)
        self.w.library.save(path, self.rows, 1200, stale)
        library = Library(self.root / 'history')
        record = library.find(path)
        self.assertEqual(record['title'], '第七课')
        self.assertTrue(record['favorite'])
        self.assertIsNone(record['category'])
        self.assertEqual(record['position'], 1200)
        self.assertTrue(self.audio.exists())
        self.assertEqual(record['sentences'], self.rows)
        self.w.apply_metadata(path, favorite=False, category=None)
        self.w.refresh_categories('favorites')
        self.w.filter_history('')
        self.assertTrue(self.w.history.item(0).isHidden())


if __name__ == '__main__':
    unittest.main()
