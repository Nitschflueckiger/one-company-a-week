"""grafik.py — the carousel (JPEG, 1080×1350) and the reel (MP4, 1080×1920) for one company.

Everything is drawn by hand with Pillow; the reel's frames go to ffmpeg (the static binary
that ships with ``imageio-ffmpeg``). No stock prices anywhere: only figures from the
company's own annual report (SEC Form 10-K).
"""
from __future__ import annotations

import math
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Optional, Sequence

from PIL import Image, ImageDraw, ImageFont

from agent.drehbuch import Drehbuch, Firma, geld_kurz, pct

# ---------------------------------------------------------------------------
# Look
# ---------------------------------------------------------------------------
GRUND = (14, 26, 38)
FLAECHE = (22, 38, 56)
LINIE = (46, 66, 88)
TEXT = (244, 239, 230)
LEISE = (154, 167, 180)
MESSING = (201, 164, 92)
GUT = (127, 184, 154)
SCHLECHT = (217, 119, 107)

KARUSSELL = (1080, 1350)
REEL = (1080, 1920)
FPS = 30
RAND = 84


def _schriftordner() -> Path:
    import matplotlib

    return Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf"


_SCHRIFTEN: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}


def schrift(art: str, groesse: int) -> ImageFont.FreeTypeFont:
    """``art``: titel (serif bold), text, fett, leise (sans)."""
    datei = {"titel": "DejaVuSerif-Bold.ttf", "serif": "DejaVuSerif.ttf", "text": "DejaVuSans.ttf",
             "fett": "DejaVuSans-Bold.ttf"}[art]
    schluessel = (datei, groesse)
    if schluessel not in _SCHRIFTEN:
        _SCHRIFTEN[schluessel] = ImageFont.truetype(str(_schriftordner() / datei), groesse)
    return _SCHRIFTEN[schluessel]


def umbrechen(text: str, font: ImageFont.FreeTypeFont, breite: int) -> list[str]:
    zeilen: list[str] = []
    for absatz in text.split("\n"):
        aktuell = ""
        for wort in absatz.split():
            probe = f"{aktuell} {wort}".strip()
            if font.getlength(probe) <= breite or not aktuell:
                aktuell = probe
            else:
                zeilen.append(aktuell)
                aktuell = wort
        zeilen.append(aktuell)
    return zeilen


def absatz(d: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, font: ImageFont.FreeTypeFont, breite: int,
           farbe=TEXT, zeilenabstand: float = 1.32, alpha: float = 1.0) -> int:
    """Draws wrapped text, returns the y below it."""
    x, y = xy
    hoehe = int(font.size * zeilenabstand)
    for zeile in umbrechen(text, font, breite):
        d.text((x, y), zeile, font=font, fill=_mit_alpha(farbe, alpha))
        y += hoehe
    return y


def _mit_alpha(farbe, alpha: float):
    if alpha >= 1:
        return farbe
    return tuple(int(g + (c - g) * max(0.0, alpha)) for c, g in zip(farbe, GRUND))


def ease(t: float) -> float:
    t = min(1.0, max(0.0, t))
    return 1 - (1 - t) ** 3


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------
def _kopf(d: ImageDraw.ImageDraw, breite: int, kicker: str, marke: str, alpha: float = 1.0) -> None:
    d.text((RAND, RAND), kicker.upper(), font=schrift("fett", 26), fill=_mit_alpha(MESSING, alpha))
    if marke:
        f = schrift("text", 26)
        d.text((breite - RAND - f.getlength(marke), RAND), marke, font=f, fill=_mit_alpha(LEISE, alpha))
    d.line((RAND, RAND + 46, breite - RAND, RAND + 46), fill=_mit_alpha(LINIE, alpha), width=2)


def _fuss(d: ImageDraw.ImageDraw, groesse: tuple[int, int], text: str, alpha: float = 1.0) -> None:
    f = schrift("text", 24)
    d.text((RAND, groesse[1] - RAND - 24), text, font=f, fill=_mit_alpha(LEISE, alpha))


