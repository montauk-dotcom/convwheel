"""Действия над папками и архивами."""
import shutil, sys, zipfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from convwheel.formats import targets_for
from convwheel.engine import run_job

FIX = Path(__file__).parent / "fixtures"
W = Path(__file__).parent / "out_folders"; shutil.rmtree(W, ignore_errors=True); W.mkdir()
F = W / "Мои файлы"; F.mkdir(); (F / "вложенная").mkdir()
for n in ("logo.png", "anim.gif", "Отчёт.docx", "readme.md"): shutil.copy(FIX / n, F / n)
(F / "вложенная" / "секрет.txt").write_text("Внутри", encoding="utf-8")
(F / ".DS_Store").write_bytes(b"x")

def show(p):
    if p.is_dir(): return f"папка [{', '.join(sorted(x.name for x in p.rglob('*') if x.is_file()))}]"
    return f"{p.stat().st_size} байт"

print("Папка →", [f"{t.label}:{t.hint}" for t in targets_for(F)])
outs = {}
for t in targets_for(F):
    o = run_job([F], t); outs[t.key] = o[0]; print(f"OK {t.key:7} → {o[0].name}: {show(o[0])}")
print("zip содержит:", sorted(zipfile.ZipFile(outs["zip"]).namelist()))
print("список:", outs["list"].read_text(encoding="utf-8").splitlines()[3:9])
# архивы: распаковать и перепаковать, включая повторную распаковку рядом
for key in ("zip", "7z", "tar.gz"):
    a = outs[key]
    ts = targets_for(a)
    print(f"Архив {a.name} →", [f"{t.label}" for t in ts])
    for t in ts:
        o = run_job([a], t)[0]; print(f"   OK {t.key:7} → {o.name}: {show(o)}")
# zip slip: вредный архив не должен писать за пределы папки
evil = W / "evil.zip"
with zipfile.ZipFile(evil, "w") as z: z.writestr("../../ВЗЛОМ.txt", "x")
try:
    run_job([evil], targets_for(evil)[0]); print("!!! zip slip НЕ остановлен")
except Exception as e: print("zip slip остановлен:", e)
print("ВЗЛОМ существует?", any(Path(__file__).parent.rglob("ВЗЛОМ.txt")))
