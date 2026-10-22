"""Окно «Вид и настройки»: галерея видов колеса с живыми превью и основные настройки.

Открывается кликом по значку (Windows), пунктом меню (macOS) или повторным запуском
ConvWheel — на случай, если значок спрятан за «чёлкой» MacBook.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

from . import APP_NAME, __version__, autostart, themes
from .config import CONFIG
from .icons import app_icon
from .platform_utils import IS_MAC, IS_WIN

STYLE = """
QWidget#root { background: #12161F; }
QLabel { color: #E8EEF7; }
QLabel#title { font-size: 22px; font-weight: 700; }
QLabel#status { color: #9AA6B8; font-size: 13px; }
QLabel#status[warn="true"] { color: #FFB547; }
QLabel#section { color: #C9D3E2; font-size: 13px; font-weight: 700; letter-spacing: 0.5px; }
QFrame#line { background: #232B3A; max-height: 1px; min-height: 1px; border: none; }
QPushButton { background: #2A3446; color: #E8EEF7; border: none; border-radius: 8px;
              padding: 8px 14px; font-size: 13px; }
QPushButton:hover { background: #34405A; }
QPushButton#primary { background: #E8E8E6; color: #1A1D23; font-weight: 600; }
QPushButton#primary:hover { background: #FFFFFF; }
QPushButton#danger { background: transparent; color: #FF8A8A; }
QPushButton#danger:hover { background: #2A1C22; }
QCheckBox { color: #E8EEF7; font-size: 13px; spacing: 8px; }
QComboBox { background: #1A202B; color: #E8EEF7; border: 1px solid #2E3850; border-radius: 7px;
            padding: 5px 10px; font-size: 13px; min-width: 210px; }
QComboBox QAbstractItemView { background: #1A202B; color: #E8EEF7; selection-background-color: #34405A; }
QLabel.label { color: #C9D3E2; font-size: 13px; }
"""

CARD_W, CARD_H, PREVIEW = 168, 212, 150


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
        self.setToolTip(f"Вид «{self.theme.name}»")
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
        border = QColor("#E8E8E6") if self.selected else QColor("#3A4660" if self.hover else "#263042")
        p.setPen(QPen(border, 2 if self.selected else 1.2))
        p.drawRoundedRect(r, 14, 14)
        # «обои» под превью — чтобы светлые и полупрозрачные виды были видны как на рабочем столе
        area = QRectF(9, 9, CARD_W - 18, PREVIEW + 6)
        clip = QPainterPath()
        clip.addRoundedRect(area, 10, 10)
        g = QLinearGradient(area.topLeft(), area.bottomRight())
        g.setColorAt(0.0, QColor("#4E6378"))
        g.setColorAt(0.55, QColor("#8A7A70"))
        g.setColorAt(1.0, QColor("#C59A72"))
        p.fillPath(clip, g)
        p.save()
        p.setClipPath(clip)
        pw = self.preview.width() / self.preview.devicePixelRatio()
        p.drawPixmap(QPointF(area.center().x() - pw / 2, area.top() + 3), self.preview)
        p.restore()
        f = QFont(self.font())
        f.setPixelSize(14)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF") if self.selected else QColor("#C9D3E2"))
        p.drawText(QRectF(0, PREVIEW + 17, CARD_W, 22), Qt.AlignCenter, self.theme.name)
        if self.key == themes.DEFAULT_THEME:
            f.setPixelSize(10)
            f.setWeight(QFont.Normal)
            p.setFont(f)
            p.setPen(QColor("#7F8BA0"))
            p.drawText(QRectF(0, PREVIEW + 39, CARD_W, 14), Qt.AlignCenter, "по умолчанию")
        if self.selected:                       # галочка в углу
            c = QPointF(CARD_W - 22, 22)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#E8E8E6"))
            p.drawEllipse(c, 11, 11)
            pen = QPen(QColor("#12161F"), 2.4)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            path = QPainterPath(QPointF(c.x() - 5, c.y()))
            path.lineTo(QPointF(c.x() - 1.5, c.y() + 3.5))
            path.lineTo(QPointF(c.x() + 5, c.y() - 3.5))
            p.drawPath(path)
        p.end()


class SettingsWindow(QWidget):
    theme_changed = Signal(str)
    demo_requested = Signal(str)
    quit_requested = Signal()
    permissions_requested = Signal()
    settings_changed = Signal()

    def __init__(self, welcome: bool = False):
        super().__init__()
        self.setObjectName("root")
        self.setWindowTitle(f"{APP_NAME} — вид и настройки")
        self.setWindowIcon(app_icon())
        self.setStyleSheet(STYLE)
        self.setAttribute(Qt.WA_StyledBackground, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 22)
        lay.setSpacing(10)

        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.status.setWordWrap(True)
        col.addWidget(title)
        col.addWidget(self.status)
        head.addLayout(col, 1)
        ver = QLabel(f"версия {__version__}")
        ver.setObjectName("status")
        head.addWidget(ver, 0, Qt.AlignTop)
        lay.addLayout(head)
        if welcome:
            where = "в строке меню вверху справа" if IS_MAC else "в трее у часов"
            hello = QLabel(f"ConvWheel работает в фоне — значок-долька {where}. "
                           "Зажмите Shift и кликните по файлу или папке. Если значка не видно, "
                           "просто откройте ConvWheel ещё раз — появится это окно.")
            hello.setObjectName("status")
            hello.setWordWrap(True)
            hello.setStyleSheet("color:#E8E8E6; background:#1C2330; border-radius:10px; padding:10px 12px;")
            lay.addWidget(hello)

        lay.addSpacing(6)
        sec = QLabel("ВИД КОЛЕСА")
        sec.setObjectName("section")
        lay.addWidget(sec)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)
        self.cards: dict[str, ThemeCard] = {}
        current = themes.normalize(CONFIG.theme)
        for i, key in enumerate(themes.THEMES):
            card = ThemeCard(key, key == current)
            card.clicked.connect(self._pick)
            self.cards[key] = card
            grid.addWidget(card, i // 4, i % 4)
        lay.addLayout(grid)

        row = QHBoxLayout()
        hint = QLabel("Нажмите на вид, чтобы выбрать его. Изменения применяются сразу.")
        hint.setObjectName("status")
        row.addWidget(hint, 1)
        demo = QPushButton("Посмотреть вживую")
        demo.setObjectName("primary")
        demo.setCursor(Qt.PointingHandCursor)
        demo.clicked.connect(lambda: self.demo_requested.emit(themes.normalize(CONFIG.theme)))
        row.addWidget(demo)
        lay.addLayout(row)

        lay.addSpacing(8)
        line = QFrame()
        line.setObjectName("line")
        lay.addWidget(line)
        lay.addSpacing(4)
        sec2 = QLabel("НАСТРОЙКИ")
        sec2.setObjectName("section")
        lay.addWidget(sec2)

        form = QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(10)
        self.cb_enabled = QCheckBox("Колесо включено")
        self.cb_enabled.setChecked(CONFIG.enabled)
        self.cb_enabled.toggled.connect(self._set_enabled)
        form.addWidget(self.cb_enabled, 0, 0)

        btn_label = QLabel("Кнопка вызова")
        btn_label.setProperty("class", "label")
        self.cmb_button = QComboBox()
        for key, label in (("left", "Shift + левая кнопка"), ("middle", "Shift + колёсико"),
                           ("right", "Shift + правая кнопка")):
            self.cmb_button.addItem(label, key)
        self.cmb_button.setCurrentIndex(max(0, self.cmb_button.findData(CONFIG.trigger_button)))
        self.cmb_button.currentIndexChanged.connect(self._set_button)
        btn_row = QHBoxLayout()
        btn_row.addWidget(btn_label)
        btn_row.addWidget(self.cmb_button)
        btn_row.addStretch(1)
        form.addLayout(btn_row, 0, 1)

        if IS_WIN or IS_MAC:
            self.cb_auto = QCheckBox("Запускать при входе в систему")
            self.cb_auto.setChecked(autostart.is_enabled())
            self.cb_auto.toggled.connect(autostart.set_enabled)
            form.addWidget(self.cb_auto, 1, 0)
        lay.addLayout(form)

        lay.addSpacing(6)
        bottom = QHBoxLayout()
        if IS_MAC:
            perm = QPushButton("Разрешения macOS…")
            perm.setCursor(Qt.PointingHandCursor)
            perm.clicked.connect(self.permissions_requested.emit)
            bottom.addWidget(perm)
        bottom.addStretch(1)
        quit_btn = QPushButton(f"Выйти из {APP_NAME}")
        quit_btn.setObjectName("danger")
        quit_btn.setCursor(Qt.PointingHandCursor)
        quit_btn.clicked.connect(self.quit_requested.emit)
        bottom.addWidget(quit_btn)
        lay.addLayout(bottom)
        self.adjustSize()
        self.setFixedSize(self.sizeHint())

    def set_status(self, text: str, warn: bool = False):
        self.status.setText(text)
        self.status.setProperty("warn", warn)
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)

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
