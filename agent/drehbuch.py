"""drehbuch.py — the week's company (facts) and the script the agent writes for it (words).

The facts come from the public "Company of the week" post (``company.json``), which is
built from the company's own annual report (SEC Form 10-K) and checked before it goes
public. The agent writes the words — title line, headlines, caption — and
:func:`pruefe` refuses any number that is not in those facts and any word that sounds
like advice or like a fund talking about itself.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Optional

MAX = {"titel": 40, "unterzeile": 90, "was": 360, "headline": 80, "dafuer": 280, "dagegen": 280, "schluss": 40,
       "caption": 2000, "zahl": 8, "zeile": 140, "frage": 150, "begriff": 32, "definition": 220, "warum": 300}
#: Every post of a week, in the order of the week (see ROUTINE.md for the calendar).
ARTEN = ("karussell", "zahl-1", "reel", "begriff", "zahl-2", "reel2", "frage")
MAX_HASHTAGS = 8
SZENEN_ARTEN = ("umsatz", "marge", "fcf", "bilanz")

#: Words that turn education into advice, or that give away who is behind the page.
VERBOTEN = (
    "buy the stock", "buy the shares", "sell the stock", "sell the shares", "should buy", "should sell",
    "time to buy", "time to sell", "buy now", "sell now", "strong buy", "buy signal", "sell signal", "buy rating",
    "sell rating", "price target", "target price", "undervalued", "overvalued", "cheap stock", "guarantee",
    "guaranteed", "can't lose", "to the moon", "financial advice", "invest now", "our fund", "our portfolio",
    "we own", "we hold", "we bought", "we sold", "our position",
)


def verbotene_namen() -> tuple[str, ...]:
    """The names of whoever is behind the page — from the environment, never written into this public code."""
    return tuple(n.strip().lower() for n in os.environ.get("VERBOTENE_NAMEN", "").split(",") if n.strip())


def geld(wert: float) -> str:
    """Same style as the website: 392 mn USD, 1.6 bn USD."""
    if abs(wert) >= 1e9:
        return f"{wert / 1e9:.1f} bn USD"
    return f"{wert / 1e6:.0f} mn USD"


def geld_kurz(wert: float) -> str:
    """Chart labels and big numbers: $1.6bn, $392m, -$12m."""
    vorzeichen = "-" if wert < 0 else ""
    w = abs(wert)
    return f"{vorzeichen}${w / 1e9:.1f}bn" if w >= 1e9 else f"{vorzeichen}${w / 1e6:.0f}m"


def pct(wert: float) -> str:
    return f"{wert * 100:.1f}%"


@dataclass
class Jahr:
    ende: str
    umsatz: float
    betrieb: Optional[float] = None
    gewinn: Optional[float] = None
    cashflow: Optional[float] = None
    investitionen: Optional[float] = None
    betriebsmarge: Optional[float] = None
    nettomarge: Optional[float] = None
    fcf: Optional[float] = None
    wachstum: Optional[float] = None
    kasse: Optional[float] = None
    schulden: Optional[float] = None
    eigenkapital: Optional[float] = None


@dataclass
class Firma:
    woche: str
    name: str
    ticker: str
    boerse: str
    branche: str
    stichtag: str
    zehn_k_url: str
    jahre: list[Jahr]
    abschnitte: dict[str, str]
    seite: str = ""

    @property
    def branche_kurz(self) -> str:
        b = self.branche or ""
        if len(b) <= 32:
            return b
        return b[:31].rsplit(" ", 1)[0].rstrip(",&") + "…"

    @property
    def kurzname(self) -> str:
        return re.sub(r",?\s+(Inc|Corp|Corporation|Co|Ltd|plc|N\.V|S\.A|Holdings?)\.?$", "", self.name).strip()


def firma_aus(d: Mapping[str, Any]) -> Firma:
    f = d["firma"]
    felder = set(Jahr.__dataclass_fields__)
    jahre = [Jahr(**{k: v for k, v in j.items() if k in felder}) for j in d["jahre"]]
    if len(jahre) < 2:
        raise ValueError("fewer than two fiscal years — nothing to show")
    return Firma(woche=str(d["woche"]), name=str(f["name"]), ticker=str(f.get("ticker") or ""),
                 boerse=str(f.get("boerse") or ""), branche=str(f.get("branche") or ""),
                 stichtag=str(f.get("zehn_k_stichtag") or jahre[-1].ende), zehn_k_url=str(f.get("zehn_k_url") or ""),
                 jahre=jahre, abschnitte=dict(d.get("abschnitte") or {}), seite=str(d.get("seite") or ""))


# ---------------------------------------------------------------------------
# The script
# ---------------------------------------------------------------------------
@dataclass
class SzeneText:
    art: str
    headline: str


@dataclass
class Zahl:
    zahl: str
    zeile: str
    caption: str


@dataclass
class Frage:
    frage: str
    caption: str


@dataclass
class Begriff:
    begriff: str
    definition: str
    szene: SzeneText
    warum: str
    caption: str


@dataclass
class Reel2:
    unterzeile: str
    szenen: list[SzeneText]
    caption: str


@dataclass
class Drehbuch:
    woche: str
    titel: str
    unterzeile: str
    was: str
    szenen: list[SzeneText]
    dafuer: str
    dagegen: str
    caption: str
    hashtags: list[str] = field(default_factory=list)
    kicker: str = "Company of the week"
    schluss: str = "One company. Every week."
    marke: str = ""
    branche: str = ""
    zahlen: list[Zahl] = field(default_factory=list)
    frage: Optional[Frage] = None
    begriff: Optional[Begriff] = None
    reel2: Optional[Reel2] = None

    def als_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=1)

    def caption_voll(self, text: Optional[str] = None) -> str:
        tags = " ".join("#" + t.lstrip("#") for t in self.hashtags)
        return f"{(text or self.caption).strip()}\n\n{HINWEIS_CAPTION}" + (f"\n\n{tags}" if tags else "")

    def caption_fuer(self, art: str) -> str:
        if art in ("karussell", "reel"):
            return self.caption_voll()
        if art.startswith("zahl-"):
            return self.caption_voll(self.zahlen[int(art[5:]) - 1].caption)
        teil = {"frage": self.frage, "begriff": self.begriff, "reel2": self.reel2}[art]
        if teil is None:
            raise ValueError(f"the script has no {art!r} section yet")
        return self.caption_voll(teil.caption)


HINWEIS_CAPTION = "Source: the company's Form 10-K (SEC). Education, not investment advice."


def drehbuch_aus(d: Mapping[str, Any]) -> Drehbuch:
    szenen = [SzeneText(**s) for s in d.get("szenen") or []]
    besonders = {"szenen", "zahlen", "frage", "begriff", "reel2"}
    rest = {k: v for k, v in d.items() if k not in besonders and k in Drehbuch.__dataclass_fields__}
    b = d.get("begriff")
    r = d.get("reel2")
    return Drehbuch(
        szenen=szenen, zahlen=[Zahl(**z) for z in d.get("zahlen") or []],
        frage=Frage(**d["frage"]) if d.get("frage") else None,
        begriff=Begriff(**{**b, "szene": SzeneText(**b["szene"])}) if b else None,
        reel2=Reel2(**{**r, "szenen": [SzeneText(**x) for x in r["szenen"]]}) if r else None,
        **rest)


def _saetze(text: str, maximum: int) -> str:
    """The first whole sentences that fit into ``maximum`` characters."""
    aus = ""
    for satz in re.split(r"(?<=[.!?])\s+", " ".join((text or "").split())):
        if len(aus) + len(satz) + 1 > maximum:
            break
        aus = f"{aus} {satz}".strip()
    return aus or (text or "")[: maximum - 1].rsplit(" ", 1)[0] + "…"


def standard(firma: Firma) -> Drehbuch:
    """A plain script straight from the facts — the fallback and the tests' baseline."""
    j0, j1 = firma.jahre[0], firma.jahre[-1]
    n = len(firma.jahre) - 1
    szenen = [SzeneText("umsatz", f"Revenue: {geld(j0.umsatz)} to {geld(j1.umsatz)} in {n} years")]
    margen = [j.betriebsmarge for j in firma.jahre if j.betriebsmarge is not None]
    if len(margen) >= 2:
        spitze = max(margen)
        szenen.append(SzeneText("marge", f"Operating margin: {pct(margen[0])}, then {pct(spitze)}, now {pct(margen[-1])}"
                                if spitze not in (margen[0], margen[-1]) else
                                f"Operating margin: {pct(margen[0])} to {pct(margen[-1])}"))
    if j1.kasse is not None and j1.schulden is not None:
        szenen.append(SzeneText("bilanz", f"Cash {geld(j1.kasse)}, debt {geld(j1.schulden)}"))
    elif any(j.fcf is not None for j in firma.jahre):
        szenen.append(SzeneText("fcf", "Free cash flow each year"))
    ab = firma.abschnitte
    zahlen = [Zahl(geld_kurz(j1.umsatz), f"Revenue in fiscal {j1.ende[:4]}, up from {geld(j0.umsatz)} "
                   f"{n} years earlier.", f"{firma.kurzname}: revenue from {geld(j0.umsatz)} to {geld(j1.umsatz)}.")]
    if j1.betriebsmarge is not None:
        zahlen.append(Zahl(pct(j1.betriebsmarge), f"Operating margin in fiscal {j1.ende[:4]}: what is left of each "
                           "dollar of sales after running the business.",
                           f"{firma.kurzname} keeps {pct(j1.betriebsmarge)} of revenue as operating profit."))
    else:
        zahlen.append(zahlen[0])
    marge_szene = next((s for s in szenen if s.art == "marge"), szenen[0])
    return Drehbuch(
        woche=firma.woche, titel=firma.kurzname, unterzeile="How it makes money, from its own annual reports",
        was=_saetze(ab.get("WHAT THEY DO", ""), MAX["was"]), szenen=szenen,
        dafuer=_saetze(ab.get("THE CASE FOR", ""), MAX["dafuer"]),
        dagegen=_saetze(ab.get("THE CASE AGAINST", ""), MAX["dagegen"]),
        caption=f"{firma.kurzname} ({firma.ticker}) in numbers from its own annual report. "
                + _saetze(ab.get("WHAT THE NUMBERS SAY", ""), 600),
        hashtags=["annualreport", "stocks", "investing101", "businessmodel"],
        marke=os.environ.get("IG_HANDLE", ""),
        zahlen=zahlen,
        frage=Frage(f"What would you look at first in {firma.kurzname}'s annual report?",
                    "One company, one question. Tell us in the comments."),
        begriff=Begriff("Operating margin", "Operating income divided by revenue: the share of sales left after "
                        "paying for products, staff, marketing and rent.", marge_szene,
                        "It shows whether growth makes money. Revenue can rise while the margin falls.",
                        f"Operating margin, explained with {firma.kurzname}."),
        reel2=Reel2("The same numbers, the other way round", list(reversed(szenen)),
                    f"{firma.kurzname}: the case against, in numbers."),
    )