def balken(d: ImageDraw.ImageDraw, box: tuple[int, int, int, int], werte: Sequence[Optional[float]],
           beschriftung: Sequence[str], wertetext: Callable[[float], str], *, fortschritt: float = 1.0,
           farbe=MESSING, hervorheben: Optional[int] = None) -> None:
    """Vertical bars in ``box``; ``fortschritt`` 0..1 lets them grow (staggered)."""
    x0, y0, x1, y1 = box
    gueltig = [w for w in werte if w is not None]
    oben = max([0.0] + gueltig)
    unten = min([0.0] + gueltig)
    spanne = (oben - unten) or 1.0
    null_y = y0 + 64 + (y1 - 60 - y0 - 64) * (oben / spanne)
    n = len(werte)
    feld = (x1 - x0) / n
    breite = feld * 0.58
    d.line((x0, null_y, x1, null_y), fill=LINIE, width=2)
    for i, (w, name) in enumerate(zip(werte, beschriftung)):
        mitte = x0 + feld * (i + 0.5)
        f_name = schrift("text", 26)
        d.text((mitte - f_name.getlength(name) / 2, y1 - 40), name, font=f_name, fill=LEISE)
        if w is None:
            continue
        lokal = ease((fortschritt * (n + 1.5) - i) / 2.5)
        if lokal <= 0:
            continue
        hoehe = (y1 - 60 - y0 - 64) * (abs(w) / spanne) * lokal
        f = farbe if hervorheben is None or i == hervorheben else _mit_alpha(farbe, 0.55)
        if w < 0:
            f = SCHLECHT
            d.rounded_rectangle((mitte - breite / 2, null_y, mitte + breite / 2, null_y + max(hoehe, 1)), radius=10, fill=f)
            y_text = null_y + hoehe + 10
        else:
            d.rounded_rectangle((mitte - breite / 2, null_y - max(hoehe, 1), mitte + breite / 2, null_y), radius=10, fill=f)
            y_text = null_y - hoehe - 44
        if lokal > 0.6:
            t = wertetext(w * lokal if lokal < 1 else w)
            ft = schrift("fett", 30)
            d.text((mitte - ft.getlength(t) / 2, y_text), t, font=ft, fill=_mit_alpha(TEXT, (lokal - 0.6) / 0.4))


def _geschaeftsjahre(firma: Firma) -> list[str]:
    return [f"FY{j.ende[2:4]}" for j in firma.jahre]


# ---------------------------------------------------------------------------
# Carousel
# ---------------------------------------------------------------------------
def _folie() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    bild = Image.new("RGB", KARUSSELL, GRUND)
    return bild, ImageDraw.Draw(bild)


def karussell(firma: Firma, db: Drehbuch) -> list[Image.Image]:
    w, h = KARUSSELL
    innen = w - 2 * RAND
    folien: list[Image.Image] = []

    # 1 · cover
    bild, d = _folie()
    _kopf(d, w, db.kicker, db.marke)
    y = absatz(d, (RAND, 330), db.titel, schrift("titel", 104), innen, zeilenabstand=1.12)
    d.text((RAND, y + 18), f"{firma.ticker} · {firma.boerse} · {db.branche or firma.branche_kurz}", font=schrift("text", 32),
           fill=LEISE)
    absatz(d, (RAND, y + 110), db.unterzeile, schrift("serif", 46), innen, farbe=MESSING)
    _kennzahlen(d, firma, (RAND, h - 400, w - RAND, h - 170))
    _fuss(d, KARUSSELL, "Swipe →")
    folien.append(bild)

    # 2 · what they do
    bild, d = _folie()
    _kopf(d, w, db.kicker, db.marke)
    d.text((RAND, 200), "What they do", font=schrift("titel", 64), fill=TEXT)
    absatz(d, (RAND, 320), db.was, schrift("text", 40), innen, zeilenabstand=1.45)
    _fuss(d, KARUSSELL, f"{db.titel} · from the annual report")
    folien.append(bild)

    # 3–5 · the numbers
    for szene in db.szenen:
        bild, d = _folie()
        _kopf(d, w, db.kicker, db.marke)
        y = absatz(d, (RAND, 190), szene.headline, schrift("titel", 54), innen, zeilenabstand=1.18)
        _diagramm(d, firma, szene.art, (RAND, max(y + 40, 470), w - RAND, h - 170), 1.0)
        _fuss(d, KARUSSELL, _quelle_kurz(firma, szene.art))
        folien.append(bild)

    # 6 · both sides
    bild, d = _folie()
    _kopf(d, w, db.kicker, db.marke)
    d.text((RAND, 190), "Two sides", font=schrift("titel", 64), fill=TEXT)
    y = 310
    f_text = schrift("text", 33)
    for titel, text, farbe in (("For", db.dafuer, GUT), ("Against", db.dagegen, SCHLECHT)):
        hoehe = 84 + len(umbrechen(text, f_text, innen - 72)) * int(33 * 1.4) + 30
        d.rounded_rectangle((RAND, y, w - RAND, y + hoehe), radius=18, fill=FLAECHE)
        d.text((RAND + 36, y + 30), titel.upper(), font=schrift("fett", 28), fill=farbe)
        absatz(d, (RAND + 36, y + 84), text, f_text, innen - 72, zeilenabstand=1.4)
        y += hoehe + 36
    _fuss(d, KARUSSELL, "No verdict here: numbers first.")
    folien.append(bild)

    # 7 · source and fine print
    bild, d = _folie()
    _kopf(d, w, db.kicker, db.marke)
    d.text((RAND, 330), db.schluss, font=schrift("titel", 60), fill=TEXT)
    y = absatz(d, (RAND, 460), f"Source: {firma.name}, Form 10-K for the fiscal year ended {firma.stichtag} (SEC EDGAR).",
               schrift("text", 34), innen, farbe=LEISE)
    absatz(d, (RAND, y + 30), HINWEIS, schrift("text", 34), innen, farbe=LEISE)
    folien.append(bild)
    return folien


