"""Рисует колесо в разных состояниях поверх фона (без экрана) — для визуальной проверки."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QPainter, QImage
from PySide6.QtCore import Qt, QPointF, QPoint
from convwheel.wheel import ConvertWheel, SIZE
from convwheel.formats import targets_for

app = QApplication([])
f = Path(__file__).parent / "fixtures" / (sys.argv[3] if len(sys.argv) > 3 else "Отчёт.docx")
bg_path = sys.argv[1] if len(sys.argv) > 1 else None
out = Path(sys.argv[2] if len(sys.argv) > 2 else ".")
def shot(name, setup):
    w = ConvertWheel([f], targets_for(f)); w.timer.stop()
    setup(w)
    w.open_p = 1.0
    img = QImage(SIZE, SIZE, QImage.Format_ARGB32_Premultiplied)
    if bg_path:
        bg = QImage(bg_path).scaled(SIZE*2, SIZE*2*9//16 + 200, Qt.KeepAspectRatioByExpanding)
        p = QPainter(img); p.drawImage(0, 0, bg, 40, 0); p.end()
    else: img.fill(Qt.darkGray)
    p = QPainter(img); w.render(p, QPoint(0,0), renderFlags=w.RenderFlag.DrawChildren); p.end()
    img.save(str(out / f"wheel_{f.suffix[1:]}_{name}.png")); w.deleteLater()
def hover(i, amt=1.0):
    def s(w):
        w.hover = i; w.hover_amt[i] = amt; w.hl_angle = w.seg_center_angle(i)
    return s
def working(w):
    hover(0)(w); w.chosen = w.targets[0]; w.state = w.WORKING; w.dim = 1; w.progress = .62; w.progress_shown=.62; w.status_text="В PDF…"
def done(w):
    working(w); w.state = w.DONE; w.result_t = 1; w.status_text = "Отчёт.pdf"; w.result_paths=["x"]
def err(w):
    working(w); w.state = w.ERROR; w.result_t = 1; w.status_text = "В PDF нет текстового слоя (это скан) — нужен OCR"
shot("choose", lambda w: None); shot("hover", hover(1)); shot("working", working); shot("done", done); shot("error", err)
print("ok")
