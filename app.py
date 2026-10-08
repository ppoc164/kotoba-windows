import json
import os
import sys
from pathlib import Path

os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
os.environ.setdefault('HF_HUB_DISABLE_SYMLINKS_WARNING', '1')

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QFileDialog, QMessageBox, QProgressBar, QListWidget,
    QListWidgetItem, QCheckBox, QSlider, QLineEdit)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from sentences import split_sentences, timestamp, to_srt


class Transcriber(QThread):
    status = Signal(str)
    progress = Signal(int)
    result = Signal(list)
    failed = Signal(str)

    def __init__(self, audio, model, language, parent=None):
        super().__init__(parent)
        self.audio, self.model, self.language = audio, model, language

    def run(self):
        stage = '加载模型'
        try:
            from faster_whisper import WhisperModel
            cache = str(Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Kotoba' / 'models')
            self.status.emit('正在加载模型；首次使用会下载模型，请保持联网…')
            # Cached models never need a network connection.
            try:
                model = WhisperModel(self.model, device='cpu', compute_type='int8', download_root=cache, local_files_only=True)
            except Exception:
                model = WhisperModel(self.model, device='cpu', compute_type='int8', download_root=cache)
            if self.isInterruptionRequested():
                return
            self.status.emit('正在本机识别音频…')
            stage = '解码和识别音频'
            segments, info = model.transcribe(self.audio, language=self.language, word_timestamps=True, vad_filter=True)
            data = []
            for s in segments:
                if self.isInterruptionRequested():
                    return
                data.append(dict(start=s.start, end=s.end, text=s.text,
                    words=[dict(start=w.start, end=w.end, text=w.word) for w in (s.words or [])]))
                self.progress.emit(min(99, round(s.end / max(info.duration, 1) * 100)))
            self.result.emit(split_sentences(data))
        except Exception as exc:
            self.failed.emit(f'{stage}失败：{exc}')


from ui import Window as BaseWindow, STYLE


class Window(BaseWindow):
    def __init__(self, history_root=None):
        super().__init__(Transcriber, history_root)


if __name__ == '__main__':
    if sys.platform == 'win32':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Kotoba.Desktop')
    app = QApplication(sys.argv)
    from PySide6.QtGui import QIcon
    icon_path = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'assets' / 'kotoba.ico'
    app.setWindowIcon(QIcon(str(icon_path)))
    app.setFont(QFont('Microsoft YaHei UI', 10))
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    if '--smoke-test' in sys.argv:
        assert not app.windowIcon().isNull(), 'Application icon was not loaded'
        from faster_whisper import WhisperModel
        from decoder_check import check_decoding
        check_decoding()
        window.show_rows([dict(start=0, end=1, text='启动验证')])
        from transcript_preview import TranscriptPreview
        preview = TranscriptPreview(window.rows, '启动验证', window)
        assert '启动验证' in preview.browser.toPlainText()
        preview.close()
        app.processEvents()
        Path(sys.argv[sys.argv.index('--smoke-test') + 1]).write_text('OK: Qt UI, multimedia, inference imports, WAV and MP4 audio decoding', encoding='utf-8')
        QTimer.singleShot(100, app.quit)
    sys.exit(app.exec())