HINWEIS = "Education, not investment advice. We don't tell anyone what to buy or sell."


def kennzahlen(firma: Firma) -> list[tuple[str, str]]:
    """Three figures for the cover: latest revenue, last year's growth, operating margin."""
    l = firma.jahre[-1]
    jahr = f"FY{l.ende[2:4]}"
    aus = [(geld_kurz(l.umsatz), f"revenue {jahr}")]
    if l.wachstum is not None:
        aus.append((f"{l.wachstum * 100:+.1f}%", "revenue growth"))
    if l.betriebsmarge is not None:
        aus.append((pct(l.betriebsmarge), "operating margin"))
    elif l.fcf is not None:
        aus.append((geld_kurz(l.fcf), "free cash flow"))
    return aus


def _kennzahlen(d: ImageDraw.ImageDraw, firma: Firma, box: tuple[int, int, int, int], alpha: float = 1.0) -> None:
    x0, y0, x1, y1 = box
    werte = kennzahlen(firma)
    feld = (x1 - x0) / len(werte)
    d.line((x0, y0, x1, y0), fill=_mit_alpha(LINIE, alpha), width=2)
    for i, (zahl, name) in enumerate(werte):
        x = x0 + feld * i
        d.text((x, y0 + 40), zahl, font=schrift("titel", 58), fill=_mit_alpha(TEXT, alpha))
        d.text((x, y0 + 130), name, font=schrift("text", 28), fill=_mit_alpha(LEISE, alpha))


def _quelle_kurz(firma: Firma, art: str) -> str:
    return f"Fiscal years ending {firma.jahre[-1].ende[5:]} · SEC Form 10-K"


def _diagramm(d: ImageDraw.ImageDraw, firma: Firma, art: str, box: tuple[int, int, int, int], fortschritt: float) -> None:
    jahre = _geschaeftsjahre(firma)
    letzte = len(firma.jahre) - 1
    if art == "umsatz":
        balken(d, box, [j.umsatz for j in firma.jahre], jahre, geld_kurz, fortschritt=fortschritt, hervorheben=letzte)
    elif art == "marge":
        balken(d, box, [j.betriebsmarge for j in firma.jahre], jahre, pct, fortschritt=fortschritt, farbe=GUT,
               hervorheben=letzte)
    elif art == "fcf":
        balken(d, box, [j.fcf for j in firma.jahre], jahre, geld_kurz, fortschritt=fortschritt, farbe=GUT, hervorheben=letzte)
    elif art == "bilanz":
        x0, y0, x1, y1 = box
        l = firma.jahre[-1]
        werte = [l.kasse, l.schulden, l.eigenkapital]
        balken(d, box, werte, ["Cash", "Debt", "Equity"], geld_kurz, fortschritt=fortschritt, farbe=MESSING)
    else:
        raise ValueError(f"unknown chart {art!r}")


def speichere_karussell(folien: Iterable[Image.Image], ordner: Path) -> list[Path]:
    ordner.mkdir(parents=True, exist_ok=True)
    pfade = []
    for i, bild in enumerate(folien, 1):
        p = ordner / f"folie-{i}.jpg"
        bild.save(p, "JPEG", quality=92, optimize=True, progressive=False)
        pfade.append(p)
    return pfade


# ---------------------------------------------------------------------------
# Reel
# ---------------------------------------------------------------------------
@dataclass
class Szene:
    dauer: float
    zeichne: Callable[[ImageDraw.ImageDraw, float], None]


