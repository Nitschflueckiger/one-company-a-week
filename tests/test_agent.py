"""The agent without the network: facts from a fixture, Instagram as a fake."""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent import ablage, drehbuch as dbm, grafik, regeln
from agent import __main__ as cli
from agent.instagram import Instagram, InstagramFehler

HIER = Path(__file__).parent


@pytest.fixture()
def firma() -> dbm.Firma:
    return dbm.firma_aus(json.loads((HIER / "company-2026-W40.json").read_text(encoding="utf-8")))


# -- script ---------------------------------------------------------------------
def test_standard_skript_besteht(firma):
    db = dbm.standard(firma)
    assert dbm.pruefe(firma, db) == []
    assert db.titel == "e.l.f. Beauty" and [s.art for s in db.szenen] == ["umsatz", "marge", "bilanz"]


def test_fremde_zahl_und_ratschlag_werden_abgelehnt(firma):
    db = dbm.standard(firma)
    db.unterzeile = "Revenue up 312% — time to buy"
    fehler = " ".join(dbm.pruefe(firma, db))
    assert "312" in fehler and "time to buy" in fehler


def test_sie_verkaufen_ist_kein_ratschlag(firma):
    db = dbm.standard(firma)
    db.was = "They sell makeup at low prices and hold a lot of shelf space."
    assert dbm.pruefe(firma, db) == []


def test_wer_dahinter_steht_bleibt_ungesagt(firma, monkeypatch):
    db = dbm.standard(firma)
    db.caption = "Our fund looked at this one."
    assert any("our fund" in f for f in dbm.pruefe(firma, db))
    monkeypatch.setenv("VERBOTENE_NAMEN", "Acme Capital, Zeus")
    db.caption = "Brought to you by acme capital."
    assert any("acme capital" in f for f in dbm.pruefe(firma, db))
    assert regeln.pruefe_antwort("Zeus runs this page")


def test_hashtags_und_woche(firma):
    db = dbm.standard(firma)
    db.hashtags = [f"tag{i}" for i in range(9)]
    db.woche = "2026-W41"
    fehler = " ".join(dbm.pruefe(firma, db))
    assert "hashtags" in fehler and "2026-W41" in fehler


def test_caption_traegt_hinweis_und_marke(firma):
    text = cli.caption(dbm.standard(firma))
    assert "not investment advice" in text and text.endswith("Company of the week · 2026-W40 · karussell")


# -- replies --------------------------------------------------------------------
def test_kein_rat_besteht_selbst():
    assert regeln.pruefe_antwort(regeln.KEIN_RAT) == []


@pytest.mark.parametrize("text, teil", [
    ("Buy now before earnings!", "buy now"),
    ("Details on www.example.com", "links"),
    ("Write to me at a@b.ch", "e-mail"),
    ("x" * 301, "at most 300"),
])
def test_antworten_werden_geprueft(text, teil):
    assert any(teil in f for f in regeln.pruefe_antwort(text))


# -- pictures -------------------------------------------------------------------
def test_karussell_sieben_folien_im_format(firma, tmp_path):
    pfade = grafik.speichere_karussell(grafik.karussell(firma, dbm.standard(firma)), tmp_path)
    from PIL import Image

    assert len(pfade) == 7
    for p in pfade:
        with Image.open(p) as b:
            assert b.size == grafik.KARUSSELL and b.format == "JPEG"


def test_reel_mit_tonspur(firma, tmp_path):
    import imageio_ffmpeg

    ziel = grafik.reel(firma, dbm.standard(firma), tmp_path / "reel.mp4", fps=4)
    info = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(ziel)], capture_output=True, text=True).stderr
    assert "Video: h264" in info and "1080x1920" in info and "Audio: aac" in info


# -- hosting --------------------------------------------------------------------
def test_adresse_und_inhaltstyp():
    url = ablage.adresse("docs/medien/2026-W40/folie-1.jpg", "abc123", repo_name="me/page")
    assert url == "https://cdn.jsdelivr.net/gh/me/page@abc123/docs/medien/2026-W40/folie-1.jpg"
    fehler = ablage.pruefe_erreichbar([url, url.replace("folie-1.jpg", "reel.mp4")],
                                      hole=lambda u: (200, "text/plain") if u.endswith(".mp4") else (200, "image/jpeg"))
    assert len(fehler) == 1 and "video/mp4" in fehler[0]


# -- Instagram ------------------------------------------------------------------
class Falsch:
    """Records calls, answers from a table keyed by (method, path-prefix)."""

    def __init__(self, antworten):
        self.antworten, self.rufe = antworten, []

    def __call__(self, methode, url, daten):
        pfad = url.split("/v25.0/", 1)[-1].split("?", 1)[0]
        self.rufe.append((methode, pfad, (daten or b"").decode()))
        for (m, praefix), antwort in self.antworten.items():
            if m == methode and pfad.startswith(praefix):
                status, koerper = antwort(pfad, daten) if callable(antwort) else antwort
                return status, json.dumps(koerper).encode()
        return 404, json.dumps({"error": {"message": f"no fake for {methode} {pfad}"}}).encode()


