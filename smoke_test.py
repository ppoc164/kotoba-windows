"""Exercise real Qt playback with a temporary silent WAV, without a model download."""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
import tempfile
import wave
from pathlib import Path
from app import QApplication, Window, QUrl, QMediaPlayer
from PySide6.QtTest import QTest

app = QApplication([])
window = Window()
window.output.setVolume(0)
with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
    path = Path(folder) / 'test.wav'
    with wave.open(str(path), 'wb') as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b'\0\0' * 48000)
    window.player.setSource(QUrl.fromLocalFile(str(path)))
    QTest.qWait(500)
    window.show_rows([dict(start=.2, end=.8, text='first'), dict(start=1, end=1.6, text='second')])
    window.play_row(0)
    QTest.qWait(1400)
    assert window.player.playbackState() == QMediaPlayer.PausedState
    assert 790 <= window.player.position() < 1050, window.player.position()
    window.loop.setChecked(True)
    window.play_row(1)
    QTest.qWait(1500)
    assert window.player.playbackState() == QMediaPlayer.PlayingState
    assert 1000 <= window.player.position() <= 1700
    window.player.stop()
    window.player.setSource(QUrl())
    QTest.qWait(200)
window.close()
print('PASS: sentence boundary stop, seek and loop with real Qt audio playback')
