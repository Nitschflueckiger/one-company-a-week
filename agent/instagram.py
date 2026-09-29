"""instagram.py — the Instagram API with Instagram Login (graph.instagram.com), nothing else.

Only what the agent needs: publish a carousel or a reel from public URLs, read its own
media, read and answer comments, hide spam, read and answer direct messages.
Every call goes through :class:`Instagram` with an injectable transport, so the tests
never touch the network. The token comes from the environment (``IG_TOKEN``) and is
never printed.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional, Sequence

HOST = "https://graph.instagram.com"
VERSION = "v25.0"
USER_AGENT = "weekly-10k-agent/1.0"

Transport = Callable[[str, str, Optional[bytes]], tuple[int, bytes]]


class InstagramFehler(RuntimeError):
    pass


def _netz(methode: str, url: str, daten: Optional[bytes]) -> tuple[int, bytes]:
    anfrage = urllib.request.Request(url, data=daten, method=methode, headers={"User-Agent": USER_AGENT})
    if daten is not None:
        anfrage.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(anfrage, timeout=60) as antwort:
            return antwort.status, antwort.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def _ohne_token(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


@dataclass
class Instagram:
    user_id: str
    token: str
    transport: Transport = _netz
    warte: Callable[[float], None] = time.sleep

    @classmethod
    def aus_umgebung(cls) -> "Instagram":
        uid, token = os.environ.get("IG_USER_ID", ""), os.environ.get("IG_TOKEN", "")
        if not uid or not token:
            raise InstagramFehler("IG_USER_ID and IG_TOKEN must be set in the cloud environment")
        return cls(uid, token)

    # -- plumbing -------------------------------------------------------------
    def _ruf(self, methode: str, pfad: str, parameter: Optional[Mapping[str, Any]] = None) -> Any:
        p = {k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in (parameter or {}).items()
             if v is not None}
        p["access_token"] = self.token
        kodiert = urllib.parse.urlencode(p)
        url = f"{HOST}/{VERSION}/{pfad.lstrip('/')}"
        if methode == "GET":
            status, roh = self.transport("GET", f"{url}?{kodiert}", None)
        else:
            status, roh = self.transport(methode, url, kodiert.encode())
        try:
            antwort = json.loads(roh or b"{}")
        except ValueError:
            antwort = {"raw": roh[:300].decode("utf-8", "replace")}
        if status >= 400 or (isinstance(antwort, dict) and "error" in antwort):
            fehler = antwort.get("error", antwort) if isinstance(antwort, dict) else antwort
            raise InstagramFehler(_ohne_token(f"{methode} {pfad} → {status}: {json.dumps(fehler)[:400]}", self.token))
        return antwort

    # -- account ----------------------------------------------------------------
    def ich(self) -> dict[str, Any]:
        return self._ruf("GET", "me", {"fields": "user_id,username,account_type,media_count,followers_count"})

    def limit(self) -> dict[str, Any]:
        d = self._ruf("GET", f"{self.user_id}/content_publishing_limit", {"fields": "quota_usage,config"})
        return (d.get("data") or [{}])[0]

    def medien(self, anzahl: int = 25) -> list[dict[str, Any]]:
        d = self._ruf("GET", f"{self.user_id}/media", {
            "fields": "id,caption,media_type,media_product_type,permalink,timestamp,comments_count,like_count",
            "limit": anzahl})
        return list(d.get("data") or [])

    # -- publishing -------------------------------------------------------------
    def _warte_fertig(self, container: str, *, versuche: int = 40, pause: float = 6.0) -> None:
        for _ in range(versuche):
            s = self._ruf("GET", container, {"fields": "status_code,status"})
            code = s.get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise InstagramFehler(f"container {container}: {code} {s.get('status', '')}")
            self.warte(pause)
        raise InstagramFehler(f"container {container} not ready after {versuche} checks")

    def _veroeffentliche(self, container: str) -> dict[str, Any]:
        d = self._ruf("POST", f"{self.user_id}/media_publish", {"creation_id": container})
        mid = d["id"]
        return self._ruf("GET", mid, {"fields": "id,permalink,timestamp,media_type,media_product_type"})

    def karussell(self, bild_urls: Sequence[str], caption: str) -> dict[str, Any]:
        if not 2 <= len(bild_urls) <= 10:
            raise InstagramFehler(f"a carousel takes 2 to 10 images, got {len(bild_urls)}")
        kinder = []
        for url in bild_urls:
            c = self._ruf("POST", f"{self.user_id}/media", {"image_url": url, "is_carousel_item": "true"})
            kinder.append(c["id"])
        for k in kinder:
            self._warte_fertig(k)
        album = self._ruf("POST", f"{self.user_id}/media",
                          {"media_type": "CAROUSEL", "children": ",".join(kinder), "caption": caption})
        self._warte_fertig(album["id"])
        return self._veroeffentliche(album["id"])

    def bild(self, bild_url: str, caption: str) -> dict[str, Any]:
        c = self._ruf("POST", f"{self.user_id}/media", {"image_url": bild_url, "caption": caption})
        self._warte_fertig(c["id"])
        return self._veroeffentliche(c["id"])

    def reel(self, video_url: str, caption: str, *, titelbild_ms: int = 1500) -> dict[str, Any]:
        c = self._ruf("POST", f"{self.user_id}/media", {"media_type": "REELS", "video_url": video_url,
                                                          "caption": caption, "share_to_feed": "true",
                                                          "thumb_offset": titelbild_ms})
        self._warte_fertig(c["id"], versuche=60, pause=10.0)
        return self._veroeffentliche(c["id"])

    # -- comments -----------------------------------------------------------------
    def kommentare(self, media_id: str) -> list[dict[str, Any]]:
        d = self._ruf("GET", f"{media_id}/comments", {
            "fields": "id,text,timestamp,username,from,hidden,replies{id,text,username,from,timestamp}", "limit": 50})
        return list(d.get("data") or [])

    def antworte(self, kommentar_id: str, text: str) -> dict[str, Any]:
        return self._ruf("POST", f"{kommentar_id}/replies", {"message": text})

    def verberge(self, kommentar_id: str, verbergen: bool = True) -> dict[str, Any]:
        return self._ruf("POST", kommentar_id, {"hide": "true" if verbergen else "false"})

    # -- direct messages ----------------------------------------------------------
    def gespraeche(self, anzahl: int = 20) -> list[dict[str, Any]]:
        d = self._ruf("GET", "me/conversations", {"platform": "instagram", "fields": "id,updated_time,participants",
                                                    "limit": anzahl})
        return list(d.get("data") or [])

    def nachrichten(self, gespraech_id: str) -> list[dict[str, Any]]:
        d = self._ruf("GET", gespraech_id, {"fields": "messages{id,created_time,from,to,message}"})
        return list((d.get("messages") or {}).get("data") or [])

    def schreibe(self, empfaenger: str, text: str) -> dict[str, Any]:
        if len(text.encode("utf-8")) > 1000:
            raise InstagramFehler("a message is at most 1000 bytes")
        return self._ruf("POST", f"{self.user_id}/messages", {"recipient": {"id": empfaenger}, "message": {"text": text}})

    # -- token --------------------------------------------------------------------
    def token_erneuern(self) -> dict[str, Any]:
        """Returns a NEW token (valid 60 days). The caller must store it — this agent cannot."""
        status, roh = self.transport("GET", f"{HOST}/refresh_access_token?grant_type=ig_refresh_token&"
                                            f"access_token={urllib.parse.quote(self.token)}", None)
        if status >= 400:
            raise InstagramFehler(f"refresh → {status}")
        return json.loads(roh)
