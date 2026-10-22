"""Все виды колеса на фоне рабочего стола: выбор (наведение) и процесс конвертации.

    python tests/render_themes.py ФОН.jpg ВЫХОД.png
"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QFont, QColor
from PySide6.QtCore import Qt, QRect
app = QApplication([])
from convwheel import themes
from convwheel.wheel import render_preview

bg_path, out = sys.argv[1], sys.argv[2]
cell = 300
keys = list(themes.THEMES)
cols = 4
rows = (len(keys) + cols - 1) // cols
sheet = QImage(cell * cols, (cell + 30) * rows * 2, QImage.Format_RGB32)
bg = QImage(bg_path).scaled(cell * cols, (cell + 30) * rows * 2, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
p = QPainter(sheet)
p.drawImage(0, 0, bg)
p.setRenderHint(QPainter.SmoothPixmapTransform)
f = QFont(); f.setPixelSize(18); f.setBold(True); p.setFont(f)
for idx, key in enumerate(keys):
    for half, state in enumerate(("choose", "working")):
        r, c = divmod(idx, cols)
        y0 = (r + half * rows) * (cell + 30)
        pm = render_preview(key, cell - 10, dpr=1.0, hover=1, state=state)
        p.drawPixmap(c * cell + 5, y0 + 30, pm)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRect(c * cell, y0 + 4, cell, 26), Qt.AlignCenter, f"{themes.THEMES[key].name}" + (" — конвертация" if half else ""))
p.end()
sheet.save(out)
print("ok", len(keys))
