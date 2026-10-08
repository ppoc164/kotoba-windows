"""Searchable full transcript, with links back to timestamped sentences."""
from html import escape
from PySide6.QtCore import Signal
from PySide6.QtGui import QTextCursor, QTextDocument
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QTextBrowser, QCheckBox)
from sentences import timestamp


class TranscriptPreview(QDialog):
    locate = Signal(int, bool)

    def __init__(self, rows, title, parent=None):
        super().__init__(parent)
        self.rows = rows
        self.setWindowTitle('全文预览 · ' + title)
        self.resize(820, 680)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        heading = QLabel('全文预览')
        heading.setObjectName('title')
        layout.addWidget(heading)
        layout.addWidget(QLabel(f'共 {len(rows)} 句 · 点击任意一句，返回音频中的对应位置'))
        tools = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索全文，按 Enter 查找下一处')
        tools.addWidget(self.search, 1)
        previous = QPushButton('上一处')
        previous.clicked.connect(lambda: self.find_match(True))
        tools.addWidget(previous)
        following = QPushButton('下一处')
        following.clicked.connect(lambda: self.find_match(False))
        tools.addWidget(following)
        layout.addLayout(tools)
        self.result = QLabel('全文模式会显示所有文本，不改变练习中的遮挡设置。')
        self.result.setObjectName('muted')
        layout.addWidget(self.result)
        self.browser = QTextBrowser()
        self.browser.setOpenLinks(False)
        self.browser.setOpenExternalLinks(False)
        self.browser.setStyleSheet('QTextBrowser { background: white; border: 1px solid #dce5e6; border-radius: 10px; padding: 16px; font-size: 16px; }')
        content = ''.join(
            f'<p style="margin-bottom:18px; line-height:150%"><a href="sentence:{i}" style="color:#285e50; text-decoration:none">'
            f'<span style="color:#82958c; font-size:12px">{i+1:02d} · {timestamp(row["start"])}　</span>'
            f'{escape(row["text"]).replace(chr(10), "<br>")}</a></p>'
            for i, row in enumerate(rows))
        self.browser.setHtml(content)
        self.browser.anchorClicked.connect(self.open_sentence)
        layout.addWidget(self.browser, 1)
        bottom = QHBoxLayout()
        self.play = QCheckBox('定位后立即播放')
        bottom.addWidget(self.play)
        bottom.addStretch()
        close = QPushButton('返回练习')
        close.clicked.connect(self.reject)
        bottom.addWidget(close)
        layout.addLayout(bottom)
        self.search.textChanged.connect(self.start_search)
        self.search.returnPressed.connect(lambda: self.find_match(False))

    def start_search(self):
        cursor = self.browser.textCursor()
        cursor.movePosition(QTextCursor.Start)
        self.browser.setTextCursor(cursor)
        self.find_match(False)

    def find_match(self, backward=False):
        query = self.search.text().strip()
        if not query:
            self.result.setText('全文模式会显示所有文本，不改变练习中的遮挡设置。')
            cursor = self.browser.textCursor()
            cursor.clearSelection()
            self.browser.setTextCursor(cursor)
            return
        count = self.browser.toPlainText().casefold().count(query.casefold())
        self.result.setText(f'找到 {count} 处匹配 · 可用上一处 / 下一处循环跳转' if count else '没有匹配的文本，请尝试其他关键词。')
        flags = QTextDocument.FindBackward if backward else QTextDocument.FindFlags()
        if not self.browser.find(query, flags):
            cursor = self.browser.textCursor()
            cursor.movePosition(QTextCursor.End if backward else QTextCursor.Start)
            self.browser.setTextCursor(cursor)
            self.browser.find(query, flags)

    def open_sentence(self, url):
        if url.scheme() != 'sentence':
            return
        try:
            index = int(url.path())
        except ValueError:
            return
        if 0 <= index < len(self.rows):
            self.locate.emit(index, self.play.isChecked())
            self.accept()
