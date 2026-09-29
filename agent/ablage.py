"""ablage.py — where the pictures live while Instagram fetches them.

Meta fetches every image and video from a public web address. This repository is
public; after a push, jsDelivr serves any file of any commit with the right content
type: ``https://cdn.jsdelivr.net/gh/<owner>/<repo>@<commit>/<path>``. Pinned to the
commit, the address never changes and never points at a newer file.
"""
from __future__ import annotations

import os
import subprocess
import urllib.request
from pathlib import Path
from typing import Callable, Optional, Sequence

CDN = "https://cdn.jsdelivr.net/gh/{repo}@{commit}/{pfad}"
ERWARTET = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".mp4": "video/mp4"}


class AblageFehler(RuntimeError):
    pass


def repo() -> str:
    r = os.environ.get("MEDIEN_REPO", "")
    if not r or r.count("/") != 1:
        raise AblageFehler("MEDIEN_REPO must be set to owner/name of this public repository")
    return r


def _git(*args: str, cwd: Optional[Path] = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def veroeffentliche(dateien: Sequence[Path], nachricht: str, *, wurzel: Path) -> str:
    """Commit and push the files; returns the commit."""
    relativ = [str(p.relative_to(wurzel)) for p in dateien]
    _git("add", *relativ, cwd=wurzel)
    if _git("status", "--porcelain", *relativ, cwd=wurzel):
        _git("commit", "-m", nachricht, cwd=wurzel)
    ast = _git("rev-parse", "--abbrev-ref", "HEAD", cwd=wurzel)
    _git("push", "origin", ast, cwd=wurzel)
    return _git("rev-parse", "HEAD", cwd=wurzel)


def adresse(pfad: str, commit: str, *, repo_name: Optional[str] = None) -> str:
    return CDN.format(repo=repo_name or repo(), commit=commit, pfad=pfad.lstrip("/"))


def _kopf(url: str) -> tuple[int, str]:
    anfrage = urllib.request.Request(url, method="GET", headers={"User-Agent": "weekly-10k-agent/1.0"})
    with urllib.request.urlopen(anfrage, timeout=60) as a:
        a.read(1024)
        return a.status, a.headers.get("Content-Type", "")


def pruefe_erreichbar(urls: Sequence[str], *, hole: Callable[[str], tuple[int, str]] = _kopf) -> list[str]:
    """Fetch each address once (warms the CDN) and check the content type Meta needs."""
    fehler = []
    for url in urls:
        try:
            status, art = hole(url)
        except Exception as exc:  # noqa: BLE001
            fehler.append(f"{url}: {type(exc).__name__}")
            continue
        endung = Path(url).suffix.lower()
        if status != 200:
            fehler.append(f"{url}: HTTP {status}")
        elif endung in ERWARTET and not art.startswith(ERWARTET[endung]):
            fehler.append(f"{url}: content type {art!r}, expected {ERWARTET[endung]}")
    return fehler