def _reel_szenen(firma: Firma, db: Drehbuch) -> list[Szene]:
    w, h = REEL
    innen = w - 2 * RAND

    def titel(d: ImageDraw.ImageDraw, t: float) -> None:
        a = ease(t / 0.35)
        _kopf(d, w, db.kicker, db.marke, a)
        versatz = int(60 * (1 - ease(t / 0.4)))
        y = absatz(d, (RAND, 640 + versatz), db.titel, schrift("titel", 118), innen, zeilenabstand=1.1, alpha=a)
        b = ease((t - 0.25) / 0.35)
        d.text((RAND, y + 20), f"{firma.ticker} · {firma.boerse}", font=schrift("text", 38), fill=_mit_alpha(LEISE, b))
        c = ease((t - 0.45) / 0.35)
        absatz(d, (RAND, y + 110), db.unterzeile, schrift("serif", 54), innen, farbe=MESSING, alpha=c)
        _kennzahlen(d, firma, (RAND, h - 700, w - RAND, h - 480), ease((t - 0.6) / 0.3))

    def zahlen(szene) -> Callable[[ImageDraw.ImageDraw, float], None]:
        def zeichne(d: ImageDraw.ImageDraw, t: float) -> None:
            _kopf(d, w, db.kicker, db.marke)
            a = ease(t / 0.2)
            y = absatz(d, (RAND, 300), szene.headline, schrift("titel", 64), innen, zeilenabstand=1.16, alpha=a)
            _diagramm(d, firma, szene.art, (RAND, max(y + 80, 700), w - RAND, h - 360), ease((t - 0.1) / 0.75))
            _fuss(d, REEL, _quelle_kurz(firma, szene.art), a)
        return zeichne

    def schluss(d: ImageDraw.ImageDraw, t: float) -> None:
        a = ease(t / 0.3)
        _kopf(d, w, db.kicker, db.marke, a)
        y = absatz(d, (RAND, 700), db.schluss, schrift("titel", 76), innen, alpha=a)
        b = ease((t - 0.3) / 0.3)
        y = absatz(d, (RAND, y + 40), f"Source: Form 10-K, fiscal year ended {firma.stichtag}.", schrift("text", 38),
                   innen, farbe=LEISE, alpha=b)
        absatz(d, (RAND, y + 24), HINWEIS, schrift("text", 38), innen, farbe=LEISE, alpha=b)

    return [Szene(3.6, titel)] + [Szene(4.6, zahlen(s)) for s in db.szenen] + [Szene(3.6, schluss)]


def reel(firma: Firma, db: Drehbuch, ziel: Path, *, fps: int = FPS) -> Path:
    """Writes the reel as H.264 MP4 with a silent AAC track (Instagram rejects some video without audio)."""
    import imageio_ffmpeg

    ziel.parent.mkdir(parents=True, exist_ok=True)
    stumm = ziel.with_suffix(".stumm.mp4")
    szenen = _reel_szenen(firma, db)
    schreiber = imageio_ffmpeg.write_frames(str(stumm), REEL, fps=fps, codec="libx264", pix_fmt_out="yuv420p",
                                            output_params=["-crf", "20", "-preset", "medium", "-movflags", "+faststart"],
                                            macro_block_size=8)
    schreiber.send(None)
    gesamt = sum(int(round(s.dauer * fps)) for s in szenen)
    bisher = 0
    try:
        for s in szenen:
            n = int(round(s.dauer * fps))
            for k in range(n):
                bild = Image.new("RGB", REEL, GRUND)
                d = ImageDraw.Draw(bild)
                s.zeichne(d, k / max(1, n - 1))
                # the thin progress line, like a story
                d.rectangle((0, 0, int(REEL[0] * (bisher + k + 1) / gesamt), 6), fill=MESSING)
                schreiber.send(bild.tobytes())
            bisher += n
    finally:
        schreiber.close()
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    subprocess.run([exe, "-y", "-loglevel", "error", "-i", str(stumm), "-f", "lavfi", "-i",
                    "anullsrc=channel_layout=stereo:sample_rate=44100", "-shortest", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "128k", "-movflags", "+faststart", str(ziel)], check=True)
    os.remove(stumm)
    return ziel


def dauer(db: Drehbuch) -> float:
    return 3.6 + 4.6 * len(db.szenen) + 3.6


