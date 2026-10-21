"""Рисует колесо в разных состояниях поверх фона (без экрана) — для визуальной проверки.

    python tests/render_preview.py ФОН.jpg ПАПКА_ВЫВОДА [тема] [путь к файлу/папке]
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPainter, QImage
from PySide6.QtCore import Qt, QPoint
from convwheel.config import CONFIG
from convwheel.wheel import ConvertWheel, SIZE
from convwheel.formats import targets_for

app = QApplication([])
bg_path, out = sys.argv[1], Path(sys.argv[2])
CONFIG.theme = sys.argv[3] if len(sys.argv) > 3 else "citrus"
target = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(__file__).parent / "fixtures" / "Отчёт.docx"
tag = f"{CONFIG.theme}_{'folder' if target.is_dir() else target.suffix[1:]}"

def shot(name, setup):
    w = ConvertWheel([target], targets_for(target)); w.timer.stop()
    setup(w); w.open_p = 1.0
    img = QImage(SIZE, SIZE, QImage.Format_ARGB32_Premultiplied)
    bg = QImage(bg_path).scaled(SIZE * 2, SIZE * 2, Qt.KeepAspectRatioByExpanding)
    p = QPainter(img); p.drawImage(0, 0, bg, 40, 0); p.end()
    p = QPainter(img); w.render(p, QPoint(0, 0), renderFlags=w.RenderFlag.DrawChildren); p.end()
    img.save(str(out / f"wheel_{tag}_{name}.png")); w.deleteLater()

def hover(i):
    def s(w): w.hover = i; w.hover_amt[i] = 1.0; w.hl_angle = w.seg_center_angle(i)
    return s
def working(w):
    hover(0)(w); w.chosen = w.targets[0]; w.state = w.WORKING; w.dim = 1
    w.progress = w.progress_shown = .62; w.status_text = f"В {w.chosen.label}…"
def done(w): working(w); w.state = w.DONE; w.result_t = 1; w.status_text = "Отчёт.pdf"; w.result_paths = ["x"]
def err(w): working(w); w.state = w.ERROR; w.result_t = 1; w.status_text = "В PDF нет текстового слоя — нужен OCR"
for n, f in (("choose", lambda w: None), ("hover", hover(1)), ("working", working), ("done", done), ("error", err)):
    shot(n, f)
print("ok", tag)