# ---------------------------------------------------------------------------
# The check
# ---------------------------------------------------------------------------
_ZAHL = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?")


def _normiert(treffer: re.Match) -> str:
    ganz = treffer.group(1).replace(",", "")
    return f"{int(ganz)}.{treffer.group(2)}" if treffer.group(2) else str(int(ganz))


def erlaubte_zahlen(firma: Firma) -> set[str]:
    erlaubt = {str(i) for i in range(0, 11)}
    for text in firma.abschnitte.values():
        erlaubt |= {_normiert(m) for m in _ZAHL.finditer(text)}
    for j in firma.jahre:
        erlaubt |= {j.ende[:4], j.ende[2:4], j.ende[5:7], j.ende[8:10]}
        for wert in asdict(j).values():
            if isinstance(wert, (int, float)) and not isinstance(wert, bool):
                for form in (geld(wert), pct(wert), f"{wert / 1e9:.2f}", f"{wert / 1e6:.1f}", f"{wert * 100:.0f}"):
                    erlaubt |= {_normiert(m) for m in _ZAHL.finditer(form)}
    return erlaubt


def pruefe(firma: Firma, db: Drehbuch) -> list[str]:
    """Everything wrong with the script; empty means it may be published."""
    fehler: list[str] = []
    erlaubt = erlaubte_zahlen(firma)
    texte = {"titel": db.titel, "unterzeile": db.unterzeile, "was": db.was, "dafuer": db.dafuer,
             "dagegen": db.dagegen, "caption": db.caption, "schluss": db.schluss}
    texte.update({f"headline {s.art}": s.headline for s in db.szenen})
    for i, z in enumerate(db.zahlen, 1):
        texte.update({f"zahl-{i} zahl": z.zahl, f"zahl-{i} zeile": z.zeile, f"zahl-{i} caption": z.caption})
    if db.frage:
        texte.update({"frage": db.frage.frage, "frage caption": db.frage.caption})
    if db.begriff:
        texte.update({"begriff": db.begriff.begriff, "definition": db.begriff.definition, "warum": db.begriff.warum,
                      "begriff headline": db.begriff.szene.headline, "begriff caption": db.begriff.caption})
    if db.reel2:
        texte.update({"reel2 unterzeile": db.reel2.unterzeile, "reel2 caption": db.reel2.caption})
        texte.update({f"reel2 headline {s.art}": s.headline for s in db.reel2.szenen})
    for name, text in texte.items():
        schluessel = name.split()[-1] if " " in name else name
        grenze = MAX["headline"] if "headline" in name else MAX.get(schluessel, MAX.get(name, 2000))
        if not text.strip():
            fehler.append(f"{name} is empty")
        if len(text) > grenze:
            fehler.append(f"{name} has {len(text)} characters, at most {grenze}")
        fremd = sorted({_normiert(m) for m in _ZAHL.finditer(text)} - erlaubt)
        if fremd:
            fehler.append(f"{name}: numbers not in the 10-K figures: {', '.join(fremd)}")
        klein = text.lower()
        for wort in VERBOTEN + verbotene_namen():
            if re.search(rf"(?<![a-z]){re.escape(wort)}(?![a-z])", klein):
                fehler.append(f"{name}: forbidden wording “{wort}”")
    if db.woche != firma.woche:
        fehler.append(f"script is for {db.woche}, the company is {firma.woche}")
    if not 2 <= len(db.szenen) <= 4:
        fehler.append("between 2 and 4 chart scenes")
    for s in db.szenen:
        if s.art not in SZENEN_ARTEN:
            fehler.append(f"unknown chart {s.art!r} — allowed: {', '.join(SZENEN_ARTEN)}")
    if len(db.hashtags) > MAX_HASHTAGS:
        fehler.append(f"{len(db.hashtags)} hashtags, at most {MAX_HASHTAGS}")
    for t in db.hashtags:
        if not re.fullmatch(r"#?[A-Za-z0-9_]{2,30}", t):
            fehler.append(f"hashtag {t!r} — letters, digits and _ only")
    return fehler
