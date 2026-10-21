"""Рисует иконку приложения 1024×1024 (PNG) — PyInstaller сам превратит её в .icns/.ico.

    python tools/make_icon.py packaging/icon.png
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QLinearGradient, QPainter,  # noqa: E402
                           QPainterPath, QPen, QRadialGradient)

S = 1024
COLORS = ["#FF5A5F", "#4C8DFF", "#3DDC97", "#FFB547"]


def render(path: Path):
    QGuiApplication.instance() or QGuiApplication([])
    img = QImage(S, S, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    # «скруглённый квадрат» по сетке иконок macOS (поле ~10%)
    m = 100
    body = QRectF(m, m, S - 2 * m, S - 2 * m)
    path_ = QPainterPath()
    path_.addRoundedRect(body, 185, 185)
    g = QLinearGradient(0, m, 0, S - m)
    g.setColorAt(0, QColor("#232B3A"))
    g.setColorAt(1, QColor("#0E1219"))
    p.fillPath(path_, g)
    p.setPen(QPen(QColor(255, 255, 255, 28), 4))
    p.drawPath(path_)

    c = QPointF(S / 2, S / 2)
    glow = QRadialGradient(c, 360)
    glow.setColorAt(0.0, QColor(59, 182, 255, 70))
    glow.setColorAt(1.0, QColor(59, 182, 255, 0))
    p.fillPath(path_, glow)

    r = 250
    rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
    for i, col in enumerate(COLORS):
        pen = QPen(QColor(col), 92)
        pen.setCapStyle(Qt.FlatCap)
        p.setPen(pen)
        p.drawArc(rect, int((90 - i * 90 - 4) * 16), int(-82 * 16))
    p.setPen(QPen(QColor(120, 205, 255, 200), 10))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(c, r + 62, r + 62)

    # документ в центре
    w, h, fold = 150, 190, 46
    x, y = c.x() - w / 2, c.y() - h / 2
    doc = QPainterPath()
    doc.moveTo(x, y)
    doc.lineTo(x + w - fold, y)
    doc.lineTo(x + w, y + fold)
    doc.lineTo(x + w, y + h)
    doc.lineTo(x, y + h)
    doc.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QColor("#EEF2F8"))
    p.drawPath(doc)
    tri = QPainterPath()
    tri.moveTo(x + w - fold, y)
    tri.lineTo(x + w - fold, y + fold)
    tri.lineTo(x + w, y + fold)
    tri.closeSubpath()
    p.setBrush(QColor("#B9C3D3"))
    p.drawPath(tri)
    p.setBrush(QColor("#9FB0C8"))
    for k in range(3):
        p.drawRoundedRect(QRectF(x + 28, y + 80 + k * 32, w - 56 - (30 if k == 2 else 0), 14), 7, 7)
    p.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))


if __name__ == "__main__":
    render(Path(sys.argv[1] if len(sys.argv) > 1 else "packaging/icon.png"))
