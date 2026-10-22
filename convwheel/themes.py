"""Виды колеса. Каждый вид — это стиль отрисовки (citrus / neon / glass / vinyl) и набор цветов.

Чтобы добавить вид, допишите ещё один Theme(...) в THEMES — больше ничего менять не нужно.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtGui import QColor

DEFAULT_THEME = "citrus"
LEGACY = {"classic": "neon"}          # старое имя из версии 1.1


def Q(*a) -> QColor:
    return QColor(*a)


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    style: str                    # citrus | neon | glass | vinyl
    # центр колеса
    center0: QColor
    center1: QColor
    border: QColor
    text: QColor
    text_sub: QColor
    text_muted: QColor
    pill: QColor
    pill_text: QColor
    doc: QColor
    doc_edge: QColor
    doc_fold: QColor
    doc_text: QColor
    folder_back: QColor
    folder_front: QColor
    accent: QColor                # кольцо прогресса
    track: QColor
    ok: QColor
    ok_mark: QColor               # цвет галочки
    err: QColor
    link: QColor
    # параметры конкретного стиля
    x: dict = field(default_factory=dict)

    @property
    def citrus(self) -> bool:
        return self.style == "citrus"


def _citrus(key, name, *, rind, rind_edge, pores, pith, wedge, wedge_h, edge, edge_h, vesicle,
            label, label_h, glow, hint, hint_h, center, border, text, sub, muted, pill, accent,
            link, doc_edge, doc_fold, doc_text, folder, err="#B3261E", seeds=None, pores_n=150,
            label_shadow=None) -> Theme:
    return Theme(
        key, name, "citrus", Q(center[0]), Q(center[1]), border, Q(text), Q(sub), Q(muted), Q(pill),
        Q("#FFFFFF"), Q("#FFFFFF"), Q(doc_edge), Q(doc_fold), Q(doc_text), Q(folder[0]), Q(folder[1]),
        Q(accent), Q(0, 0, 0, 28), Q(accent), Q("#FFFFFF"), Q(err), Q(link),
        dict(rind=[Q(c) for c in rind], rind_edge=Q(rind_edge), pores=pores, pith=[Q(c) for c in pith],
             wedge=[Q(c) for c in wedge], wedge_h=[Q(c) for c in wedge_h], edge=Q(edge), edge_h=Q(edge_h),
             vesicle=vesicle, label=Q(label), label_h=Q(label_h), glow=glow, hint=Q(hint),
             hint_h=Q(hint_h), ring=Q(255, 255, 255), seeds=seeds, pores_n=pores_n,
             label_shadow=label_shadow))


def _mk(key, name, style, *, center, border, text, sub, muted, pill, pill_text="#FFFFFF",
        doc="#FFFFFF", doc_edge, doc_fold, doc_text, folder, accent, track=(0, 0, 0, 40), ok=None,
        ok_mark="#FFFFFF", err="#B3261E", link=None, **x) -> Theme:
    """Короткая запись вида: цвета центра + параметры стиля (x)."""
    def c(v):
        return v if isinstance(v, QColor) else (Q(*v) if isinstance(v, tuple) else Q(v))
    return Theme(key, name, style, c(center[0]), c(center[1]), c(border), c(text), c(sub), c(muted),
                 c(pill), c(pill_text), c(doc), c(doc_edge), c(doc_fold), c(doc_text), c(folder[0]),
                 c(folder[1]), c(accent), c(track), c(ok or accent), c(ok_mark), c(err), c(link or accent),
                 {k: (c(v) if isinstance(v, (str, tuple)) and k not in ("seeds_zone",) else v)
                  for k, v in x.items()})


THEMES: dict[str, Theme] = {}


def _add(t: Theme):
    THEMES[t.key] = t


# ---------------------------------------------------------------- цитрусовые
_add(_citrus(
    "citrus", "Цитрус",
    rind=("#B9B9B7", "#8E8E8C", "#777775"), rind_edge="#6A6A68",
    pores=((255, 255, 255), (0, 0, 0)), pith=("#F4F4F2", "#E6E6E3", "#D4D4D1"),
    wedge=("#9C9C9A", "#B4B4B2"), wedge_h=("#D2D2D0", "#F0F0EE"), edge="#8A8A88", edge_h="#FFFFFF",
    vesicle=(255, 255, 255), label="#2E2E2D", label_h="#161616", glow=(255, 255, 255, 110),
    hint="#4A4A48", hint_h="#2E2E2D", center=("#F7F7F5", "#E2E2DF"), border=Q(0, 0, 0, 40),
    text="#2A2A29", sub="#5C5C5A", muted="#80807E", pill="#4D4D4B", accent="#4D4D4B", link="#3A3A39",
    doc_edge="#BDBDBB", doc_fold="#C9C9C7", doc_text="#5C5C5A", folder=("#8F8F8D", "#B3B3B1"),
    err="#2A2A29"))

_add(_citrus(
    "orange", "Апельсин",
    rind=("#F7A33A", "#EE8A1C", "#D9731A"), rind_edge="#C8661A",
    pores=((255, 236, 200), (150, 70, 0)), pith=("#FFF9EA", "#FBEFD2", "#F3E0B6"),
    wedge=("#F59A2C", "#F9B34E"), wedge_h=("#FFB54D", "#FFCF7A"), edge="#E08421", edge_h="#FFF6E4",
    vesicle=(255, 238, 196), label="#5B2C00", label_h="#3A1C00", glow=(255, 244, 220, 140),
    hint="#7A4510", hint_h="#4D2A06", center=("#FFFBF1", "#F6E9CB"), border=Q(150, 90, 20, 60),
    text="#4A2A08", sub="#7A5426", muted="#A07A4C", pill="#E07B16", accent="#E07B16", link="#B35C0C",
    doc_edge="#E8D3A8", doc_fold="#F1DDB2", doc_text="#9A6A2C", folder=("#E9A04A", "#F5BC6A")))

_add(_citrus(
    "lime", "Лайм",
    rind=("#8CC63F", "#6FAE2B", "#5A9622"), rind_edge="#4E8420",
    pores=((240, 255, 210), (40, 80, 10)), pith=("#F8FDEB", "#EEF7D6", "#DDEDBC"),
    wedge=("#A9D459", "#BFE27A"), wedge_h=("#C6E784", "#DDF3A8"), edge="#93C04B", edge_h="#F6FFE6",
    vesicle=(248, 255, 226), label="#23400A", label_h="#152A04", glow=(250, 255, 235, 140),
    hint="#3E6219", hint_h="#28440E", center=("#FBFEF2", "#EAF5D2"), border=Q(60, 110, 20, 60),
    text="#22380C", sub="#4F6B2D", muted="#7A9156", pill="#5E9B22", accent="#5E9B22", link="#3F7A12",
    doc_edge="#D2E5AE", doc_fold="#DCECBF", doc_text="#6A8A3C", folder=("#8FC24A", "#B1D97A")))

# ---------------------------------------------------------------- неон
_add(Theme(
    "neon", "Неон", "neon",
    Q(36, 44, 60, 250), Q(18, 22, 32, 250), Q(120, 205, 255, 90), Q("#FFFFFF"), Q(190, 200, 215),
    Q(150, 160, 178), Q(37, 120, 220), Q("#FFFFFF"), Q(236, 240, 246), Q(236, 240, 246), Q(190, 198, 210),
    Q(90, 100, 118), Q("#3D7BD9"), Q("#5B9BF0"), Q("#3BB6FF"), Q(255, 255, 255, 25), Q("#34D399"),
    Q("#FFFFFF"), Q("#FF5A5F"), Q(140, 200, 255),
    dict(bg=[Q(30, 37, 50, 246), Q(17, 21, 30, 244), Q(11, 14, 20, 246)], glow=(59, 182, 255),
         rim=Q(120, 205, 255, 230), badges=None)))

_add(Theme(
    "synthwave", "Синтвейв", "neon",
    Q(46, 18, 66, 250), Q(24, 8, 40, 250), Q(255, 110, 220, 90), Q("#FFFFFF"), Q(225, 195, 240),
    Q(175, 145, 200), Q("#FF4FD8"), Q("#FFFFFF"), Q(245, 236, 250), Q(245, 236, 250), Q(210, 190, 225),
    Q(110, 70, 140), Q("#B66BFF"), Q("#D49BFF"), Q("#3EE6FF"), Q(255, 255, 255, 25), Q("#3EE6FF"),
    Q("#1B0830"), Q("#FF4F6D"), Q("#3EE6FF"),
    dict(bg=[Q(48, 16, 70, 246), Q(26, 9, 44, 244), Q(13, 4, 24, 246)], glow=(255, 60, 200),
         rim=Q(255, 110, 220, 235), badges=["#FF4FD8", "#3EE6FF", "#B66BFF", "#FF9F45"])))

# ---------------------------------------------------------------- стекло
_add(Theme(
    "glass", "Стекло", "glass",
    Q("#FFFFFF"), Q("#F2F2F5"), Q(0, 0, 0, 28), Q("#1D1D1F"), Q("#6E6E73"), Q("#8E8E93"), Q("#0A84FF"),
    Q("#FFFFFF"), Q("#FFFFFF"), Q("#D1D1D6"), Q("#E5E5EA"), Q("#8E8E93"), Q("#5AC8FA"), Q("#8DD8FB"),
    Q("#0A84FF"), Q(0, 0, 0, 20), Q("#34C759"), Q("#FFFFFF"), Q("#FF3B30"), Q("#0A84FF"),
    dict(tile=Q(255, 255, 255, 222), tile_edge=Q(0, 0, 0, 26), tile_h=Q("#0A84FF"),
         tile_h_edge=Q("#0A84FF"), label=Q("#1D1D1F"), label_h=Q("#FFFFFF"), hint=Q("#6E6E73"),
         hint_h=Q(255, 255, 255, 225), shadow=50)))

_add(Theme(
    "graphite", "Графит", "glass",
    Q("#2C2C2E"), Q("#1C1C1E"), Q(255, 255, 255, 30), Q("#F2F2F7"), Q("#AEAEB2"), Q("#8E8E93"),
    Q("#F2F2F7"), Q("#1C1C1E"), Q("#E5E5EA"), Q("#E5E5EA"), Q("#AEAEB2"), Q("#3A3A3C"), Q("#8E8E93"),
    Q("#AEAEB2"), Q("#F2F2F7"), Q(255, 255, 255, 30), Q("#F2F2F7"), Q("#1C1C1E"), Q("#FF453A"),
    Q("#F2F2F7"),
    dict(tile=Q(40, 40, 44, 238), tile_edge=Q(255, 255, 255, 24), tile_h=Q("#F2F2F7"),
         tile_h_edge=Q("#FFFFFF"), label=Q("#F2F2F7"), label_h=Q("#1C1C1E"), hint=Q(174, 174, 178),
         hint_h=Q(60, 60, 67), shadow=90)))

# ---------------------------------------------------------------- винил
_add(Theme(
    "vinyl", "Винил", "vinyl",
    Q("#F06A3C"), Q("#D44A22"), Q(0, 0, 0, 60), Q("#1A0E08"), Q("#3D1F12"), Q("#5A2E1A"), Q("#1A1A1A"),
    Q("#F7E9E1"), Q("#FFF5EF"), Q("#FFF5EF"), Q("#F3C9B4"), Q("#B5482A"), Q("#1A1A1A"), Q("#3A3A3A"),
    Q("#1A1A1A"), Q(0, 0, 0, 45), Q("#1A1A1A"), Q("#F06A3C"), Q("#6B0F0F"), Q("#1A1A1A"),
    dict(disc=[Q("#222222"), Q("#121212"), Q("#0A0A0A")], groove=Q(255, 255, 255, 13),
         sheen=Q(255, 255, 255, 40), sep=Q(255, 255, 255, 20), hover=Q(255, 255, 255, 46),
         label=Q("#E6E6E6"), label_h=Q("#FFFFFF"), hint=Q(150, 150, 150), hint_h=Q(225, 225, 225),
         ring=Q("#F06A3C"))))


# ---------------------------------------------------------------- фрукты с семечками
_add(_citrus(
    "watermelon", "Арбуз",
    rind=("#C9E89A", "#5E9E2E", "#1F5A17"), rind_edge="#174D12",
    pores=((225, 245, 190), (20, 70, 15)), pith=("#F4FAE6", "#E4F2C8", "#CFE6A6"),
    wedge=("#E2384E", "#F25468"), wedge_h=("#F65A6E", "#FF7D8C"), edge="#C92A40", edge_h="#FFE3E7",
    vesicle=(255, 205, 212), label="#FFFFFF", label_h="#FFFFFF", glow=(120, 10, 25, 150),
    hint="#FFE3E7", hint_h="#FFFFFF", center=("#FFF7F7", "#FBE3E3"), border=Q(150, 30, 45, 60),
    text="#4A0A14", sub="#7A2A36", muted="#A0525E", pill="#2E7D32", accent="#D62A44", link="#B71C35",
    doc_edge="#F1C9CF", doc_fold="#F6D5DA", doc_text="#A0525E", folder=("#5E9E2E", "#8CC63F"),
    seeds={"color": (30, 22, 20), "zone": "both", "count": 5, "size": 1.0}, label_shadow=(90, 0, 15, 170)))

_add(_citrus(
    "kiwi", "Киви",
    rind=("#9C7A52", "#7A5734", "#5C3F22"), rind_edge="#4E341C",
    pores=((200, 170, 130), (60, 40, 20)), pith=("#F1F7D8", "#E2EEBB", "#CFE29A"),
    wedge=("#C7E07A", "#7DB733"), wedge_h=("#DBEE98", "#9CD24C"), edge="#6FA82B", edge_h="#F5FFE0",
    vesicle=(235, 250, 200), label="#1F3608", label_h="#122304", glow=(245, 255, 225, 150),
    hint="#3A5A16", hint_h="#22400A", center=("#FFFDF0", "#F3EDCC"), border=Q(90, 110, 40, 60),
    text="#2A3A10", sub="#556B2F", muted="#7E8F5A", pill="#5E8F22", accent="#5E8F22", link="#3F7A12",
    doc_edge="#DCE6B8", doc_fold="#E6EFC6", doc_text="#6A8A3C", folder=("#8DB84A", "#B4D77A"),
    seeds={"color": (25, 20, 15), "zone": "inner", "count": 9, "size": 0.75}, pores_n=420))

# ---------------------------------------------------------------- еда
_add(_mk(
    "pizza", "Пицца", "pizza",
    center=("#FFF6E2", "#F0DCB2"), border=(120, 70, 20, 70), text="#4A240A", sub="#7A4A20",
    muted="#9C7448", pill="#C8442B", doc_edge="#E8D3A8", doc_fold="#F1DDB2", doc_text="#9A6A2C",
    folder=("#D98B3A", "#EDB36A"), accent="#C8442B",
    crust=["#E9B568", "#D08E40", "#A9662A"], sauce="#C8442B", cheese=["#F9DA7E", "#F3C24F"],
    cheese_h=["#FFE59A", "#FFD36A"], cheese_edge="#E2A93A", pepperoni="#B8352A", basil="#3E8E3A",
    label="#5A1E0A", label_h="#3E1404", glow=(255, 248, 220, 170), hint="#7A3A14", hint_h="#5A2A0A"))

_add(_mk(
    "donut", "Пончик", "donut",
    center=("#FFF4E4", "#F6DDBA"), border=(150, 90, 40, 60), text="#5A2E10", sub="#8A5A30",
    muted="#A8805A", pill="#E0457B", doc_edge="#F1D2BC", doc_fold="#F6DCC8", doc_text="#B06A48",
    folder=("#E9A04A", "#F5BC6A"), accent="#E0457B",
    dough=["#F0C27E", "#D9984F", "#B8733A"], glaze=["#F9A8C9", "#F07AA8"], glaze_edge="#E2669A",
    sprinkles=["#FFFFFF", "#FFD54F", "#64B5F6", "#81C784", "#BA68C8", "#FF8A65"],
    label="#5A1030", label_h="#3A0820", glow=(255, 240, 246, 190), hint="#7A2848", hint_h="#5A1030",
    ring="#FFFFFF"))

# ---------------------------------------------------------------- предметы
_add(_mk(
    "helm", "Штурвал", "helm",
    center=("#F6DC92", "#C99A3E"), border=(110, 75, 20, 140), text="#3A2608", sub="#5E4216",
    muted="#7A5A28", pill="#6B3F1D", pill_text="#F7E7C4", doc="#FFF8E6", doc_edge="#C9A44A",
    doc_fold="#E8D29A", doc_text="#8A6420", folder=("#8B5A2B", "#B07A44"), accent="#6B3F1D",
    ok="#6B3F1D", ok_mark="#F6DC92",
    wood=["#9A6534", "#7A4A22", "#5C3416"], brass="#D4AF4F", paper=["#F6E8C8", "#E6CD9C"],
    label="#3E2412", label_h="#2A1608", glow=(255, 248, 228, 160), hint="#6B4A2B", hint_h="#4A2E14",
    hover=(255, 200, 90, 120), ring="#FFD36A"))

_add(_mk(
    "tire", "Колесо", "tire",
    center=("#F3F5F7", "#B6BCC4"), border=(60, 65, 72, 120), text="#1E2126", sub="#3E434A",
    muted="#5E646C", pill="#1E2126", doc_edge="#C9CED5", doc_fold="#DADFE4", doc_text="#5E646C",
    folder=("#7D838B", "#A9AFB7"), accent="#E53935", ok="#E53935", err="#8E1B1B",
    rubber=["#3A3A3A", "#222222", "#0E0E0E"], metal=["#F1F3F5", "#A7ADB5", "#6E747C"],
    brake="#34373C", label="#F5F5F5", label_h="#FFFFFF", hint="#AEB3BA", hint_h="#E6E8EB",
    hover=(255, 255, 255, 30), ring="#E53935"))

_add(_mk(
    "disc", "CD-диск", "disc",
    center=("#FFFFFF", "#E2E6EA"), border=(0, 0, 0, 40), text="#1F2328", sub="#4A5058",
    muted="#6E757E", pill="#1F2328", doc_edge="#D3D8DE", doc_fold="#E3E7EB", doc_text="#6E757E",
    folder=("#9AA3AD", "#C3CAD2"), accent="#6C5CE7",
    silver=["#F2F4F6", "#D7DCE1", "#B9C0C8"], label="#1A1E23", label_h="#000000",
    glow=(255, 255, 255, 200), hint="#3E444C", hint_h="#1F2328", ring="#FFFFFF"))


# порядок в окне и в меню: фрукты, еда, яркие, спокойные, предметы
ORDER = ["citrus", "orange", "lime", "watermelon", "kiwi",
         "pizza", "donut", "neon", "synthwave", "vinyl",
         "glass", "graphite", "disc", "helm", "tire"]
THEMES = {k: THEMES[k] for k in ORDER + [k for k in THEMES if k not in ORDER]}


def get(key: str | None) -> Theme:
    key = LEGACY.get(key or "", key or "")
    return THEMES.get(key) or THEMES[DEFAULT_THEME]


def normalize(key: str | None) -> str:
    return get(key).key