def test_karussell_ablauf():
    zaehler = iter(range(100))
    t = Falsch({
        ("POST", "42/media_publish"): (200, {"id": "M1"}),
        ("POST", "42/media"): lambda p, d: (200, {"id": f"C{next(zaehler)}"}),
        ("GET", "C"): (200, {"status_code": "FINISHED"}),
        ("GET", "M1"): (200, {"id": "M1", "permalink": "https://instagram.com/p/x"}),
    })
    ig = Instagram("42", "GEHEIM", transport=t, warte=lambda s: None)
    e = ig.karussell(["https://a/1.jpg", "https://a/2.jpg"], "caption")
    assert e["permalink"].endswith("/p/x")
    album = [r for r in t.rufe if r[0] == "POST" and "media_type=CAROUSEL" in r[2]]
    assert len(album) == 1 and "children=C0%2CC1" in album[0][2]


def test_token_steht_nie_in_einer_fehlermeldung():
    ig = Instagram("42", "GEHEIM", transport=lambda m, u, d: (400, json.dumps({"error": {"message": f"bad {u}"}}).encode()))
    with pytest.raises(InstagramFehler) as e:
        ig.ich()
    assert "GEHEIM" not in str(e.value)


def test_lage_findet_offenes_und_uebergeht_erledigtes(firma):
    jetzt = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    zeit = lambda h: (jetzt - timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%S+0000")
    t = Falsch({
        ("GET", "me/conversations"): (200, {"data": [{"id": "G1"}, {"id": "G2"}, {"id": "G3"}]}),
        ("GET", "me"): (200, {"username": "page", "followers_count": 10, "media_count": 1}),
        ("GET", "42/content_publishing_limit"): (200, {"data": [{"quota_usage": 1}]}),
        ("GET", "42/media"): (200, {"data": [
            {"id": "P1", "caption": "…\n\nCompany of the week · 2026-W40 · karussell", "media_type": "CAROUSEL_ALBUM",
             "media_product_type": "FEED", "timestamp": zeit(20), "comments_count": 3, "permalink": "https://ig/p1"}]}),
        ("GET", "P1/comments"): (200, {"data": [
            {"id": "K1", "text": "What is operating margin?", "username": "anna", "timestamp": zeit(5)},
            {"id": "K2", "text": "thanks", "username": "ben", "timestamp": zeit(6),
             "replies": {"data": [{"id": "R", "username": "page"}]}},
            {"id": "K3", "text": "scam", "username": "spam", "timestamp": zeit(7), "hidden": True}]}),
        ("GET", "G1"): (200, {"messages": {"data": [{"id": "N1", "from": {"id": "U1", "username": "cara"},
                                                     "message": "Should I buy ELF?", "created_time": zeit(2)}]}}),
        ("GET", "G2"): (200, {"messages": {"data": [{"id": "N2", "from": {"id": "42", "username": "page"},
                                                     "message": "answered", "created_time": zeit(1)}]}}),
        ("GET", "G3"): (200, {"messages": {"data": [{"id": "N3", "from": {"id": "U3", "username": "dan"},
                                                     "message": "old", "created_time": zeit(30)}]}}),
    })
    ig = Instagram("42", "T", transport=t, warte=lambda s: None)
    lage = cli.lage(ig, firma, jetzt=jetzt)
    assert lage["gepostet"]["karussell"]["id"] == "P1" and lage["gepostet"]["reel"] is None
    assert lage["stunden_seit_letztem_beitrag"] == 20.0
    assert [k["kommentar"] for k in lage["offene_kommentare"]] == ["K1"]
    assert [n["an"] for n in lage["offene_nachrichten"]] == ["U1"]


@pytest.mark.parametrize("art, anzahl, endung", [("zahl-1", 1, ".jpg"), ("zahl-2", 1, ".jpg"), ("frage", 1, ".jpg"),
                                                  ("begriff", 3, ".jpg"), ("karussell", 7, ".jpg")])
def test_jede_art_hat_ihre_bilder(firma, tmp_path, art, anzahl, endung):
    pfade = grafik.medien_fuer(firma, dbm.standard(firma), art, tmp_path)
    assert len(pfade) == anzahl and all(p.suffix == endung for p in pfade)


def test_jede_art_hat_ihre_caption(firma):
    db = dbm.drehbuch_aus(json.loads(dbm.standard(firma).als_json()))
    for art in dbm.ARTEN:
        assert cli.caption(db, art).endswith(f"· {art}") and "not investment advice" in cli.caption(db, art)
