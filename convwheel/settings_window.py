"""Окно ConvWheel: выбор вида колеса и основные настройки.

Ведёт себя как у AmneziaVPN: открывается пунктом «Показать ConvWheel» в меню значка
(на Windows — ещё и кликом по значку), крестик только прячет окно — ConvWheel продолжает
работать в строке меню / трее. Полностью закрыть — «Закрыть ConvWheel» в меню значка.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QLinearGradient, QPainter, QPainterPath, QPen, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from . import APP_NAME, __version__, autostart, themes
from .config import CONFIG
from .icons import app_icon
from .platform_utils import IS_MAC, IS_WIN

STYLE = """
QWidget#root { background: #12161F; }
QLabel { color: #E8EEF7; }
QLabel#title { font-size: 17px; font-weight: 700; }
QLabel#muted { color: #8C98AB; font-size: 12px; }
QLabel#warn { color: #FFB547; font-size: 12px; }
QLabel#hello { color: #E8E8E6; background: #1C2330; border-radius: 9px; padding: 8px 10px; font-size: 12px; }
QLabel#section { color: #AEB9CA; font-size: 11px; font-weight: 700; letter-spacing: 0.6px; }
QPushButton { background: #2A3446; color: #E8EEF7; border: none; border-radius: 7px;
              padding: 6px 12px; font-size: 12px; }
QPushButton:hover { background: #34405A; }
QPushButton#primary { background: #E8E8E6; color: #1A1D23; font-weight: 600; }
QPushButton#primary:hover { background: #FFFFFF; }
QCheckBox { color: #E8EEF7; font-size: 12px; spacing: 7px; }
QComboBox { background: #1A202B; color: #E8EEF7; border: 1px solid #2E3850; border-radius: 6px;
            padding: 4px 8px; font-size: 12px; min-width: 170px; }
QComboBox QAbstractItemView { background: #1A202B; color: #E8EEF7; selection-background-color: #34405A; }
"""

CARD_W, CARD_H, PREVIEW = 112, 130, 96
COLUMNS = 5


class ThemeCard(QWidget):
    clicked = Signal(str)

    def __init__(self, key: str, selected: bool):
        super().__init__()
        self.key = key
        self.theme = themes.get(key)
        self.selected = selected
        self.hover = False
        self.setFixedSize(CARD_W, CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        tip = f"Вид «{self.theme.name}»"
        if key == themes.DEFAULT_THEME:
            tip += " — по умолчанию"
        self.setToolTip(tip)
        from .wheel import render_preview
        self.preview = render_preview(key, PREVIEW, dpr=max(2.0, self.devicePixelRatioF()))

    def set_selected(self, on: bool):
        self.selected = on
        self.update()

    def enterEvent(self, _):
        self.hover = True
        self.update()

    def leaveEvent(self, _):
        self.hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit(self.key)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        p.setBrush(QColor("#1A202B"))
        border = QColor("#E8E8E6") if self.selected else QColor("#3A4660" if self.hover else "#232B3A")
        p.setPen(QPen(border, 2 if self.selected else 1.1))
        p.drawRoundedRect(r, 11, 11)
        # «обои» под превью — чтобы светлые и полупрозрачные виды были видны как на рабочем столе
        area = QRectF(7, 7, CARD_W - 14, PREVIEW + 4)
        clip = QPainterPath()
        clip.addRoundedRect(area, 8, 8)
        g = QLinearGradient(area.topLeft(), area.bottomRight())
        g.setColorAt(0.0, QColor("#4E6378"))
        g.setColorAt(0.55, QColor("#8A7A70"))
        g.setColorAt(1.0, QColor("#C59A72"))
        p.fillPath(clip, g)
        p.save()
        p.setClipPath(clip)
        pw = self.preview.width() / self.preview.devicePixelRatio()
        p.drawPixmap(QPointF(area.center().x() - pw / 2, area.top() + 2), self.preview)
        p.restore()
        f = QFont(self.font())
        f.setPixelSize(12)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF") if self.selected else QColor("#C9D3E2"))
        p.drawText(QRectF(0, PREVIEW + 13, CARD_W, 18), Qt.AlignCenter, self.theme.name)
        if self.selected:                       # галочка в углу
            c = QPointF(CARD_W - 17, 17)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#E8E8E6"))
            p.drawEllipse(c, 8.5, 8.5)
            pen = QPen(QColor("#12161F"), 2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            path = QPainterPath(QPointF(c.x() - 3.8, c.y()))
            path.lineTo(QPointF(c.x() - 1.1, c.y() + 2.7))
            path.lineTo(QPointF(c.x() + 3.8, c.y() - 2.7))
            p.drawPath(path)
        p.end()


class SettingsWindow(QWidget):
    theme_changed = Signal(str)
    demo_requested = Signal(str)
    permissions_requested = Signal()
    settings_changed = Signal()
    visibility_changed = Signal()

    def __init__(self, welcome: bool = False):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setStyleSheet(STYLE)
        self.setAttribute(Qt.WA_StyledBackground, True)
        QShortcut(QKeySequence.Close, self, activated=self.close)       # Cmd+W / Ctrl+W

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 16)
        lay.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        head.addWidget(title)
        head.addStretch(1)
        ver = QLabel(f"версия {__version__}")
        ver.setObjectName("muted")
        head.addWidget(ver)
        lay.addLayout(head)
        self.status = QLabel("")
        self.status.setObjectName("muted")
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        self.warning = QLabel("")
        self.warning.setObjectName("warn")
        self.warning.setWordWrap(True)
        self.warning.hide()
        lay.addWidget(self.warning)
        if welcome:
            where = "в строке меню вверху" if IS_MAC else "в трее у часов"
            hello = QLabel(f"ConvWheel работает в фоне — значок-долька {where}. Зажмите Shift и "
                           "кликните по файлу или папке. Это окно можно закрыть.")
            hello.setObjectName("hello")
            hello.setWordWrap(True)
            lay.addWidget(hello)

        lay.addSpacing(4)
        sec_row = QHBoxLayout()
        sec = QLabel("ВИД КОЛЕСА")
        sec.setObjectName("section")
        sec_row.addWidget(sec)
        sec_row.addStretch(1)
        demo = QPushButton("Посмотреть вживую")
        demo.setObjectName("primary")
        demo.setCursor(Qt.PointingHandCursor)
        demo.clicked.connect(lambda: self.demo_requested.emit(themes.normalize(CONFIG.theme)))
        sec_row.addWidget(demo)
        lay.addLayout(sec_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self.cards: dict[str, ThemeCard] = {}
        current = themes.normalize(CONFIG.theme)
        for i, key in enumerate(themes.THEMES):
            card = ThemeCard(key, key == current)
            card.clicked.connect(self._pick)
            self.cards[key] = card
            grid.addWidget(card, i // COLUMNS, i % COLUMNS)
        lay.addLayout(grid)

        lay.addSpacing(6)
        sec2 = QLabel("НАСТРОЙКИ")
        sec2.setObjectName("section")
        lay.addWidget(sec2)

        row1 = QHBoxLayout()
        self.cb_enabled = QCheckBox("Колесо включено")
        self.cb_enabled.setChecked(CONFIG.enabled)
        self.cb_enabled.toggled.connect(self._set_enabled)
        row1.addWidget(self.cb_enabled)
        row1.addStretch(1)
        lbl = QLabel("Вызов:")
        lbl.setObjectName("muted")
        row1.addWidget(lbl)
        self.cmb_button = QComboBox()
        for key, label in (("left", "Shift + левая кнопка"), ("middle", "Shift + колёсико"),
                           ("right", "Shift + правая кнопка")):
            self.cmb_button.addItem(label, key)
        self.cmb_button.setCurrentIndex(max(0, self.cmb_button.findData(CONFIG.trigger_button)))
        self.cmb_button.currentIndexChanged.connect(self._set_button)
        row1.addWidget(self.cmb_button)
        lay.addLayout(row1)

        row2 = QHBoxLayout()
        if IS_WIN or IS_MAC:
            self.cb_auto = QCheckBox("Запускать при входе в систему")
            self.cb_auto.setChecked(autostart.is_enabled())
            self.cb_auto.toggled.connect(autostart.set_enabled)
            row2.addWidget(self.cb_auto)
        row2.addStretch(1)
        if IS_MAC:
            perm = QPushButton("Разрешения macOS…")
            perm.setCursor(Qt.PointingHandCursor)
            perm.clicked.connect(self.permissions_requested.emit)
            row2.addWidget(perm)
        lay.addLayout(row2)
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    # окно не уничтожается: крестик только прячет его
    def showEvent(self, e):
        super().showEvent(e)
        self.visibility_changed.emit()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.visibility_changed.emit()

    def set_status(self, text: str, warning: str = ""):
        self.status.setText(text)
        self.warning.setText(warning)
        self.warning.setVisible(bool(warning))
        self.setFixedSize(self.sizeHint())

    def sync(self):
        """Обновить переключатели, если настройки поменяли из меню значка."""
        current = themes.normalize(CONFIG.theme)
        for k, c in self.cards.items():
            c.set_selected(k == current)
        self.cb_enabled.blockSignals(True)
        self.cb_enabled.setChecked(CONFIG.enabled)
        self.cb_enabled.blockSignals(False)
        self.cmb_button.blockSignals(True)
        self.cmb_button.setCurrentIndex(max(0, self.cmb_button.findData(CONFIG.trigger_button)))
        self.cmb_button.blockSignals(False)

    def _pick(self, key: str):
        CONFIG.theme = key
        CONFIG.save()
        for k, c in self.cards.items():
            c.set_selected(k == key)
        self.theme_changed.emit(key)

    def _set_enabled(self, on: bool):
        CONFIG.enabled = on
        CONFIG.save()
        self.settings_changed.emit()

    def _set_button(self, _i: int):
        CONFIG.trigger_button = self.cmb_button.currentData()
        CONFIG.save()
        self.settings_changed.emit()
