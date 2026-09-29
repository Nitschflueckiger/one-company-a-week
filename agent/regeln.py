"""regeln.py — what a reply to a comment or a direct message may say.

The agent answers strangers on its own. These checks run before anything is sent;
a reply that fails is not sent, whatever the agent thinks of it.
"""
from __future__ import annotations

import re

from agent.drehbuch import VERBOTEN, verbotene_namen

MAX_KOMMENTAR = 300
MAX_NACHRICHT_BYTES = 1000

#: The one answer to “should I buy it?”, “what do you think of X?”, “is this a good investment?”.
KEIN_RAT = ("We don't give personal investment advice — we only walk through what a company's own annual "
            "report says. Everything in the post is from its Form 10-K.")

_LINK = re.compile(r"(https?://|www\.|\b[a-z0-9-]+\.(com|ch|net|org|io|co|app|de|fr|it)\b)", re.I)
_MAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_TELEFON = re.compile(r"\+?\d[\d\s/-]{7,}\d")


def pruefe_antwort(text: str, *, art: str = "kommentar") -> list[str]:
    """Everything wrong with a reply; empty means it may go out. ``art``: kommentar or nachricht."""
    fehler: list[str] = []
    t = text.strip()
    if not t:
        return ["empty reply"]
    if art == "kommentar" and len(t) > MAX_KOMMENTAR:
        fehler.append(f"{len(t)} characters, a comment reply is at most {MAX_KOMMENTAR}")
    if art == "nachricht" and len(t.encode("utf-8")) > MAX_NACHRICHT_BYTES:
        fehler.append(f"a message is at most {MAX_NACHRICHT_BYTES} bytes")
    klein = t.lower()
    for wort in VERBOTEN + verbotene_namen():
        if re.search(rf"(?<![a-z]){re.escape(wort)}(?![a-z])", klein):
            fehler.append(f"forbidden wording “{wort}”")
    if _LINK.search(t):
        fehler.append("no links — not ours, not anyone's")
    if _MAIL.search(t) or _TELEFON.search(t):
        fehler.append("no e-mail addresses or phone numbers")
    return fehler
