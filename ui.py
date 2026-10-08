import json
from pathlib import Path
from bisect import bisect_right

from PySide6.QtCore import Qt, QUrl, QTimer, Signal, QSize
from PySide6.QtGui import QPainter, QPen, QColor
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QFileDialog, QMessageBox, QProgressBar, QListWidget,
    QListWidgetItem, QCheckBox, QSlider, QLineEdit, QFrame, QSizePolicy, QStyle, QInputDialog, QMenu)
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from sentences import timestamp, to_srt
from library import Library
from transcript_preview import TranscriptPreview


class StyledComboBox(QComboBox):
    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#528575' if self.isEnabled() else '#b3c3bd'), 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x, y = self.width() - 18, self.height() // 2
        painter.drawLine(x - 4, y - 2, x, y + 2)
        painter.drawLine(x, y + 2, x + 4, y - 2)
        painter.end()


class SeekSlider(QSlider):
    """Click anywhere or drag; the player seeks only on release."""
    def __init__(self):
        super().__init__(Qt.Horizontal)
        self.setRange(0, 0)

    def point_value(self, event):
        ratio = min(1, max(0, (event.position().x() - 8) / max(1, self.width() - 16)))
        return round(self.minimum() + ratio * (self.maximum() - self.minimum()))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self.setSliderDown(True)
            self.setValue(self.point_value(event))
            self.sliderMoved.emit(self.value())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.isSliderDown():
            self.setValue(self.point_value(event))
            self.sliderMoved.emit(self.value())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.isSliderDown():
            self.setValue(self.point_value(event))
            self.setSliderDown(False)
        else:
            super().mouseReleaseEvent(event)


class RevealLabel(QLabel):
    clicked = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()


class SentenceCard(QFrame):
    def __init__(self, index, row, play, reveal):
        super().__init__()
        self.setObjectName('sentence')
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        self.play = QPushButton()
        self.play.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play.setFixedSize(42, 42)
        self.play.setToolTip('播放这句，不显示文本')
        self.play.clicked.connect(lambda: play(index))
        layout.addWidget(self.play)
        text = QVBoxLayout()
        meta = QLabel(f"{index + 1:02d}    {timestamp(row['start'])} — {timestamp(row['end'])}")
        meta.setObjectName('muted')
        text.addWidget(meta)
        self.answer = RevealLabel()
        self.answer.setWordWrap(True)
        self.answer.setTextFormat(Qt.PlainText)
        self.answer.setCursor(Qt.PointingHandCursor)
        self.answer.clicked.connect(lambda: reveal(index))
        self.answer.setMinimumHeight(30)
        text.addWidget(self.answer)
        layout.addLayout(text, 1)
        self.reveal = QPushButton('显示文本')
        self.reveal.clicked.connect(lambda: reveal(index))
        layout.addWidget(self.reveal)

    def display(self, text, hidden):
        self.answer.setText('●  ●  ●    先听一遍，点击这里揭晓文本' if hidden else text)
        self.answer.setObjectName('masked' if hidden else 'answer')
        self.reveal.setText('显示文本' if hidden else '遮挡文本')
        self.answer.style().unpolish(self.answer)
        self.answer.style().polish(self.answer)


