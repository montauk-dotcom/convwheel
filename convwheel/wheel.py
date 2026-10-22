"""Радиальное меню конвертации.

Вся анимация идёт от одного таймера с экспоненциальным сглаживанием: значения плавно
«догоняют» цель, поэтому подсветка перетекает между секторами без рывков. Окно
перерисовывается, только пока что-то движется.

Важно про время жизни: колесо само себя НЕ удаляет. В конце анимации оно прячется и
сообщает `closed`, а удаляет его WheelManager через deleteLater(). Пока идёт
конвертация (`busy`), закрыть колесо нельзя ничем, включая Alt+F4 / Cmd+W.
Сама конвертация живёт в менеджере, а не внутри колеса.
"""
from __future__ import annotations

import math
import random
import time
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QConicalGradient, QCursor, QFont, QFontMetrics, QGuiApplication,
                           QImage, QKeyEvent, QMouseEvent, QPainter, QPainterPath, QPainterPathStroker,
                           QPen, QPixmap, QPolygonF, QRadialGradient)
from PySide6.QtWidgets import QWidget

from . import themes
from .config import CONFIG
from .formats import Target
from .platform_utils import IS_MAC, IS_WIN, human_size, reveal_in_file_manager

SIZE = 480
R_OUT = 180.0
R_IN = 76.0
HIT_R = R_OUT + 40          # до этого радиуса клик — по колесу (и выбор сектора, и «не мимо»)
GAP_DEG = 1.6
ACCENT = QColor("#3BB6FF")

# «Цитрус»: корка R_OUT..CIT_PITH, мякоть, дольки CIT_RI..CIT_RO
CIT_PITH = 166.0
CIT_RO = 160.0
CIT_RI = R_IN + 2
CIT_GAP = 7.0
CIT_ROUND = 9.0


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    t = max(0.0, min(1.0, t))
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t), int(a.alpha() + (b.alpha() - a.alpha()) * t))


def _rgba(rgb, a) -> QColor:
    return QColor(rgb[0], rgb[1], rgb[2], max(0, min(255, int(a))))


def ease_out_back(t: float, s: float = 1.45) -> float:
    t -= 1
    return t * t * ((s + 1) * t + s) + 1


def ease_out_cubic(t: float) -> float:
    return 1 - (1 - t) ** 3


def approach(cur: float, target: float, dt: float, speed: float = 16.0) -> float:
    return target + (cur - target) * math.exp(-speed * dt)