# ---------------------------------------------------------------------------
# The other posts of the week
# ---------------------------------------------------------------------------
def zahl_bild(firma: Firma, db: Drehbuch, nummer: int) -> Image.Image:
    """One number, big: stops the scroll, gets saved."""
    z = db.zahlen[nummer - 1]
    w, h = KARUSSELL
    bild, d = _folie()
    _kopf(d, w, db.kicker, db.marke)
    d.text((RAND, 250), db.titel, font=schrift("fett", 40), fill=LEISE)
    groesse = 300 if len(z.zahl) <= 4 else 230 if len(z.zahl) <= 6 else 180
    d.text((RAND - 8, 360), z.zahl, font=schrift("titel", groesse), fill=MESSING)
    absatz(d, (RAND, 360 + int(groesse * 1.25)), z.zeile, schrift("serif", 50), w - 2 * RAND, zeilenabstand=1.3)
    _fuss(d, KARUSSELL, f"Form 10-K, fiscal year ended {firma.stichtag}")
    return bild


def frage_bild(firma: Firma, db: Drehbuch) -> Image.Image:
    """A question people answer in the comments."""
    if db.frage is None:
        raise ValueError("the script has no question")
    w, h = KARUSSELL
    bild, d = _folie()
    _kopf(d, w, db.kicker, db.marke)
    d.text((RAND - 10, 150), "?", font=schrift("titel", 420), fill=_mit_alpha(MESSING, 0.35))
    absatz(d, (RAND, 620), db.frage.frage, schrift("titel", 66), w - 2 * RAND, zeilenabstand=1.22)
    _kennzahlen(d, firma, (RAND, h - 400, w - RAND, h - 170))
    _fuss(d, KARUSSELL, "Tell us in the comments.")
    return bild


def begriff_karussell(firma: Firma, db: Drehbuch) -> list[Image.Image]:
    """A term, explained with this week's company: definition, example, why it matters."""
    b = db.begriff
    if b is None:
        raise ValueError("the script has no term")
    w, h = KARUSSELL
    innen = w - 2 * RAND
    folien = []
    bild, d = _folie()
    _kopf(d, w, "Explained", db.marke)
    y = absatz(d, (RAND, 330), b.begriff, schrift("titel", 104), innen, zeilenabstand=1.1)
    absatz(d, (RAND, y + 50), b.definition, schrift("serif", 48), innen, farbe=MESSING, zeilenabstand=1.3)
    _fuss(d, KARUSSELL, "Swipe for an example →")
    folien.append(bild)
    bild, d = _folie()
    _kopf(d, w, f"Example: {db.titel}", db.marke)
    y = absatz(d, (RAND, 190), b.szene.headline, schrift("titel", 54), innen, zeilenabstand=1.18)
    _diagramm(d, firma, b.szene.art, (RAND, max(y + 40, 470), w - RAND, h - 170), 1.0)
    _fuss(d, KARUSSELL, _quelle_kurz(firma, b.szene.art))
    folien.append(bild)
    bild, d = _folie()
    _kopf(d, w, "Explained", db.marke)
    d.text((RAND, 250), "Why it matters", font=schrift("titel", 64), fill=TEXT)
    absatz(d, (RAND, 380), b.warum, schrift("text", 42), innen, zeilenabstand=1.45)
    _kennzahlen(d, firma, (RAND, h - 400, w - RAND, h - 170))
    _fuss(d, KARUSSELL, HINWEIS)
    folien.append(bild)
    return folien


def reel2(firma: Firma, db: Drehbuch, ziel: Path, *, fps: int = FPS) -> Path:
    """The second reel of the week: the same facts, another angle."""
    if db.reel2 is None:
        raise ValueError("the script has no second reel")
    from dataclasses import replace

    return reel(firma, replace(db, unterzeile=db.reel2.unterzeile, szenen=db.reel2.szenen), ziel, fps=fps)


def medien_fuer(firma: Firma, db: Drehbuch, art: str, ordner: Path) -> list[Path]:
    """Render exactly what one post needs."""
    ordner.mkdir(parents=True, exist_ok=True)
    if art == "karussell":
        return speichere_karussell(karussell(firma, db), ordner)
    if art == "reel":
        return [reel(firma, db, ordner / "reel.mp4")]
    if art == "reel2":
        return [reel2(firma, db, ordner / "reel2.mp4")]
    if art.startswith("zahl-"):
        p = ordner / f"{art}.jpg"
        zahl_bild(firma, db, int(art[5:])).save(p, "JPEG", quality=92, optimize=True)
        return [p]
    if art == "frage":
        p = ordner / "frage.jpg"
        frage_bild(firma, db).save(p, "JPEG", quality=92, optimize=True)
        return [p]
    if art == "begriff":
        pfade = []
        for i, b in enumerate(begriff_karussell(firma, db), 1):
            p = ordner / f"begriff-{i}.jpg"
            b.save(p, "JPEG", quality=92, optimize=True)
            pfade.append(p)
        return pfade
    raise ValueError(f"unknown post {art!r}")