class Window(QMainWindow):
    def __init__(self, worker_class=None, history_root=None):
        super().__init__()
        self.worker_class = worker_class
        self.library = Library(history_root)
        self.audio_path = None
        self.record = None
        self.rows, self.cards, self.starts = [], [], []
        self.revealed = set()
        self.active = -1
        self.clip = None
        self.worker = None
        self.pending_position = None
        self.scrubbing = False
        self.resume_after_seek = False
        self.setWindowTitle('Kotoba · 逐句听')
        self.resize(1240, 850)
        self.setMinimumSize(1000, 720)
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.output.setVolume(.85)
        self.player.setAudioOutput(self.output)
        root = QWidget()
        self.setCentralWidget(root)
        shell = QHBoxLayout(root)
        shell.setContentsMargins(0, 0, 0, 0)
        shell.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(252)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(20, 30, 20, 24)
        side.setSpacing(16)
        logo = QLabel('kotoba  /  言葉')
        logo.setObjectName('logo')
        side.addWidget(logo)
        side.addWidget(QLabel('让每一句，都听得懂。'))
        self.import_btn = QPushButton('＋  导入音频')
        self.import_btn.setObjectName('primary')
        self.import_btn.clicked.connect(self.import_audio)
        side.addWidget(self.import_btn)
        side.addSpacing(12)
        side.addWidget(QLabel('我的音频  /  转写历史'))
        folders = QHBoxLayout()
        self.category_filter = StyledComboBox()
        self.category_filter.setMinimumWidth(135)
        self.category_filter.currentIndexChanged.connect(lambda: self.filter_history(self.history_search.text()))
        folders.addWidget(self.category_filter, 1)
        self.manage_btn = QPushButton('分类')
        self.manage_btn.setToolTip('新建、重命名或删除收藏分类')
        self.manage_btn.clicked.connect(self.manage_categories)
        folders.addWidget(self.manage_btn)
        side.addLayout(folders)
        self.history_search = QLineEdit()
        self.history_search.setPlaceholderText('搜索历史音频')
        self.history_search.textChanged.connect(self.filter_history)
        side.addWidget(self.history_search)
        self.history = QListWidget()
        self.history.setObjectName('history')
        self.history.setWordWrap(True)
        self.history.itemClicked.connect(self.open_history)
        self.history.setContextMenuPolicy(Qt.CustomContextMenu)
        self.history.customContextMenuRequested.connect(self.history_menu)
        side.addWidget(self.history, 1)
        self.old_btn = QPushButton('导入旧版转写记录')
        self.old_btn.clicked.connect(self.import_old)
        side.addWidget(self.old_btn)
        privacy = QLabel('本地识别 · 音频不上传\n历史和模型保存在这台电脑')
        privacy.setObjectName('muted')
        side.addWidget(privacy)
        shell.addWidget(sidebar)
        main = QVBoxLayout()
        main.setContentsMargins(28, 26, 28, 22)
        main.setSpacing(12)
        shell.addLayout(main, 1)
        eyebrow = QLabel('LISTEN  /  REVEAL  /  REPEAT')
        eyebrow.setObjectName('eyebrow')
        main.addWidget(eyebrow)
        title = QLabel('先听声音，再看答案。')
        title.setObjectName('title')
        main.addWidget(title)
        self.file_label = QLabel('导入音频，开始你的听力练习')
        self.file_label.setTextFormat(Qt.PlainText)
        self.file_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.file_label.setMinimumHeight(26)
        name_bar = QHBoxLayout()
        name_bar.addWidget(self.file_label, 1)
        self.rename_btn = QPushButton('重命名')
        self.rename_btn.setEnabled(False)
        self.rename_btn.clicked.connect(lambda: self.rename_audio(self.audio_path))
        name_bar.addWidget(self.rename_btn)
        self.favorite_btn = QPushButton('收藏')
        self.favorite_btn.setEnabled(False)
        self.favorite_btn.clicked.connect(lambda: self.favorite_menu(self.audio_path, self.favorite_btn.mapToGlobal(self.favorite_btn.rect().bottomLeft())))
        name_bar.addWidget(self.favorite_btn)
        main.addLayout(name_bar)
        options = QHBoxLayout()
        self.language = StyledComboBox()
        for text, code in [('自动检测语言', None), ('中文', 'zh'), ('日语', 'ja'), ('英语', 'en'), ('韩语', 'ko')]:
            self.language.addItem(text, code)
        self.model = StyledComboBox()
        for text, code in [('轻量 · base', 'base'), ('更准确 · small', 'small'), ('快速试用 · tiny', 'tiny')]:
            self.model.addItem(text, code)
        self.transcribe_btn = QPushButton('开始本地转写')
        self.transcribe_btn.setObjectName('primary')
        self.transcribe_btn.setEnabled(False)
        self.transcribe_btn.clicked.connect(self.transcribe)
        self.cancel_btn = QPushButton('取消')
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.cancel)
        for widget in [self.language, self.model, self.transcribe_btn, self.cancel_btn]:
            options.addWidget(widget)
        options.addStretch()
        main.addLayout(options)
        self.status = QLabel('选择音频后，转写结果会自动加入左侧历史。')
        self.status.setObjectName('muted')
        self.status.setWordWrap(True)
        main.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setFixedHeight(4)
        self.progress.setTextVisible(False)
        main.addWidget(self.progress)
        bar = QHBoxLayout()
        self.count = QLabel('听力片段  /  0 句')
        bar.addWidget(self.count)
        bar.addStretch()
        self.hide_text = QCheckBox('遮挡文本')
        self.hide_text.setChecked(True)
        self.hide_text.toggled.connect(self.reset_reveal)
        bar.addWidget(self.hide_text)
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索句子')
        self.search.setMaximumWidth(180)
        self.search.textChanged.connect(self.filter_rows)
        bar.addWidget(self.search)
        self.preview_btn = QPushButton('全文预览')
        self.preview_btn.setEnabled(False)
        self.preview_btn.clicked.connect(self.open_preview)
        bar.addWidget(self.preview_btn)
        self.export_btn = QPushButton('导出')
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self.export)
        bar.addWidget(self.export_btn)
        main.addLayout(bar)
        self.list = QListWidget()
        self.list.setSpacing(5)
        self.list.setResizeMode(QListWidget.Adjust)
        main.addWidget(self.list, 1)
        player_box = QFrame()
        player_box.setObjectName('playerBox')
        panel = QVBoxLayout(player_box)
        panel.setContentsMargins(18, 16, 18, 16)
        panel.setSpacing(12)
        player_head = QHBoxLayout()
        self.now = QLabel('准备好，听见新的进步。')
        self.now.setObjectName('playingTitle')
        player_head.addWidget(self.now, 1)
        self.time = QLabel('00:00:00 / 00:00:00')
        player_head.addWidget(self.time)
        panel.addLayout(player_head)
        self.slider = SeekSlider()
        self.slider.sliderPressed.connect(self.begin_seek)
        self.slider.sliderMoved.connect(self.preview_seek)
        self.slider.sliderReleased.connect(self.end_seek)
        self.slider.actionTriggered.connect(self.keyboard_seek)
        panel.addWidget(self.slider)
        controls = QHBoxLayout()
        self.previous = QPushButton('上一句')
        self.previous.clicked.connect(lambda: self.play_row(max(0, self.active - 1)))
        self.play_btn = QPushButton('播放')
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_btn.setObjectName('primary')
        self.play_btn.clicked.connect(self.toggle)
        self.following = QPushButton('下一句')
        self.following.clicked.connect(lambda: self.play_row(self.active + 1))
        self.mode = StyledComboBox()
        self.mode.addItems(['单句播放', '连续播放整段'])
        self.mode.currentIndexChanged.connect(self.change_mode)
        self.loop = QCheckBox('单句循环')
        self.loop.toggled.connect(self.change_loop)
        self.speed = StyledComboBox()
        self.speed.addItems(['0.5×', '0.75×', '1.0×', '1.25×', '1.5×', '2.0×'])
        self.speed.setCurrentIndex(2)
        self.speed.currentIndexChanged.connect(lambda i: self.player.setPlaybackRate([.5, .75, 1, 1.25, 1.5, 2][i]))
        for widget in [self.previous, self.play_btn, self.following, self.mode, self.loop, self.speed]:
            controls.addWidget(widget)
        panel.addLayout(controls)
        main.addWidget(player_box)
        self.player.durationChanged.connect(self.duration_changed)
        self.player.mediaStatusChanged.connect(self.media_ready)
        self.player.seekableChanged.connect(lambda ok: self.slider.setEnabled(ok))
        self.player.playbackStateChanged.connect(self.update_play_button)
        self.player.errorOccurred.connect(lambda *_: self.status.setText('无法播放：' + self.player.errorString()))
        self.timer = QTimer(self)
        self.timer.setInterval(20)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self.refresh_categories()
        self.refresh_history()
        self.show_rows([])
        self.set_playable(False)

    def set_playable(self, playable):
        for widget in [self.play_btn, self.previous, self.following, self.mode, self.loop]:
            widget.setEnabled(playable)
        self.slider.setEnabled(playable and self.player.isSeekable())

    def update_play_button(self, state):
        playing = state == QMediaPlayer.PlayingState
        self.play_btn.setText('暂停' if playing else '播放')
        self.play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause if playing else QStyle.SP_MediaPlay))

    def refresh_history(self):
        self.history.clear()
        for record in self.library.entries():
            title = record.get('title') or Path(record['path']).name
            category = self.library.categories().get(record.get('category'), '未分类')
            note = f"收藏 · {category}" if record.get('favorite') else record.get('updated', '')[:10]
            item = QListWidgetItem(f"{title}\n{len(record['sentences'])} 句 · {note}")
            item.setData(Qt.UserRole, record)
            item.setToolTip(record['path'])
            self.history.addItem(item)
        self.filter_history(self.history_search.text())
        self.update_metadata_ui()

    def filter_history(self, text):
        for i in range(self.history.count()):
            item = self.history.item(i)
            record = item.data(Qt.UserRole)
            group = self.category_filter.currentData()
            matches = group in (None, 'all') or (record.get('favorite') and (
                group == 'favorites' or (group == 'uncategorized' and not record.get('category')) or record.get('category') == group))
            item.setHidden(not matches or text.casefold() not in item.text().casefold())

    def refresh_categories(self, selected=None):
        selected = selected or self.category_filter.currentData()
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        for label, key in [('全部音频', 'all'), ('全部收藏', 'favorites'), ('未分类收藏', 'uncategorized')]:
            self.category_filter.addItem(label, key)
        for key, label in self.library.categories().items():
            self.category_filter.addItem(label, key)
        self.category_filter.setCurrentIndex(max(0, self.category_filter.findData(selected)))
        self.category_filter.blockSignals(False)

    def update_metadata_ui(self):
        record = self.library.find(self.audio_path) if self.audio_path else None
        self.rename_btn.setEnabled(record is not None)
        self.favorite_btn.setEnabled(record is not None)
        if self.audio_path:
            self.file_label.setText((record or {}).get('title') or Path(self.audio_path).name)
        self.favorite_btn.setText('已收藏 · 管理' if record and record.get('favorite') else '收藏')

    def apply_metadata(self, path, **fields):
        try:
            record = self.library.edit(path, **fields)
            if self.audio_path and self.library.key(path) == self.library.key(self.audio_path):
                self.record = record
            self.refresh_history()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, '无法保存', str(exc))

    def rename_audio(self, path):
        record = self.library.find(path) if path else None
        if not record:
            return
        name, ok = QInputDialog.getText(self, '重命名音频', '应用内名称（不修改原文件）：', text=record.get('title') or Path(path).name)
        if ok:
            name = name.strip()
            if not name or len(name) > 160:
                QMessageBox.information(self, '名称无效', '请输入 1–160 个字符。')
                return
            self.apply_metadata(path, title=name)

    def favorite_menu(self, path, position):
        record = self.library.find(path) if path else None
        if not record:
            return
        menu = QMenu(self)
        menu.addAction('收藏到「未分类」', lambda: self.apply_metadata(path, favorite=True, category=None))
        for key, name in self.library.categories().items():
            action = menu.addAction('收藏到「' + name + '」', lambda k=key: self.apply_metadata(path, favorite=True, category=k))
            action.setCheckable(True)
            action.setChecked(bool(record.get('favorite') and record.get('category') == key))
        menu.addSeparator()
        menu.addAction('新建分类并收藏…', lambda: self.create_category(path))
        if record.get('favorite'):
            menu.addAction('取消收藏', lambda: self.apply_metadata(path, favorite=False, category=None))
        menu.exec(position)

    def create_category(self, path=None):
        name, ok = QInputDialog.getText(self, '新建收藏分类', '分类名称：')
        if not ok:
            return
        try:
            key = self.library.set_category(name)
            self.refresh_categories()
            if path:
                self.apply_metadata(path, favorite=True, category=key)
            self.refresh_history()
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, '无法创建分类', str(exc))

    def manage_categories(self):
        menu = QMenu(self)
        menu.addAction('新建分类…', self.create_category)
        key = self.category_filter.currentData()
        if key in self.library.categories():
            menu.addAction('重命名当前分类…', lambda: self.rename_category(key))
            menu.addAction('删除分类（收藏移至未分类）', lambda: self.remove_category(key))
        menu.exec(self.manage_btn.mapToGlobal(self.manage_btn.rect().bottomLeft()))

    def rename_category(self, key):
        name, ok = QInputDialog.getText(self, '重命名分类', '分类名称：', text=self.library.categories()[key])
        if ok:
            try:
                self.library.set_category(name, key)
                self.refresh_categories(key)
                self.refresh_history()
            except (OSError, ValueError) as exc:
                QMessageBox.warning(self, '无法保存分类', str(exc))

    def remove_category(self, key):
        try:
            self.library.delete_category(key)
            self.refresh_categories('uncategorized')
            self.refresh_history()
        except OSError as exc:
            QMessageBox.warning(self, '无法删除分类', str(exc))

    def history_menu(self, position):
        item = self.history.itemAt(position)
        if not item:
            return
        path = item.data(Qt.UserRole)['path']
        menu = QMenu(self)
        menu.addAction('重命名…', lambda: self.rename_audio(path))
        menu.addAction('收藏 / 移动分类…', lambda: self.favorite_menu(path, self.history.viewport().mapToGlobal(position)))
        menu.exec(self.history.viewport().mapToGlobal(position))

    def save_current(self):
        if self.audio_path and self.rows:
            try:
                self.record = self.library.save(self.audio_path, self.rows, self.player.position(), self.record)
            except OSError as exc:
                self.status.setText('历史保存失败：' + str(exc))

    def import_audio(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择音频', '', '音频 (*.mp3 *.wav *.m4a *.flac *.ogg *.aac *.wma *.mp4);;所有文件 (*)')
        if path:
            self.load_audio(path)

    def load_audio(self, path, record=None):
        if self.worker and self.worker.isRunning():
            return
        self.save_current()
        self.player.stop()
        self.pending_position = None
        self.audio_path = str(Path(path).resolve())
        self.record = record or self.library.find(path)
        self.search.clear()
        self.file_label.setText(Path(path).name)
        self.file_label.setToolTip(path)
        exists = Path(path).is_file()
        if exists and self.record and not self.library.matches(self.record, path):
            self.record = None
        if exists and not self.record and Path(path + '.kotoba.json').exists():
            try:
                self.record = self.library.import_sidecar(path + '.kotoba.json')
            except (OSError, ValueError, KeyError, TypeError):
                pass
        self.show_rows(self.record['sentences'] if self.record else [])
        self.pending_position = self.record.get('position', 0) if self.record else 0
        self.player.setSource(QUrl.fromLocalFile(path) if exists else QUrl())
        self.transcribe_btn.setEnabled(exists)
        self.set_playable(exists)
        self.status.setText('已恢复转写记录，点击 ▶ 听音频，点击遮挡处查看文本。' if self.rows else '选择语言和模型，开始本地转写。')
        if not exists:
            self.status.setText('原音频已移动或删除：仍可查看和导出文本。重新导入原音频可恢复播放。')
        self.progress.setValue(100 if self.rows else 0)
        self.refresh_history()

    def open_history(self, item):
        record = item.data(Qt.UserRole)
        self.load_audio(record['path'], record)

    def import_old(self):
        files, _ = QFileDialog.getOpenFileNames(self, '选择旧版音频旁的 .kotoba.json 文件', '', '旧版转写记录 (*.kotoba.json)')
        success = 0
        for file in files:
            try:
                self.library.import_sidecar(file)
                success += 1
            except (OSError, ValueError, KeyError, TypeError):
                pass
        if files:
            self.refresh_history()
            self.status.setText(f'已导入 {success} 条历史；{len(files) - success} 条无法导入（原音频缺失、已改变或记录无效）。')

    def duration_changed(self, duration):
        self.slider.setRange(0, duration)

    def media_ready(self, status):
        if status == QMediaPlayer.LoadedMedia and self.pending_position is not None:
            position, self.pending_position = self.pending_position, None
            QTimer.singleShot(0, lambda: self.player.setPosition(min(position, self.player.duration())))

    def transcribe(self):
        if not self.audio_path or (self.worker and self.worker.isRunning()):
            return
        self.player.pause()
        self.progress.setRange(0, 0)
        for widget in [self.import_btn, self.old_btn, self.history, self.transcribe_btn]:
            widget.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.worker = self.worker_class(self.audio_path, self.model.currentData(), self.language.currentData(), self)
        self.worker.status.connect(self.status.setText)
        self.worker.progress.connect(self.update_progress)
        self.worker.result.connect(self.completed)
        self.worker.failed.connect(self.failed)
        self.worker.finished.connect(self.finished)
        self.worker.start()

    def update_progress(self, n):
        self.progress.setRange(0, 100)
        self.progress.setValue(n)

    def cancel(self):
        if self.worker:
            self.worker.requestInterruption()
            self.cancel_btn.setEnabled(False)
            self.status.setText('正在取消，当前下载或识别步骤结束后停止…')

    def finished(self):
        for widget in [self.import_btn, self.old_btn, self.history, self.transcribe_btn]:
            widget.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setRange(0, 100)
        if self.worker.isInterruptionRequested():
            self.status.setText('已取消。')

    def failed(self, message):
        self.status.setText('转写未完成。')
        QMessageBox.warning(self, '无法完成转写', message)

    def completed(self, rows):
        self.show_rows(rows)
        self.update_progress(100)
        self.status.setText(f'转写完成 · {len(rows)} 句 · 先听后看，开始练习。' if rows else '没有检测到语音，请检查音频或手动选择语言后重试。')
        self.save_current()
        self.refresh_history()

    def show_rows(self, rows):
        self.player.pause()
        self.rows, self.active, self.clip = rows, -1, None
        self.starts = [r['start'] for r in rows]
        self.revealed.clear()
        self.cards = []
        self.list.clear()
        for i, row in enumerate(rows):
            item = QListWidgetItem()
            card = SentenceCard(i, row, self.play_row, self.reveal_row)
            card.display(row['text'], self.hide_text.isChecked())
            item.setSizeHint(QSize(0, 105))
            self.list.addItem(item)
            self.list.setItemWidget(item, card)
            self.cards.append(card)
        if not rows:
            self.list.addItem('还没有听力片段\n\n导入一段音频，或从左侧打开历史记录。')
        self.count.setText(f'听力片段  /  {len(rows)} 句')
        self.export_btn.setEnabled(bool(rows))
        self.preview_btn.setEnabled(bool(rows))
        self.now.setText('点击 ▶ 播放一句，点击遮挡处揭晓文本')
        self.filter_rows(self.search.text())
        QTimer.singleShot(0, self.resize_cards)

    def resize_cards(self):
        for i, card in enumerate(self.cards):
            card.setFixedWidth(max(100, self.list.viewport().width() - 16))
            self.list.item(i).setSizeHint(QSize(0, max(96, card.sizeHint().height())))

    def open_preview(self):
        if self.rows:
            dialog = TranscriptPreview(self.rows, self.file_label.text(), self)
            dialog.locate.connect(self.locate_sentence)
            dialog.exec()

    def locate_sentence(self, index, play=False):
        if not 0 <= index < len(self.rows):
            return
        self.search.clear()
        self.player.pause()
        self.highlight(index)
        self.list.scrollToItem(self.list.item(index), QListWidget.PositionAtCenter)
        if not self.player.source().isEmpty():
            self.clip = index if self.mode.currentIndex() == 0 else None
            self.player.setPosition(round(self.rows[index]['start'] * 1000))
            if play:
                self.play_row(index)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'cards'):
            QTimer.singleShot(0, self.resize_cards)

    def reveal_row(self, index):
        if index in self.revealed:
            self.revealed.remove(index)
        else:
            self.revealed.add(index)
        self.update_card(index)

    def update_card(self, index):
        hidden = self.hide_text.isChecked() != (index in self.revealed)
        self.cards[index].display(self.rows[index]['text'], hidden)
        self.resize_cards()

    def reset_reveal(self):
        self.revealed.clear()
        for i in range(len(self.cards)):
            self.cards[i].display(self.rows[i]['text'], self.hide_text.isChecked())
        self.resize_cards()

    def filter_rows(self, text):
        for i, row in enumerate(self.rows):
            self.list.item(i).setHidden(text.casefold() not in row['text'].casefold())

    def highlight(self, index):
        if index == self.active:
            return
        previous = self.active
        self.active = index
        for i in (previous, index):
            if 0 <= i < len(self.cards):
                card = self.cards[i]
                card.setProperty('active', i == index)
                card.style().unpolish(card)
                card.style().polish(card)
        self.list.setCurrentRow(index)
        self.now.setText(f"正在听第 {index + 1:02d} 句 · {'连续播放' if self.mode.currentIndex() == 1 else '单句练习'}" if index >= 0 else '整段音频 · 自由聆听')

    def play_row(self, index):
        if not 0 <= index < len(self.rows) or self.player.source().isEmpty():
            return
        self.clip = index if self.mode.currentIndex() == 0 else None
        self.highlight(index)
        self.player.setPosition(round(self.rows[index]['start'] * 1000))
        self.player.play()

    def change_mode(self, index):
        if index == 1:
            self.loop.setChecked(False)
            self.clip = None
        else:
            self.clip = self.active if self.active >= 0 else None
        self.now.setText('连续播放 · 将播放至音频末尾' if index else '单句练习 · 句末自动暂停')

    def change_loop(self, checked):
        if checked:
            self.mode.setCurrentIndex(0)
            self.clip = self.active if self.active >= 0 else None

    def begin_seek(self):
        self.scrubbing = True
        self.resume_after_seek = self.player.playbackState() == QMediaPlayer.PlayingState
        self.player.pause()

    def preview_seek(self, ms):
        self.time.setText(f'{timestamp(ms / 1000)} / {timestamp(self.player.duration() / 1000)}')

    def end_seek(self):
        self.seek(self.slider.value())
        self.scrubbing = False
        if self.resume_after_seek:
            self.player.play()

    def keyboard_seek(self, action):
        if not self.scrubbing and action != QSlider.SliderNoAction:
            self.seek(self.slider.sliderPosition())

    def seek(self, ms):
        self.clip = None
        self.mode.setCurrentIndex(1)
        self.loop.setChecked(False)
        self.player.setPosition(ms)

    def toggle(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        elif self.clip is not None and self.player.position() >= round(self.rows[self.clip]['end'] * 1000) - 30:
            self.play_row(self.clip)
        else:
            if self.player.mediaStatus() == QMediaPlayer.EndOfMedia:
                self.player.setPosition(0)
            self.player.play()

    def tick(self):
        if self.scrubbing:
            return
        pos = self.player.position()
        self.slider.setValue(pos)
        self.preview_seek(pos)
        if self.clip is None and not self.player.source().isEmpty():
            index = bisect_right(self.starts, pos / 1000) - 1
            if index >= 0 and pos / 1000 > self.rows[index]['end']:
                index = -1
            self.highlight(index)
        elif self.clip is not None and pos >= round(self.rows[self.clip]['end'] * 1000) and (self.player.playbackState() == QMediaPlayer.PlayingState or self.player.mediaStatus() == QMediaPlayer.EndOfMedia):
            if self.loop.isChecked():
                self.play_row(self.clip)
            else:
                self.player.pause()

    def export(self):
        path, selected = QFileDialog.getSaveFileName(self, '导出文本', str(Path(self.audio_path).with_suffix('.srt')), '字幕 (*.srt);;纯文本 (*.txt)')
        if path:
            try:
                Path(path).write_text(to_srt(self.rows) if selected.startswith('字幕') else '\n'.join(r['text'] for r in self.rows), encoding='utf-8-sig')
                self.status.setText('已导出：' + path)
            except OSError as exc:
                QMessageBox.warning(self, '导出失败', str(exc))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.cancel()
            QMessageBox.information(self, '正在停止识别', '已请求取消，请等待当前步骤结束后再关闭窗口。')
            event.ignore()
        else:
            self.save_current()
            self.player.stop()
            event.accept()


STYLE = '''
QWidget { background: #f5f7fa; color: #243b4b; font-family: "Microsoft YaHei UI"; font-size: 13px; }
QFrame#sidebar { background: #e9f0ed; border-right: 1px solid #d9e4de; }
QFrame#sidebar QLabel { background: transparent; }
QLabel#logo { font-size: 23px; font-weight: 700; color: #1b6053; }
QLabel#title { font-size: 28px; font-weight: 700; color: #203e42; }
QLabel#eyebrow { font-size: 11px; color: #408575; letter-spacing: 2px; }
QLabel#muted { color: #7a8994; font-size: 12px; background: transparent; }
QPushButton, QComboBox, QLineEdit { background: white; border: 1px solid #dce5e6; border-radius: 8px; padding: 9px 12px; }
QPushButton:hover { background: #e8f3ee; border-color: #559f87; }
QPushButton:disabled { color: #a3afb5; background: #edf1f3; }
QPushButton#primary { background: #247b66; color: white; border: 1px solid #247b66; font-weight: 600; }
QPushButton#primary:hover { background: #196550; }
QPushButton#primary:disabled { background: #a6c8bc; border-color: #a6c8bc; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { border-radius: 10px; }
QListWidget::item:selected { background: #d5e8df; }
QListWidget#history::item { padding: 13px 9px; margin: 3px 0; }
QListWidget#history::item:hover { background: #dfebe4; }
QFrame#sentence { background: white; border: 1px solid #e0e8e9; border-radius: 10px; }
QFrame#sentence[active="true"] { border: 2px solid #73b399; background: #f7fcf9; }
QFrame#sentence QLabel { background: transparent; }
QFrame#sentence QLabel#masked { color: #82968e; background: #edf3ef; border-radius: 6px; padding: 8px; }
QLabel#answer { color: #233e49; font-size: 15px; padding: 5px; }
QFrame#playerBox { background: white; border: 1px solid #dce6e4; border-radius: 14px; }
QFrame#playerBox QLabel, QFrame#playerBox QCheckBox { background: transparent; }
QLabel#playingTitle { color: #237c64; font-weight: 600; }
QProgressBar { border: 0; background: #e5ece9; border-radius: 2px; }
QProgressBar::chunk { background: #54a88a; border-radius: 2px; }
QSlider { background: transparent; min-height: 22px; }
QSlider::groove:horizontal { background: #e2ebe7; height: 5px; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #3d977c; border-radius: 2px; }
QSlider::handle:horizontal { background: #247b66; border: 3px solid #dcefe6; width: 12px; margin: -6px 0; border-radius: 9px; }
QCheckBox { spacing: 6px; background: transparent; }
QComboBox { padding-right: 32px; min-height: 18px; }
QComboBox:hover, QComboBox:focus { border-color: #71ad98; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 28px; border: none; background: transparent; }
QComboBox::down-arrow { image: none; width: 0; height: 0; }
QComboBox QAbstractItemView { background: white; border: 1px solid #d5e5dd; border-radius: 8px; padding: 6px; outline: none; selection-background-color: #e0efe7; selection-color: #21634f; }
QComboBox QAbstractItemView::item { min-height: 30px; padding: 4px 10px; }
QMenu { background: white; border: 1px solid #d5e5dd; padding: 6px; border-radius: 9px; }
QMenu::item { padding: 9px 20px; border-radius: 5px; }
QMenu::item:selected { background: #e0efe7; color: #21634f; }
QMenu::separator { height: 1px; background: #e5ede9; margin: 5px; }
QScrollBar:vertical { background: #e6eeea; width: 10px; margin: 3px 1px; border-radius: 5px; }
QScrollBar::handle:vertical { background: #a7c8b9; border-radius: 4px; min-height: 36px; margin: 1px; }
QScrollBar::handle:vertical:hover { background: #79ae98; }
QScrollBar::handle:vertical:pressed { background: #4e9478; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; background: transparent; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: #e6eeea; height: 10px; border-radius: 5px; }
QScrollBar::handle:horizontal { background: #a7c8b9; min-width: 36px; border-radius: 4px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
'''