class ConvertWheel(QWidget):
    closed = Signal(object)                     # (колесо) — анимация закрытия закончилась
    convert_requested = Signal(object, object)  # (колесо, Target)

    CHOOSE, WORKING, DONE, ERROR = range(4)
    _base_cache: dict = {}                      # (тема, dpr) -> QPixmap статичного фона

    def __init__(self, files: list[Path], targets: list[Target], *, theme: str | None = None,
                 demo: bool = False):
        super().__init__(None)
        self.files = files
        self.targets = targets
        self.demo = demo
        self.n = max(len(targets), 1)
        self.step = 360.0 / self.n
        self.th = themes.get(theme or CONFIG.theme)

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.resize(SIZE, SIZE)
        self._describe()
        rnd = random.Random(11)   # фиксированное зерно — текстура не «мигает» между кадрами
        self._vesicles = [[(rnd.random(), rnd.uniform(-1, 1), rnd.uniform(5, 13), rnd.randint(60, 130),
                            rnd.uniform(0.9, 1.7)) for _ in range(22)] for _ in range(self.n)]

        # --- состояние
        self.state = self.CHOOSE
        self.t_open_start = time.perf_counter()
        self.open_p = 0.0
        self.closing_from: float | None = None
        self._closed_emitted = False
        self.hover = -1
        self.hover_amt = [0.0] * self.n
        self.hl_angle: float | None = None
        self.center_hover = 0.0
        self.dim = 0.0
        self.spin = 0.0
        self.progress = -1.0
        self.progress_shown = 0.0
        self.status_text = ""
        self.result_paths: list[str] = []
        self.chosen: Target | None = None
        self.result_t = 0.0
        self.last_tick = time.perf_counter()
        self._dirty = True

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000 // 120)

        self.autoclose = QTimer(self)
        self.autoclose.setSingleShot(True)
        self.autoclose.timeout.connect(self.dismiss)

    @property
    def busy(self) -> bool:
        return self.state == self.WORKING

    def _describe(self):
        """Подписи в центре считаются один раз (обход большой папки — не на каждом кадре)."""
        from .converters.archive import archive_kind
        from .converters.folder import folder_summary
        f0 = self.files[0]
        many = len(self.files) > 1
        if f0.is_dir():
            self.kind = "folder"
            n, size, cut = folder_summary(f0) if not many else (0, 0, False)
            self.title = f"{len(self.files)} папки" if many else f0.name
            self.subtitle = (f"{n}{'+' if cut else ''} файлов • {human_size(size)}" if not many
                             else "Несколько папок")
            self.question = "Выберите действие"
            self.ext_label = ""
            return
        self.kind = "archive" if archive_kind(f0) else "file"
        k = archive_kind(f0)
        self.ext_label = (k.lstrip(".").upper() if k else f0.suffix.lstrip(".").upper())[:6] or "FILE"
        try:
            size = sum(f.stat().st_size for f in self.files)
        except OSError:
            size = 36_900 if self.demo else 0
        self.title = f"{len(self.files)} файл(а)" if many else f0.name
        self.subtitle = human_size(size) if many else f"{human_size(size)} • {self.ext_label}"
        self.question = "Выберите действие" if self.kind == "archive" else "Выберите формат"

    # ------------------------------------------------------------------ показ / закрытие
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
        """Плавно закрыть. Во время конвертации — ничего не делает."""
        if self.busy or self._closed_emitted:
            return
        if self.closing_from is None:
            self.closing_from = time.perf_counter()
            self.autoclose.stop()

    def _finish_close(self):
        self.timer.stop()
        self.autoclose.stop()
        self.hide()
        if not self._closed_emitted:
            self._closed_emitted = True
            self.closed.emit(self)

    def closeEvent(self, e):
        if self.busy:              # Alt+F4 / Cmd+W посреди конвертации — игнорируем
            e.ignore()
            return
        e.accept()
        self.timer.stop()
        self.autoclose.stop()
        if not self._closed_emitted:
            self._closed_emitted = True
            self.closed.emit(self)

    def contains_global(self, gp) -> bool:
        c = self.mapToGlobal(QPointF(SIZE / 2, SIZE / 2).toPoint())
        return math.hypot(gp.x() - c.x(), gp.y() - c.y()) <= HIT_R

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
        if r < R_IN - 4 or r > HIT_R or not self.targets:
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
        moving = self._dirty
        self._dirty = False

        if self.closing_from is not None:
            if self.busy:                    # конвертацию начали после команды «закрыть»
                self.closing_from = None
            else:
                k = min((now - self.closing_from) / 0.16, 1.0)
                self.open_p = 1.0 - ease_out_cubic(k)
                self.update()
                if k >= 1.0:
                    self._finish_close()
                return
        if self.open_p < 1.0:
            self.open_p = min((now - self.t_open_start) / 0.30, 1.0)
            moving = True

        for i in range(self.n):
            old = self.hover_amt[i]
            self.hover_amt[i] = approach(old, 1.0 if i == self.hover else 0.0, dt, 18)
            moving |= abs(self.hover_amt[i] - old) > 1e-3
        if self.hover >= 0:
            target = self.seg_center_angle(self.hover)
            if self.hl_angle is None:
                self.hl_angle = target
            else:  # кратчайший путь по окружности
                diff = (target - self.hl_angle + 180) % 360 - 180
                if abs(diff) > 0.05:
                    self.hl_angle += diff * (1 - math.exp(-20 * dt))
                    moving = True

        hovering_center = self.state in (self.DONE, self.ERROR) and self.in_center(
            QPointF(self.mapFromGlobal(QCursor.pos())))
        old = self.center_hover
        self.center_hover = approach(old, 1.0 if hovering_center else 0.0, dt, 14)
        moving |= abs(self.center_hover - old) > 1e-3
        old = self.dim
        self.dim = approach(old, 1.0 if self.state != self.CHOOSE else 0.0, dt, 10)
        moving |= abs(self.dim - old) > 1e-3
        if self.busy:
            self.spin = (self.spin + dt * 300) % 360
            moving = True
        if self.progress >= 0 and abs(self.progress_shown - self.progress) > 1e-3:
            self.progress_shown = approach(self.progress_shown, self.progress, dt, 9)
            moving = True
        if self.state in (self.DONE, self.ERROR):
            if self.result_t < 1.0:
                self.result_t = min(self.result_t + dt / 0.45, 1.0)
                moving = True
            inside = self.contains_global(QCursor.pos())   # не закрываемся, пока курсор над колесом
            if inside and self.autoclose.isActive():
                self.autoclose.stop()
            elif not inside and not self.autoclose.isActive():
                self.autoclose.start(2600 if self.state == self.DONE else 6000)
        if moving:
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
            else:
                self.dismiss()
        elif self.state == self.DONE:
            if self.in_center(p) and self.result_paths and not self.demo:
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
        elif self.state == self.DONE and k in (Qt.Key_Return, Qt.Key_Enter):
            if self.result_paths and not self.demo:
                reveal_in_file_manager(self.result_paths[0])
            self.dismiss()

    def changeEvent(self, e):
        # клик в другое место (окно потеряло активность) — закрываемся
        if e.type() == e.Type.ActivationChange and not self.isActiveWindow() and self.state == self.CHOOSE:
            if self.isVisible() and not self.contains_global(QCursor.pos()):
                self.dismiss()
        super().changeEvent(e)

    # ------------------------------------------------------------------ конвертация
    def start(self, i: int):
        if self.state != self.CHOOSE or not (0 <= i < len(self.targets)):
            return
        self.chosen = self.targets[i]
        self.hover = i
        self.state = self.WORKING
        self.closing_from = None       # если «закрыть» пришло одновременно с выбором — выбор важнее
        self.open_p = 1.0
        self.autoclose.stop()
        self.status_text = f"В {self.chosen.label}…"
        self.setCursor(Qt.BusyCursor)
        if self.demo:
            self._demo_t = 0.0
            self.progress = 0.0
            self._demo_timer = QTimer(self)
            self._demo_timer.timeout.connect(self._demo_step)
            self._demo_timer.start(40)
        else:
            self.convert_requested.emit(self, self.chosen)

    def _demo_step(self):
        self._demo_t += 0.04
        self.set_progress(min(self._demo_t / 1.4, 1.0))
        if self._demo_t >= 1.5:
            self._demo_timer.stop()
            ext = self.chosen.key if self.chosen.key.isalnum() else "pdf"
            self.finish_ok([f"{Path(self.title).stem}.{ext}"])

    def set_progress(self, p: float, _name: str = ""):
        self.progress = p
        self._dirty = True

    def finish_ok(self, outs: list):
        self.result_paths = list(outs)
        self.progress = 1.0
        self.state = self.DONE
        self.status_text = Path(outs[0]).name if len(outs) == 1 else f"Готово: {len(outs)} файл(а)"
        self.result_t = 0.0
        self.setCursor(Qt.ArrowCursor)
        self._dirty = True

    def finish_fail(self, msg: str):
        self.state = self.ERROR
        self.status_text = msg
        self.result_t = 0.0
        self.setCursor(Qt.ArrowCursor)
        self._dirty = True

    # ================================================================ отрисовка
    def paintEvent(self, _):
        p = QPainter(self)
        self.paint_into(p)
        p.end()

    def paint_into(self, p: QPainter):
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        op = self.open_p
        appear = ease_out_back(op) if self.closing_from is None else op
        p.setOpacity(min(1.0, op * 1.6))
        p.translate(self.c)
        sc = 0.55 + 0.45 * appear
        p.scale(sc, sc)
        p.rotate(-14 * (1 - appear))            # лёгкое «докручивание» при появлении
        p.translate(-self.c)

        style = self.th.style
        p.drawPixmap(0, 0, self._base_pixmap(p))
        seg = getattr(self, f"_seg_{style}")
        for i, t in enumerate(self.targets):
            # каскад: каждый следующий сектор появляется чуть позже
            local = max(0.0, min(1.0, (op * 1.5) - i * 0.05)) if self.closing_from is None else 1.0
            p.save()
            p.setOpacity(p.opacity() * local * self._segment_alpha(t))
            seg(p, i, t)
            p.restore()
        self._paint_highlight_ring(p)
        self._paint_center(p)

    # ---------------------------------------------------------------- фон (кэшируется)
    def _base_pixmap(self, p: QPainter) -> QPixmap:
        dpr = max(1.0, float(self.devicePixelRatioF()) if self.isVisible() else 2.0)
        key = (self.th.key, round(dpr, 2))
        pm = ConvertWheel._base_cache.get(key)
        if pm is None:
            pm = QPixmap(int(SIZE * dpr), int(SIZE * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            q = QPainter(pm)
            q.setRenderHint(QPainter.Antialiasing)
            getattr(self, f"_base_{self.th.style}")(q)
            q.end()
            ConvertWheel._base_cache[key] = pm
        return pm

    def _base_neon(self, p: QPainter):
        c, x = self.c, self.th.x
        for k, a in ((22, 18), (14, 28), (7, 45)):      # мягкое свечение
            p.setPen(QPen(_rgba(x["glow"], a), k))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(c, R_OUT + 2, R_OUT + 2)
        g = QRadialGradient(c, R_OUT)
        for pos, col in zip((0.0, 0.7, 1.0), x["bg"]):
            g.setColorAt(pos, col)
        p.setBrush(g)
        p.setPen(QPen(x["rim"], 2.2))
        p.drawEllipse(c, R_OUT, R_OUT)

    def _base_citrus(self, p: QPainter):
        c, x = self.c, self.th.x
        sh = QRadialGradient(QPointF(c.x(), c.y() + 8), R_OUT + 18)   # тень под долькой
        sh.setColorAt(0.86, QColor(0, 0, 0, 70))
        sh.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(sh)
        p.drawEllipse(QPointF(c.x(), c.y() + 8), R_OUT + 18, R_OUT + 18)
        g = QRadialGradient(c, R_OUT)                                 # корка
        g.setColorAt(CIT_PITH / R_OUT, x["rind"][0])
        g.setColorAt(0.97, x["rind"][1])
        g.setColorAt(1.0, x["rind"][2])
        p.setBrush(g)
        p.setPen(QPen(x["rind_edge"], 1.6))
        p.drawEllipse(c, R_OUT, R_OUT)
        rnd = random.Random(7)                                        # поры на корке
        light, dark = x["pores"]
        p.setPen(Qt.NoPen)
        for _ in range(150):
            ang, rr = rnd.uniform(0, 2 * math.pi), rnd.uniform(CIT_PITH + 3, R_OUT - 3)
            s, kind = rnd.uniform(0.6, 1.4), rnd.choice((0, 0, 1, 1, 2))
            p.setBrush(_rgba(light, 45 + 20 * kind) if kind else _rgba(dark, 26))
            p.drawEllipse(QPointF(c.x() + rr * math.cos(ang), c.y() - rr * math.sin(ang)), s, s)
        g2 = QRadialGradient(c, CIT_PITH)                             # белая мякоть
        g2.setColorAt(0.0, x["pith"][0])
        g2.setColorAt(0.92, x["pith"][1])
        g2.setColorAt(1.0, x["pith"][2])
        p.setBrush(g2)
        p.setPen(QPen(QColor(0, 0, 0, 25), 1))
        p.drawEllipse(c, CIT_PITH, CIT_PITH)

    def _base_glass(self, p: QPainter):
        pass   # у «стекла» нет общего диска — только отдельные плитки

    def _base_vinyl(self, p: QPainter):
        c, x = self.c, self.th.x
        sh = QRadialGradient(QPointF(c.x(), c.y() + 7), R_OUT + 16)
        sh.setColorAt(0.88, QColor(0, 0, 0, 90))
        sh.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.NoPen)
        p.setBrush(sh)
        p.drawEllipse(QPointF(c.x(), c.y() + 7), R_OUT + 16, R_OUT + 16)
        g = QRadialGradient(c, R_OUT)
        g.setColorAt(0.0, x["disc"][0])
        g.setColorAt(0.75, x["disc"][1])
        g.setColorAt(1.0, x["disc"][2])
        p.setBrush(g)
        p.setPen(QPen(QColor(255, 255, 255, 34), 1.2))
        p.drawEllipse(c, R_OUT, R_OUT)
        p.setBrush(Qt.NoBrush)                                        # дорожки
        r, k = R_IN + 8, 0
        while r < R_OUT - 4:
            a = x["groove"].alpha() * (1.7 if k % 7 == 0 else 1.0)
            p.setPen(QPen(QColor(255, 255, 255, int(a)), 0.8))
            p.drawEllipse(c, r, r)
            r += 2.6
            k += 1
        for gap_r in (R_IN + 34, R_OUT - 34):                         # паузы между треками
            p.setPen(QPen(QColor(0, 0, 0, 120), 2.4))
            p.drawEllipse(c, gap_r, gap_r)
        sheen = QConicalGradient(c, 45)                               # блики
        clear, s = QColor(255, 255, 255, 0), x["sheen"]
        for pos, col in ((0.0, s), (0.09, clear), (0.41, clear), (0.5, s), (0.59, clear), (0.91, clear),
                         (1.0, s)):
            sheen.setColorAt(pos, col)
        ring = QPainterPath()
        ring.addEllipse(c, R_OUT - 1, R_OUT - 1)
        hole = QPainterPath()
        hole.addEllipse(c, R_IN + 2, R_IN + 2)
        p.fillPath(ring.subtracted(hole), sheen)

    # ---------------------------------------------------------------- сектора
    def _segment_alpha(self, t: Target) -> float:
        chosen = self.state != self.CHOOSE and self.chosen is t
        return 1 - self.dim * (0.0 if chosen else 0.6)

    def _ring_segment(self, i: int, r_in: float, r_out: float, grow: float = 0.0) -> QPainterPath:
        mid = self.seg_center_angle(i)
        half = (self.step - GAP_DEG) / 2
        a0, sweep = mid + half, -(2 * half)
        off = grow * 7                       # «выдвигаем» сектор наружу при наведении
        cx = self.c.x() + off * math.cos(math.radians(mid))
        cy = self.c.y() - off * math.sin(math.radians(mid))
        ro, ri = r_out + grow * 4, r_in
        path = QPainterPath()
        path.arcMoveTo(QRectF(cx - ro, cy - ro, 2 * ro, 2 * ro), a0)
        path.arcTo(QRectF(cx - ro, cy - ro, 2 * ro, 2 * ro), a0, sweep)
        path.arcTo(QRectF(cx - ri, cy - ri, 2 * ri, 2 * ri), a0 + sweep, -sweep)
        path.closeSubpath()
        return path

    def _wedge(self, i: int, ri: float, ro: float, gap: float, rnd: float,
               grow: float, push: float = 6) -> tuple[QPainterPath, QPointF]:
        """Долька/плитка со скруглёнными углами: многоугольник, «раздутый» круглой обводкой."""
        mid = self.seg_center_angle(i)
        off = grow * push
        cx = self.c.x() + off * math.cos(math.radians(mid))
        cy = self.c.y() - off * math.sin(math.radians(mid))
        ri, ro = ri + rnd, ro + grow * 3 - rnd
        half = self.step / 2
        ho = half - math.degrees((gap / 2 + rnd) / ro)
        hi = max(0.8, half - math.degrees((gap / 2 + rnd) / ri))

        def pt(rad, a):
            return QPointF(cx + rad * math.cos(math.radians(a)), cy - rad * math.sin(math.radians(a)))

        n = max(8, int(self.step / 2))
        pts = [pt(ro, mid + ho - 2 * ho * k / n) for k in range(n + 1)]
        m = max(3, n // 3)
        pts += [pt(ri, mid - hi + 2 * hi * k / m) for k in range(m + 1)]
        poly = QPainterPath()
        poly.addPolygon(QPolygonF(pts))
        poly.closeSubpath()
        st = QPainterPathStroker()
        st.setWidth(2 * rnd)
        st.setJoinStyle(Qt.RoundJoin)
        st.setCapStyle(Qt.RoundCap)
        return st.createStroke(poly).united(poly).simplified(), QPointF(cx, cy)

    def _seg_neon(self, p: QPainter, i: int, t: Target):
        h = self.hover_amt[i]
        col = self._neon_color(i, t)
        path = self._ring_segment(i, R_IN + 6, R_OUT - 6, h)
        p.setBrush(QColor(255, 255, 255, int(10 + 12 * h)))
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
        pos, lift = self._label_pos(i, (R_IN + R_OUT) / 2 + 4, h, t, R_OUT - 14)
        f = self._label_font(t)
        p.setFont(f)
        w = QFontMetrics(f).horizontalAdvance(t.label) + 18
        badge = QRectF(pos.x() - w / 2, pos.y() - 22 - lift, w, 30)
        bc = QColor(col); bc.setAlpha(int(55 + 120 * h))
        p.setBrush(bc)
        p.setPen(QPen(QColor(col.red(), col.green(), col.blue(), 230), 1.2))
        p.drawRoundedRect(badge, 8, 8)
        p.setPen(QColor(255, 255, 255))
        p.drawText(badge, Qt.AlignCenter, t.label)
        self._paint_hint(p, t, pos, lift, QColor(220, 228, 240, int(150 + 100 * h)))

    def _neon_color(self, i: int, t: Target) -> QColor:
        badges = self.th.x.get("badges")
        return QColor(badges[i % len(badges)] if badges else t.color)

    def _seg_citrus(self, p: QPainter, i: int, t: Target):
        h, x = self.hover_amt[i], self.th.x
        path, wc = self._wedge(i, CIT_RI, CIT_RO, CIT_GAP, CIT_ROUND, h)
        mid = math.radians(self.seg_center_angle(i))
        if h > 0.01:                    # «приподнятая» долька отбрасывает тень
            p.save()
            p.translate(0, 4 * h)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, int(60 * h)))
            p.drawPath(path)
            p.restore()
        g = QRadialGradient(wc, CIT_RO + 6)
        g.setColorAt(CIT_RI / CIT_RO, _mix(x["wedge"][0], x["wedge_h"][0], h))
        g.setColorAt(1.0, _mix(x["wedge"][1], x["wedge_h"][1], h))
        p.setBrush(g)
        p.setPen(QPen(_mix(x["edge"], x["edge_h"], h), 1.4 + 0.8 * h))
        p.drawPath(path)
        p.save()                         # «сочные» волокна
        p.setClipPath(path)
        for fr, fa, ln, a, w in self._vesicles[i]:
            rad = CIT_RI + 10 + fr * (CIT_RO - CIT_RI - 18)
            ang = mid + fa * math.radians(self.step / 2 - 3) * (0.35 + 0.65 * fr)
            px, py = wc.x() + rad * math.cos(ang), wc.y() - rad * math.sin(ang)
            dx, dy = math.cos(ang) * ln / 2, -math.sin(ang) * ln / 2
            pen = QPen(_rgba(x["vesicle"], a * (0.75 + 0.25 * h)), w)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QPointF(px - dx, py - dy), QPointF(px + dx, py + dy))
        hl = QRadialGradient(wc, CIT_RO)  # блик по внешнему краю
        hl.setColorAt(0.80, QColor(255, 255, 255, 0))
        hl.setColorAt(0.97, QColor(255, 255, 255, int(55 + 50 * h)))
        hl.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, hl)
        p.restore()
        pos, lift = self._label_pos(i, (CIT_RI + CIT_RO) / 2 + 6, h, t, CIT_RO - 10)
        self._paint_label(p, t, pos, lift, _mix(x["label"], x["label_h"], h), _rgba(x["glow"], x["glow"][3]))
        self._paint_hint(p, t, pos, lift, _mix(x["hint"], x["hint_h"], h))

    def _seg_glass(self, p: QPainter, i: int, t: Target):
        h, x = self.hover_amt[i], self.th.x
        path, _ = self._wedge(i, R_IN + 6, R_OUT - 4, 9, 13, h, push=7)
        p.save()
        p.setPen(Qt.NoPen)
        for dy, a in ((5 + 4 * h, 0.35), (2, 0.55)):     # мягкая тень
            p.save()
            p.translate(0, dy)
            p.setBrush(QColor(0, 0, 0, int(x["shadow"] * a * (1 + 0.6 * h))))
            p.drawPath(path)
            p.restore()
        p.restore()
        p.setBrush(_mix(x["tile"], x["tile_h"], h))
        p.setPen(QPen(_mix(x["tile_edge"], x["tile_h_edge"], h), 1.0))
        p.drawPath(path)
        top = QRadialGradient(QPointF(self.c.x(), self.c.y() - R_OUT), R_OUT * 2)   # стеклянный отлив
        top.setColorAt(0.0, QColor(255, 255, 255, int(70 * (1 - h))))
        top.setColorAt(0.6, QColor(255, 255, 255, 0))
        p.fillPath(path, top)
        pos, lift = self._label_pos(i, (R_IN + R_OUT) / 2 + 4, h, t, R_OUT - 16)
        self._paint_label(p, t, pos, lift, _mix(x["label"], x["label_h"], h), None)
        self._paint_hint(p, t, pos, lift, _mix(x["hint"], x["hint_h"], h))

    def _seg_vinyl(self, p: QPainter, i: int, t: Target):
        h, x = self.hover_amt[i], self.th.x
        if h > 0.01:
            path = self._ring_segment(i, R_IN + 4, R_OUT - 3, 0)
            p.fillPath(path, QColor(x["hover"].red(), x["hover"].green(), x["hover"].blue(),
                                    int(x["hover"].alpha() * h)))
        a = math.radians(self.seg_center_angle(i) + self.step / 2)          # разделитель
        p.setPen(QPen(x["sep"], 1))
        p.drawLine(QPointF(self.c.x() + (R_IN + 6) * math.cos(a), self.c.y() - (R_IN + 6) * math.sin(a)),
                   QPointF(self.c.x() + (R_OUT - 6) * math.cos(a), self.c.y() - (R_OUT - 6) * math.sin(a)))
        pos, lift = self._label_pos(i, (R_IN + R_OUT) / 2 + 4, h, t, R_OUT - 14)
        self._paint_label(p, t, pos, lift, _mix(x["label"], x["label_h"], h), None)
        self._paint_hint(p, t, pos, lift, _mix(x["hint"], x["hint_h"], h))

    # ---------------------------------------------------------------- подписи
    def _label_pos(self, i: int, rr: float, h: float, t: Target | None = None,
                   r_max: float = 0.0) -> tuple[QPointF, float]:
        mid = math.radians(self.seg_center_angle(i))
        if t is not None and r_max:
            # широкие подписи на боковых секторах сдвигаем к центру, чтобы не залезали на край
            half_w = max(QFontMetrics(self._label_font(t)).horizontalAdvance(t.label),
                         QFontMetrics(self._hint_font(t)).horizontalAdvance(t.hint)) / 2 + 4
            cos = abs(math.cos(mid))
            if cos > 0.05:
                rr = min(rr, (r_max - half_w) / cos)
            rr = max(rr, R_IN + 30)
        rr += h * 5
        return QPointF(self.c.x() + rr * math.cos(mid), self.c.y() - rr * math.sin(mid)), 3 * h

    def _label_font(self, t: Target) -> QFont:
        f = QFont(self.font())
        f.setPixelSize(20 if len(t.label) <= 4 else 15)
        f.setWeight(QFont.Bold)
        return f

    def _hint_font(self, t: Target) -> QFont:
        f2 = QFont(self.font())
        f2.setPixelSize(11)
        if self.th.style != "neon":
            f2.setWeight(QFont.Medium)
            f2.setPixelSize(10 if len(t.hint) > 14 else 11)
        return f2

    def _paint_label(self, p: QPainter, t: Target, pos: QPointF, lift: float, col: QColor,
                     glow: QColor | None):
        p.setFont(self._label_font(t))
        box = QRectF(pos.x() - 70, pos.y() - 24 - lift, 140, 30)
        if glow is not None:              # светлая «подложка» для чёткости на текстуре
            p.setPen(glow)
            p.drawText(box.translated(0, 1), Qt.AlignCenter, t.label)
        p.setPen(col)
        p.drawText(box, Qt.AlignCenter, t.label)

    def _paint_hint(self, p: QPainter, t: Target, pos: QPointF, lift: float, col: QColor):
        p.setFont(self._hint_font(t))
        p.setPen(col)
        p.drawText(QRectF(pos.x() - 62, pos.y() + 11 - lift, 124, 16), Qt.AlignCenter, t.hint)

    def _paint_highlight_ring(self, p: QPainter):
        """Дуга-«бегунок» по краю, плавно перетекающая к сектору под курсором."""
        style = self.th.style
        if self.hl_angle is None or style == "glass":
            return
        amt = max(self.hover_amt) if self.hover_amt else 0
        if amt < 0.01:
            return
        span = self.step - GAP_DEG * 2
        if style == "citrus":
            col = QColor(255, 255, 255, int(200 * amt))
            r, layers = (R_OUT + CIT_PITH) / 2, ((9, 0.22), (4, 1.0))
            span -= 6
        elif style == "vinyl":
            col = QColor(self.th.x["ring"])
            col.setAlpha(int(255 * amt))
            r, layers = R_OUT - 3, ((8, 0.25), (3, 1.0))
            span -= 4
        else:
            hv = self.hover if self.hover >= 0 else 0
            col = self._neon_color(hv, self.targets[hv]) if self.targets else QColor(ACCENT)
            col.setAlpha(int(255 * amt))
            r, layers = R_OUT, ((10, 0.25), (4, 1.0))
        rect = QRectF(self.c.x() - r, self.c.y() - r, 2 * r, 2 * r)
        p.save()
        for width, alpha in layers:
            c = QColor(col); c.setAlphaF(col.alphaF() * alpha)
            pen = QPen(c, width)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, int((self.hl_angle - span / 2) * 16), int(span * 16))
        p.restore()

    # ---------------------------------------------------------------- центр
    def _paint_center(self, p: QPainter):
        c, th = self.c, self.th
        r = R_IN - 2 + 3 * self.center_hover
        if th.style == "glass":
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, int(th.x["shadow"] * 0.5)))
            p.drawEllipse(QPointF(c.x(), c.y() + 3), r, r)
        g = QRadialGradient(c, r)
        g.setColorAt(0, th.center0)
        g.setColorAt(1, th.center1)
        p.setBrush(g)
        border = QColor(th.border)
        border.setAlpha(min(255, border.alpha() + int(90 * self.center_hover)))
        p.setPen(QPen(border, 1.4))
        p.drawEllipse(c, r, r)
        if th.style == "vinyl":          # как у настоящей пластинки — тонкое кольцо по краю наклейки
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(0, 0, 0, 40), 1))
            p.drawEllipse(c, r - 6, r - 6)

        if self.state == self.CHOOSE:
            self._paint_file_info(p)
        elif self.state == self.WORKING:
            self._paint_progress(p)
        else:
            self._paint_result(p)

    def _paint_file_info(self, p: QPainter):
        c, th = self.c, self.th
        icon_top = c.y() - 50
        if self.kind == "folder":
            self._paint_folder_icon(p, QRectF(c.x() - 22, icon_top + 4, 44, 36))
        else:
            w, h, fold = 34, 42, 10
            x, y = c.x() - w / 2, icon_top
            doc = QPainterPath()
            doc.moveTo(x, y)
            doc.lineTo(x + w - fold, y)
            doc.lineTo(x + w, y + fold)
            doc.lineTo(x + w, y + h)
            doc.lineTo(x, y + h)
            doc.closeSubpath()
            p.setBrush(th.doc)
            p.setPen(QPen(th.doc_edge, 1) if th.style != "neon" else Qt.NoPen)
            p.drawPath(doc)
            p.setBrush(th.doc_fold)
            tri = QPainterPath()
            tri.moveTo(x + w - fold, y)
            tri.lineTo(x + w - fold, y + fold)
            tri.lineTo(x + w, y + fold)
            tri.closeSubpath()
            p.drawPath(tri)
            f = QFont(self.font()); f.setPixelSize(9); f.setWeight(QFont.Bold)
            p.setFont(f)
            p.setPen(th.doc_text)
            p.drawText(QRectF(x - 4, y + h - 16, w + 8, 14), Qt.AlignCenter, self.ext_label)

        f = QFont(self.font()); f.setPixelSize(12); f.setWeight(QFont.DemiBold)
        p.setFont(f)
        fm = QFontMetrics(f)
        name = fm.elidedText(self.title, Qt.ElideMiddle, int(2 * R_IN - 26))
        tw = fm.horizontalAdvance(name) + 12
        pill = QRectF(c.x() - tw / 2, c.y() + 0, tw, 19)
        p.setBrush(th.pill)
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(pill, 5, 5)
        p.setPen(th.pill_text)
        p.drawText(pill, Qt.AlignCenter, name)
        f = QFont(self.font()); f.setPixelSize(10)
        p.setFont(f)
        p.setPen(th.text_sub)
        p.drawText(QRectF(c.x() - 66, c.y() + 21, 132, 14), Qt.AlignCenter, self.subtitle)
        p.setPen(th.text_muted)
        p.drawText(QRectF(c.x() - 60, c.y() + 34, 120, 14), Qt.AlignCenter, self.question)

    def _paint_folder_icon(self, p: QPainter, r: QRectF):
        th = self.th
        tab = QPainterPath()
        tab.addRoundedRect(QRectF(r.x(), r.y(), r.width() * 0.45, r.height() * 0.4), 4, 4)
        p.setPen(Qt.NoPen)
        p.setBrush(th.folder_back)
        p.drawPath(tab)
        p.drawRoundedRect(QRectF(r.x(), r.y() + r.height() * 0.15, r.width(), r.height() * 0.85), 5, 5)
        p.setBrush(th.folder_front)
        p.drawRoundedRect(QRectF(r.x(), r.y() + r.height() * 0.32, r.width(), r.height() * 0.68), 5, 5)

    def _paint_progress(self, p: QPainter):
        c, th = self.c, self.th
        r = R_IN - 16
        rect = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        if th.style == "neon" and not th.x.get("badges") and self.chosen:
            col = QColor(self.chosen.color)
        else:
            col = th.accent
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(th.track, 5))
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
        p.setPen(th.text)
        p.drawText(QRectF(c.x() - 50, c.y() - 16, 100, 22), Qt.AlignCenter, label)
        f = QFont(self.font()); f.setPixelSize(10)
        p.setFont(f)
        p.setPen(th.text_sub)
        p.drawText(QRectF(c.x() - 50, c.y() + 6, 100, 14), Qt.AlignCenter, self.status_text)

    def _paint_result(self, p: QPainter):
        c, th = self.c, self.th
        ok = self.state == self.DONE
        col = th.ok if ok else th.err
        t = ease_out_cubic(self.result_t)
        rr = 20 * ease_out_back(min(1.0, self.result_t * 1.3))
        cy = c.y() - 22
        fill = QColor(col)
        fill.setAlpha(50 if th.style == "neon" else 255)
        p.setBrush(fill)
        p.setPen(QPen(col, 2))
        p.drawEllipse(QPointF(c.x(), cy), rr, rr)
        pen = QPen(th.ok_mark if (ok and th.style != "neon") else QColor(255, 255, 255), 3.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        if ok:   # галочка рисуется «пером»
            path = QPainterPath()
            path.moveTo(QPointF(c.x() - 8, cy + 1))
            path.lineTo(QPointF(c.x() - 2, cy + 7))
            path.lineTo(QPointF(c.x() + 9, cy - 6))
            p.drawPath(_partial(path, t))
        else:
            d = 6 * t
            p.drawLine(QPointF(c.x() - d, cy - d), QPointF(c.x() + d, cy + d))
            p.drawLine(QPointF(c.x() + d, cy - d), QPointF(c.x() - d, cy + d))
        f = QFont(self.font()); f.setPixelSize(10)
        p.setFont(f)
        p.setPen(th.text)
        box = QRectF(c.x() - R_IN + 12, c.y() + 2, 2 * R_IN - 24, 44)
        text = self.status_text if not ok else QFontMetrics(f).elidedText(
            self.status_text, Qt.ElideMiddle, int(box.width()))
        p.drawText(box, Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap, text)
        if ok and not self.demo:
            link = QColor(th.link)
            link.setAlpha(int(170 + 85 * self.center_hover))
            p.setPen(link)
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


# ---------------------------------------------------------------- превью для окна «Вид»
SAMPLE_FILE = Path("Отчёт.docx")


def sample_targets() -> list[Target]:
    from .formats import targets_for
    return targets_for(SAMPLE_FILE)


def render_preview(theme_key: str, px: int, dpr: float = 2.0, hover: int = 1, state: str = "choose") -> QPixmap:
    """Колесо выбранного вида как картинка (без окна) — для карточек выбора вида."""
    w = ConvertWheel([SAMPLE_FILE], sample_targets(), theme=theme_key, demo=True)
    w.timer.stop()
    w.open_p = 1.0
    if hover >= 0:
        w.hover = hover
        w.hover_amt[hover] = 1.0
        w.hl_angle = w.seg_center_angle(hover)
    if state == "working":
        w.hover_amt = [0.0] * w.n
        w.hover, w.hover_amt[0], w.hl_angle = 0, 1.0, w.seg_center_angle(0)
        w.chosen, w.state, w.dim = w.targets[0], w.WORKING, 1.0
        w.progress = w.progress_shown = 0.62
        w.status_text = "В PDF…"
    img = QImage(int(SIZE * dpr), int(SIZE * dpr), QImage.Format_ARGB32_Premultiplied)
    img.setDevicePixelRatio(dpr)
    img.fill(Qt.transparent)
    p = QPainter(img)
    w.paint_into(p)
    p.end()
    w.deleteLater()
    out = QPixmap.fromImage(img.scaled(int(px * dpr), int(px * dpr), Qt.KeepAspectRatio,
                                       Qt.SmoothTransformation))
    out.setDevicePixelRatio(dpr)
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
