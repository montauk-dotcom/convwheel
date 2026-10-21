"""Радиальное меню конвертации.

Вся анимация идёт от одного таймера ~60 FPS с экспоненциальным сглаживанием: значения
плавно «догоняют» цель, поэтому подсветка перетекает между секторами без рывков.
"""
from __future__ import annotations

import math
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QCursor, QFont, QFontMetrics, QGuiApplication, QKeyEvent,
                           QMouseEvent, QPainter, QPainterPath, QPen, QRadialGradient)
from PySide6.QtWidgets import QWidget

from .engine import ConvertJob
from .formats import Target
from .platform_utils import IS_MAC, IS_WIN, human_size, reveal_in_file_manager

SIZE = 480
R_OUT = 180.0
R_IN = 76.0
GAP_DEG = 1.6
ACCENT = QColor("#3BB6FF")


def ease_out_back(t: float, s: float = 1.45) -> float:
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def approach(cur: float, target: float, dt: float, speed: float = 16.0) -> float:
    return target + (cur - target) * math.exp(-speed * dt)


class ConvertWheel(QWidget):
    closed = Signal()

    CHOOSE, WORKING, DONE, ERROR = range(4)

    def __init__(self, files: list[Path], targets: list[Target]):
        super().__init__(None)
        self.files = files
        self.targets = targets
        self.n = max(len(targets), 1)
        self.step = 360.0 / self.n

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.resize(SIZE, SIZE)

        # --- состояние анимации
        self.state = self.CHOOSE
        self.t_open_start = time.perf_counter()
        self.open_p = 0.0            # 0..1 появление
        self.closing_from: float | None = None
        self.hover = -1
        self.hover_amt = [0.0] * self.n       # плавная подсветка каждого сектора
        self.hl_angle = None                  # угол «бегунка»-подсветки
        self.center_hover = 0.0
        self.dim = 0.0                         # затемнение секторов во время работы
        self.spin = 0.0
        self.progress = -1.0
        self.progress_shown = 0.0
        self.status_text = ""
        self.result_paths: list[str] = []
        self.chosen: Target | None = None
        self.result_t = 0.0                    # анимация галочки/крестика
        self.job: ConvertJob | None = None
        self.last_tick = time.perf_counter()
        self.mouse_inside_since_done = False

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000 // 120)

        self.autoclose = QTimer(self)
        self.autoclose.setSingleShot(True)
        self.autoclose.timeout.connect(self.dismiss)

    # ------------------------------------------------------------------ показ
    def popup_at(self, pos=None):
        pos = pos or QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        g = screen.availableGeometry()
        x = min(max(pos.x() - SIZE // 2, g.left()), g.right() - SIZE)
        y = min(max(pos.y() - SIZE // 2, g.top()), g.bottom() - SIZE)
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()
        _force_foreground(self)
        self.setFocus()

    def dismiss(self):
        if self.state == self.WORKING:
            return  # не закрываем во время конвертации
        if self.closing_from is None:
            self.closing_from = time.perf_counter()

    def contains_global(self, gp) -> bool:
        c = self.mapToGlobal(QPointF(SIZE / 2, SIZE / 2).toPoint())
        return math.hypot(gp.x() - c.x(), gp.y() - c.y()) <= R_OUT + 14

    # ------------------------------------------------------------------ геометрия
    @property
    def c(self) -> QPointF:
        return QPointF(SIZE / 2, SIZE / 2)

    def seg_center_angle(self, i: int) -> float:
        """Угол центра сектора в градусах Qt (0 = справа, против часовой). 0-й — сверху."""
        return 90.0 - i * self.step

    def index_at(self, p: QPointF) -> int:
        dx, dy = p.x() - self.c.x(), p.y() - self.c.y()
        r = math.hypot(dx, dy)
        if r < R_IN - 4 or r > R_OUT + 40 or not self.targets:
            return -1
        ang = math.degrees(math.atan2(-dy, dx))
        return int(round((90.0 - ang) / self.step)) % self.n

    def in_center(self, p: QPointF) -> bool:
        return math.hypot(p.x() - self.c.x(), p.y() - self.c.y()) < R_IN - 4

    # ------------------------------------------------------------------ анимация
    def _tick(self):
        now = time.perf_counter()
        dt = min(now - self.last_tick, 0.05)
        self.last_tick = now

        # появление/исчезновение
        if self.closing_from is not None:
            k = min((now - self.closing_from) / 0.16, 1.0)
            self.open_p = 1.0 - ease_out_cubic(k)
            if k >= 1.0:
                self.timer.stop()
                self.close()
                return
        else:
            self.open_p = min((now - self.t_open_start) / 0.30, 1.0)

        for i in range(self.n):
            self.hover_amt[i] = approach(self.hover_amt[i], 1.0 if i == self.hover else 0.0, dt, 18)
        if self.hover >= 0:
            target = self.seg_center_angle(self.hover)
            if self.hl_angle is None:
                self.hl_angle = target
            else:  # кратчайший путь по окружности
                diff = (target - self.hl_angle + 180) % 360 - 180
                self.hl_angle = self.hl_angle + diff * (1 - math.exp(-20 * dt))

        hovering_center = self.state in (self.DONE, self.ERROR) and self.in_center(
            QPointF(self.mapFromGlobal(QCursor.pos())))
        self.center_hover = approach(self.center_hover, 1.0 if hovering_center else 0.0, dt, 14)
        self.dim = approach(self.dim, 1.0 if self.state != self.CHOOSE else 0.0, dt, 10)
        self.spin = (self.spin + dt * 300) % 360
        if self.progress >= 0:
            self.progress_shown = approach(self.progress_shown, self.progress, dt, 9)
        if self.state in (self.DONE, self.ERROR):
            self.result_t = min(self.result_t + dt / 0.45, 1.0)
            # автозакрытие, но не пока курсор над колесом
            inside = self.contains_global(QCursor.pos())
            if inside and self.autoclose.isActive():
                self.autoclose.stop()
            elif not inside and not self.autoclose.isActive() and self.closing_from is None:
                self.autoclose.start(2600 if self.state == self.DONE else 6000)
        self.update()

    # ------------------------------------------------------------------ ввод
    def mouseMoveEvent(self, e: QMouseEvent):
        if self.state == self.CHOOSE:
            self.hover = self.index_at(e.position())
            self.setCursor(Qt.PointingHandCursor if self.hover >= 0 else Qt.ArrowCursor)
        elif self.state in (self.DONE, self.ERROR):
            self.setCursor(Qt.PointingHandCursor if self.in_center(e.position()) else Qt.ArrowCursor)

    def leaveEvent(self, _):
        if self.state == self.CHOOSE:
            self.hover = -1

    def mousePressEvent(self, e: QMouseEvent):
        p = e.position()
        if e.button() == Qt.RightButton:
            self.dismiss()
            return
        if self.state == self.CHOOSE:
            i = self.index_at(p)
            if i >= 0:
                self.start(i)
            elif self.in_center(p) or not self.contains_global(e.globalPosition().toPoint()):
                self.dismiss()
        elif self.state == self.DONE:
            if self.in_center(p) and self.result_paths:
                reveal_in_file_manager(self.result_paths[0])
            self.dismiss()
        elif self.state == self.ERROR:
            self.dismiss()

    def keyPressEvent(self, e: QKeyEvent):
        k = e.key()
        if k == Qt.Key_Escape:
            self.dismiss()
        elif self.state == self.CHOOSE:
            if Qt.Key_1 <= k <= Qt.Key_9 and k - Qt.Key_1 < len(self.targets):
                self.start(k - Qt.Key_1)
            elif k in (Qt.Key_Right, Qt.Key_Down, Qt.Key_Tab):
                self.hover = (self.hover + 1) % self.n
            elif k in (Qt.Key_Left, Qt.Key_Up):
                self.hover = (self.hover - 1) % self.n if self.hover >= 0 else self.n - 1
            elif k in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) and self.hover >= 0:
                self.start(self.hover)
        elif self.state == self.DONE and k in (Qt.Key_Return, Qt.Key_Enter) and self.result_paths:
            reveal_in_file_manager(self.result_paths[0])
            self.dismiss()

    def changeEvent(self, e):
        # клик в любое другое место (окно потеряло активность) — закрываемся
        if e.type() == e.Type.ActivationChange and not self.isActiveWindow() and self.state == self.CHOOSE:
            if not self.contains_global(QCursor.pos()):
                self.dismiss()
        super().changeEvent(e)

    def closeEvent(self, e):
        self.closed.emit()
        super().closeEvent(e)

    # ------------------------------------------------------------------ конвертация
    def start(self, i: int):
        self.chosen = self.targets[i]
        self.hover = i
        self.state = self.WORKING
        self.status_text = f"В {self.chosen.label}…"
        self.setCursor(Qt.BusyCursor)
        self.job = ConvertJob(self.files, self.chosen, self)
        self.job.progressed.connect(self._on_progress)
        self.job.succeeded.connect(self._on_done)
        self.job.failed.connect(self._on_fail)
        self.job.start()

    def _on_progress(self, p: float, _name: str):
        self.progress = p

    def _on_done(self, outs: list):
        self.result_paths = outs
        self.progress = 1.0
        self.state = self.DONE
        self.status_text = Path(outs[0]).name if len(outs) == 1 else f"Готово: {len(outs)} файл(а)"
        self.result_t = 0.0
        self.setCursor(Qt.ArrowCursor)

    def _on_fail(self, msg: str):
        self.state = self.ERROR
        self.status_text = msg
        self.result_t = 0.0
        self.setCursor(Qt.ArrowCursor)

    # ------------------------------------------------------------------ отрисовка
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        op = self.open_p
        appear = ease_out_back(op) if self.closing_from is None else op
        p.setOpacity(min(1.0, op * 1.6))
        p.translate(self.c)
        sc = 0.55 + 0.45 * appear
        p.scale(sc, sc)
        p.rotate(-14 * (1 - appear))           # лёгкое «докручивание» при появлении
        p.translate(-self.c)

        self._paint_base(p)
        for i, t in enumerate(self.targets):
            # каскад: каждый следующий сектор появляется чуть позже
            local = max(0.0, min(1.0, (op * 1.5) - i * 0.05)) if self.closing_from is None else 1.0
            self._paint_segment(p, i, t, local)
        self._paint_highlight_ring(p)
        self._paint_center(p)
        p.end()

    def _paint_base(self, p: QPainter):
        c = self.c
        # мягкое свечение
        for k, a in ((22, 18), (14, 28), (7, 45)):
            p.setPen(QPen(QColor(59, 182, 255, a), k))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, R_OUT + 2, R_OUT + 2)
        g = QRadialGradient(c, R_OUT)
        g.setColorAt(0.0, QColor(30, 37, 50, 246))
        g.setColorAt(0.7, QColor(17, 21, 30, 244))
        g.setColorAt(1.0, QColor(11, 14, 20, 246))
        p.setBrush(g)
        p.setPen(QPen(QColor(120, 205, 255, 230), 2.2))
        p.drawEllipse(c, R_OUT, R_OUT)

    def _segment_path(self, i: int, r_in: float, r_out: float, grow: float = 0.0) -> QPainterPath:
        mid = self.seg_center_angle(i)
        half = (self.step - GAP_DEG) / 2
        a0, sweep = mid + half, -(2 * half)
        c = self.c
        # «выдвигаем» сектор наружу при наведении
        off = grow * 7
        cx = c.x() + off * math.cos(math.radians(mid))
        cy = c.y() - off * math.sin(math.radians(mid))
        ro, ri = r_out + grow * 4, r_in
        path = QPainterPath()
        path.arcMoveTo(QRectF(cx - ro, cy - ro, 2 * ro, 2 * ro), a0)
        path.arcTo(QRectF(cx - ro, cy - ro, 2 * ro, 2 * ro), a0, sweep)
        path.arcTo(QRectF(cx - ri, cy - ri, 2 * ri, 2 * ri), a0 + sweep, -sweep)
        path.closeSubpath()
        return path

    def _paint_segment(self, p: QPainter, i: int, t: Target, appear: float):
        h = self.hover_amt[i]
        chosen = self.state != self.CHOOSE and self.chosen is t
        dim = self.dim * (0.0 if chosen else 0.65)
        col = QColor(t.color)
        p.save()
        p.setOpacity(p.opacity() * appear * (1 - dim))

        path = self._segment_path(i, R_IN + 6, R_OUT - 6, h)
        base = QColor(255, 255, 255, int(10 + 12 * h))
        p.setBrush(base)
        p.setPen(QPen(QColor(255, 255, 255, int(22 + 40 * h)), 1))
        p.drawPath(path)
        if h > 0.01:
            mid = self.seg_center_angle(i)
            tip = QPointF(self.c.x() + R_OUT * math.cos(math.radians(mid)),
                          self.c.y() - R_OUT * math.sin(math.radians(mid)))
            g = QRadialGradient(tip, R_OUT * 0.95)
            c1 = QColor(col); c1.setAlpha(int(150 * h))
            c2 = QColor(col); c2.setAlpha(int(35 * h))
            g.setColorAt(0.0, c1)
            g.setColorAt(1.0, c2)
            p.setBrush(g)
            p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), int(200 * h)), 1.4))
            p.drawPath(path)

        # подпись: бейдж формата + маленький текст
        mid = math.radians(self.seg_center_angle(i))
        rr = (R_IN + R_OUT) / 2 + 4 + h * 5
        pos = QPointF(self.c.x() + rr * math.cos(mid), self.c.y() - rr * math.sin(mid))
        lift = 3 * h
        f = QFont(self.font())
        f.setPixelSize(20 if len(t.label) <= 4 else 15)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        fm = QFontMetrics(f)
        w = fm.horizontalAdvance(t.label) + 18
        badge = QRectF(pos.x() - w / 2, pos.y() - 22 - lift, w, 30)
        bc = QColor(col); bc.setAlpha(int(55 + 120 * h))
        p.setBrush(bc)
        p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 230), 1.2))
        p.drawRoundedRect(badge, 8, 8)
        p.setPen(QColor(255, 255, 255))
        p.drawText(badge, Qt.AlignCenter, t.label)

        f2 = QFont(self.font())
        f2.setPixelSize(11)
        p.setFont(f2)
        p.setPen(QColor(220, 228, 240, int(150 + 100 * h)))
        p.drawText(QRectF(pos.x() - 60, pos.y() + 11 - lift, 120, 16), Qt.AlignCenter, t.hint)
        p.restore()

    def _paint_highlight_ring(self, p: QPainter):
        """Дуга-«бегунок» на внешнем кольце, плавно перетекающая к сектору под курсором."""
        if self.hl_angle is None:
            return
        amt = max(self.hover_amt) if self.hover_amt else 0
        if amt < 0.01:
            return
        col = QColor(self.targets[self.hover].color if self.hover >= 0 else ACCENT)
        col.setAlpha(int(255 * amt))
        r = R_OUT
        rect = QRectF(self.c.x() - r, self.c.y() - r, 2 * r, 2 * r)
        span = self.step - GAP_DEG * 2
        p.save()
        for width, alpha in ((10, 0.25), (4, 1.0)):
            c = QColor(col); c.setAlphaF(col.alphaF() * alpha)
            pen = QPen(c, width)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, int((self.hl_angle - span / 2) * 16), int(span * 16))
        p.restore()

    def _paint_center(self, p: QPainter):
        c = self.c
        r = R_IN - 2 + 3 * self.center_hover
        g = QRadialGradient(c, r)
        g.setColorAt(0, QColor(36, 44, 60, 250))
        g.setColorAt(1, QColor(18, 22, 32, 250))
        p.setBrush(g)
        p.setPen(QPen(QColor(120, 205, 255, 90 + int(100 * self.center_hover)), 1.4))
        p.drawEllipse(c, r, r)

        if self.state == self.CHOOSE:
            self._paint_file_info(p)
        elif self.state == self.WORKING:
            self._paint_progress(p)
        else:
            self._paint_result(p)

    def _paint_file_info(self, p: QPainter):
        c = self.c
        f0 = self.files[0]
        ext = f0.suffix.lstrip(".").upper()[:5] or "FILE"
        # иконка документа с загнутым уголком
        w, h, fold = 34, 42, 10
        x, y = c.x() - w / 2, c.y() - 50
        doc = QPainterPath()
        doc.moveTo(x, y)
        doc.lineTo(x + w - fold, y)
        doc.lineTo(x + w, y + fold)
        doc.lineTo(x + w, y + h)
        doc.lineTo(x, y + h)
        doc.closeSubpath()
        p.setBrush(QColor(236, 240, 246))
        p.setPen(Qt.NoPen)
        p.drawPath(doc)
        p.setBrush(QColor(190, 198, 210))
        tri = QPainterPath()
        tri.moveTo(x + w - fold, y)
        tri.lineTo(x + w - fold, y + fold)
        tri.lineTo(x + w, y + fold)
        tri.closeSubpath()
        p.drawPath(tri)
        f = QFont(self.font()); f.setPixelSize(9); f.setWeight(QFont.Bold)
        p.setFont(f)
        p.setPen(QColor(90, 100, 118))
        p.drawText(QRectF(x, y + h - 16, w, 14), Qt.AlignCenter, ext)

        # имя файла и размер
        many = len(self.files) > 1
        name = f"{len(self.files)} файл(а)" if many else f0.name
        f = QFont(self.font()); f.setPixelSize(12); f.setWeight(QFont.DemiBold)
        p.setFont(f)
        fm = QFontMetrics(f)
        name = fm.elidedText(name, Qt.ElideMiddle, int(2 * R_IN - 26))
        tw = fm.horizontalAdvance(name) + 12
        pill = QRectF(c.x() - tw / 2, c.y() + 0, tw, 19)
        p.setBrush(QColor(37, 120, 220))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(pill, 5, 5)
        p.setPen(QColor(255, 255, 255))
        p.drawText(pill, Qt.AlignCenter, name)
        try:
            size = sum(f.stat().st_size for f in self.files)
        except OSError:
            size = 0
        f = QFont(self.font()); f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QColor(190, 200, 215))
        sub = f"{human_size(size)} • {ext}" if not many else human_size(size)
        p.drawText(QRectF(c.x() - 60, c.y() + 22, 120, 14), Qt.AlignCenter, sub)
        p.setPen(QColor(150, 160, 178))
        p.drawText(QRectF(c.x() - 70, c.y() + 37, 140, 14), Qt.AlignCenter, "Во что конвертировать?")

    def _paint_progress(self, p: QPainter):
        c = self.c
        r = R_IN - 16
        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        col = QColor(self.chosen.color if self.chosen else ACCENT)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 25), 5))
        p.drawEllipse(rect)
        pen = QPen(col, 5)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        if self.progress < 0:   # неизвестная длительность — крутящаяся дуга
            span = 70 + 50 * math.sin(math.radians(self.spin * 2))
            p.drawArc(rect, int(-self.spin * 16), int(span * 16))
            label = "…"
        else:
            p.drawArc(rect, 90 * 16, int(-360 * 16 * max(0.01, self.progress_shown)))
            label = f"{int(self.progress_shown * 100)}%"
        f = QFont(self.font()); f.setPixelSize(18); f.setWeight(QFont.Bold)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(c.x() - 50, c.y() - 16, 100, 22), Qt.AlignCenter, label)
        f = QFont(self.font()); f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QColor(190, 200, 215))
        p.drawText(QRectF(c.x() - 50, c.y() + 6, 100, 14), Qt.AlignCenter, self.status_text)

    def _paint_result(self, p: QPainter):
        c = self.c
        ok = self.state == self.DONE
        col = QColor("#34D399") if ok else QColor("#FF5A5F")
        t = ease_out_cubic(self.result_t)
        rr = 20 * ease_out_back(min(1.0, self.result_t * 1.3))
        cy = c.y() - 22
        p.setBrush(QColor(col.red(), col.green(), col.blue(), 50))
        p.setPen(QPen(col, 2))
        p.drawEllipse(QPointF(c.x(), cy), rr, rr)
        pen = QPen(QColor(255, 255, 255), 3.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        path = QPainterPath()
        if ok:   # галочка рисуется «пером»
            pts = [QPointF(c.x() - 8, cy + 1), QPointF(c.x() - 2, cy + 7), QPointF(c.x() + 9, cy - 6)]
            path.moveTo(pts[0])
            path.lineTo(pts[1])
            path.lineTo(pts[2])
            p.drawPath(_partial(path, t))
        else:
            d = 6 * t
            p.drawLine(QPointF(c.x() - d, cy - d), QPointF(c.x() + d, cy + d))
            p.drawLine(QPointF(c.x() + d, cy - d), QPointF(c.x() - d, cy + d))

        f = QFont(self.font()); f.setPixelSize(10)
        p.setFont(f)
        p.setPen(QColor(230, 236, 245))
        box = QRectF(c.x() - R_IN + 12, c.y() + 2, 2 * R_IN - 24, 44)
        text = self.status_text if not ok else QFontMetrics(f).elidedText(
            self.status_text, Qt.ElideMiddle, int(box.width()))
        p.drawText(box, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, text)
        if ok:
            p.setPen(QColor(140, 200, 255, int(160 + 95 * self.center_hover)))
            p.drawText(QRectF(c.x() - 60, c.y() + 30, 120, 14), Qt.AlignCenter, "Показать в папке")


def _partial(path: QPainterPath, t: float) -> QPainterPath:
    """Часть пути длиной t (0..1) — для анимации «рисования» галочки."""
    if t >= 1:
        return path
    out = QPainterPath()
    steps = 40
    n = max(1, int(steps * t))
    out.moveTo(path.pointAtPercent(0))
    for k in range(1, n + 1):
        out.lineTo(path.pointAtPercent(min(t, k / steps)))
    return out


def _force_foreground(w: QWidget):
    """Окно фоновой программы иначе может не получить фокус клавиатуры (Esc, цифры)."""
    try:
        if IS_WIN:
            import ctypes
            user32 = ctypes.windll.user32
            hwnd = int(w.winId())
            fg = user32.GetForegroundWindow()
            cur = ctypes.windll.kernel32.GetCurrentThreadId()
            other = user32.GetWindowThreadProcessId(fg, None)
            if other != cur:
                user32.AttachThreadInput(other, cur, True)
                user32.SetForegroundWindow(hwnd)
                user32.AttachThreadInput(other, cur, False)
            else:
                user32.SetForegroundWindow(hwnd)
        elif IS_MAC:
            from AppKit import NSApplication
            NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
    except Exception:
        pass
