"""Рисует иконку приложения 1024×1024 (PNG) — PyInstaller сам превратит её в .icns/.ico.
Серая долька цитруса на тёмном «скруглённом квадрате» — в одном стиле со значком строки меню.

    python tools/make_icon.py packaging/icon.png
"""
import math
import os
import random
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt  # noqa: E402
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QLinearGradient, QPainter,  # noqa: E402
                           QPainterPath, QPainterPathStroker, QPen, QPolygonF, QRadialGradient)

S = 1024


def _wedge(c, i, n, ri, ro, gap, rnd):
    mid = 90 - i * 360 / n
    half = 180 / n
    ri, ro = ri + rnd, ro - rnd
    ho = half - math.degrees((gap / 2 + rnd) / ro)
    hi = max(0.8, half - math.degrees((gap / 2 + rnd) / ri))

    def pt(rad, a):
        return QPointF(c.x() + rad * math.cos(math.radians(a)), c.y() - rad * math.sin(math.radians(a)))

    pts = [pt(ro, mid + ho - 2 * ho * k / 24) for k in range(25)]
    pts += [pt(ri, mid - hi + 2 * hi * k / 6) for k in range(7)]
    poly = QPainterPath()
    poly.addPolygon(QPolygonF(pts))
    poly.closeSubpath()
    st = QPainterPathStroker()
    st.setWidth(2 * rnd)
    st.setJoinStyle(Qt.RoundJoin)
    return st.createStroke(poly).united(poly).simplified(), mid


def render(path: Path):
    QGuiApplication.instance() or QGuiApplication([])
    img = QImage(S, S, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)

    m = 100                                                   # поле по сетке иконок macOS
    body = QPainterPath()
    body.addRoundedRect(QRectF(m, m, S - 2 * m, S - 2 * m), 185, 185)
    g = QLinearGradient(0, m, 0, S - m)
    g.setColorAt(0, QColor("#2C313A"))
    g.setColorAt(1, QColor("#14171C"))
    p.fillPath(body, g)
    p.setPen(QPen(QColor(255, 255, 255, 26), 4))
    p.drawPath(body)

    c = QPointF(S / 2, S / 2 - 6)
    R, PITH = 330, 300
    p.setPen(Qt.NoPen)                                        # тень дольки
    sh = QRadialGradient(QPointF(c.x(), c.y() + 18), R + 30)
    sh.setColorAt(0.85, QColor(0, 0, 0, 110))
    sh.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.setBrush(sh)
    p.drawEllipse(QPointF(c.x(), c.y() + 18), R + 30, R + 30)
    rind = QRadialGradient(c, R)                              # корка
    rind.setColorAt(PITH / R, QColor("#BDBDBB"))
    rind.setColorAt(0.97, QColor("#8E8E8C"))
    rind.setColorAt(1.0, QColor("#747472"))
    p.setBrush(rind)
    p.setPen(QPen(QColor("#666664"), 3))
    p.drawEllipse(c, R, R)
    rnd = random.Random(3)
    p.setPen(Qt.NoPen)
    for _ in range(260):
        a, rr = rnd.uniform(0, 2 * math.pi), rnd.uniform(PITH + 5, R - 5)
        p.setBrush(QColor(255, 255, 255, rnd.choice((40, 60))) if rnd.random() < 0.6 else QColor(0, 0, 0, 30))
        s = rnd.uniform(1.5, 3.2)
        p.drawEllipse(QPointF(c.x() + rr * math.cos(a), c.y() - rr * math.sin(a)), s, s)
    pith = QRadialGradient(c, PITH)                           # белая мякоть
    pith.setColorAt(0.0, QColor("#F6F6F4"))
    pith.setColorAt(0.92, QColor("#E7E7E4"))
    pith.setColorAt(1.0, QColor("#D2D2CF"))
    p.setBrush(pith)
    p.drawEllipse(c, PITH, PITH)

    n = 8
    for i in range(n):                                        # дольки
        wedge, mid = _wedge(c, i, n, 52, 286, 22, 22)
        wg = QRadialGradient(c, 290)
        wg.setColorAt(0.2, QColor("#9C9C9A"))
        wg.setColorAt(1.0, QColor("#BEBEBC"))
        p.setBrush(wg)
        p.setPen(QPen(QColor("#8A8A88"), 3))
        p.drawPath(wedge)
        p.save()
        p.setClipPath(wedge)
        for _ in range(40):                                   # волокна
            fr, fa = rnd.random(), rnd.uniform(-1, 1)
            rad = 80 + fr * 190
            ang = math.radians(mid + fa * (180 / n - 6) * (0.35 + 0.65 * fr))
            ln = rnd.uniform(14, 34)
            x, y = c.x() + rad * math.cos(ang), c.y() - rad * math.sin(ang)
            dx, dy = math.cos(ang) * ln / 2, -math.sin(ang) * ln / 2
            pen = QPen(QColor(255, 255, 255, rnd.randint(70, 140)), rnd.uniform(3, 5.5))
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(x - dx, y - dy), QPointF(x + dx, y + dy))
        p.restore()
    p.setPen(Qt.NoPen)                                        # сердцевина
    p.setBrush(QColor("#EDEDEA"))
    p.drawEllipse(c, 40, 40)
    p.end()
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(path))


if __name__ == "__main__":
    render(Path(sys.argv[1] if len(sys.argv) > 1 else "packaging/icon.png"))
