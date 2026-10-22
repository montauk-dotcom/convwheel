"""Значок для строки меню macOS / трея Windows: долька цитруса одной краской.

На macOS значок помечается как «шаблон» (template) — система сама красит его в чёрный
или белый под светлую/тёмную строку меню, как у Forti, AmneziaVPN и системных значков.
На Windows цвет подбирается под тему панели задач.
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPainterPathStroker, QPen, QPixmap, QPolygonF

from .platform_utils import IS_MAC, IS_WIN


def _glyph(px: int, color: QColor) -> QPixmap:
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    c = QPointF(px / 2, px / 2)
    ring_r, ring_w = px * 0.43, max(1.2, px * 0.085)
    p.setPen(QPen(color, ring_w))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(c, ring_r, ring_r)
    n = 6
    ro, ri = px * 0.335, px * 0.07
    gap, rnd = px * 0.085, px * 0.03
    p.setPen(Qt.NoPen)
    p.setBrush(color)
    for i in range(n):
        mid = 90 - i * 360 / n
        half = 180 / n
        ho = half - math.degrees((gap / 2 + rnd) / (ro - rnd))
        hi = max(1.0, half - math.degrees((gap / 2 + rnd) / (ri + rnd)))
        pts = []
        for k in range(9):
            a = math.radians(mid + ho - 2 * ho * k / 8)
            pts.append(QPointF(c.x() + (ro - rnd) * math.cos(a), c.y() - (ro - rnd) * math.sin(a)))
        for a_deg in (mid - hi, mid + hi):
            a = math.radians(a_deg)
            pts.append(QPointF(c.x() + (ri + rnd) * math.cos(a), c.y() - (ri + rnd) * math.sin(a)))
        poly = QPainterPath()
        poly.addPolygon(QPolygonF(pts))
        poly.closeSubpath()
        st = QPainterPathStroker()
        st.setWidth(2 * rnd)
        st.setJoinStyle(Qt.RoundJoin)
        p.drawPath(st.createStroke(poly).united(poly))
    p.end()
    return pm


def windows_taskbar_is_light() -> bool:
    if not IS_WIN:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return bool(winreg.QueryValueEx(k, "SystemUsesLightTheme")[0])
    except OSError:
        return False


def tray_icon() -> QIcon:
    icon = QIcon()
    if IS_MAC:
        for px in (18, 36):                       # 18 pt и @2x для Retina
            icon.addPixmap(_glyph(px, QColor("black")))
        icon.setIsMask(True)                      # template: macOS красит сам
    else:
        col = QColor("#1F1F1F") if windows_taskbar_is_light() else QColor("#F2F2F2")
        for px in (16, 20, 24, 32, 40, 48):
            icon.addPixmap(_glyph(px, col))
    return icon


def app_icon() -> QIcon:
    """Цветной значок для окон (заголовок окна, Alt+Tab)."""
    icon = QIcon()
    for px in (32, 64, 128):
        pm = QPixmap(px, px)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#2A2F38"))
        p.drawRoundedRect(QRectF(0, 0, px, px), px * 0.22, px * 0.22)
        g = _glyph(int(px * 0.8), QColor("#E8E8E6"))
        p.drawPixmap(int(px * 0.1), int(px * 0.1), g)
        p.end()
        icon.addPixmap(pm)
    return icon
