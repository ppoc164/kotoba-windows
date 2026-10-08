"""Render the vector icon into a multi-resolution Windows ICO."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import struct
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtCore import QByteArray, QBuffer, QIODevice, Qt

app = QApplication([])
root = Path(__file__).parent / 'assets'
renderer = QSvgRenderer(str(root / 'kotoba.svg'))
sizes = [16, 24, 32, 48, 64, 128, 256]
images = []
for size in sizes:
    image = QImage(size, size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    image.save(buffer, 'PNG')
    images.append(bytes(data))
    if size == 256:
        image.save(str(root / 'kotoba.png'))
offset = 6 + 16 * len(sizes)
directory = bytearray(struct.pack('<HHH', 0, 1, len(sizes)))
for size, data in zip(sizes, images):
    directory.extend(struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
    offset += len(data)
(root / 'kotoba.ico').write_bytes(directory + b''.join(images))
print('Created Windows icon with sizes:', sizes)
