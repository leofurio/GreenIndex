"""Recupero del codice di un repository GitHub senza il binario `git`.

Pensato per ambienti serverless (es. Vercel) dove `git` non è disponibile e il
filesystem è di sola lettura tranne /tmp. Scarica il tarball del repository via
HTTPS dall'API di GitHub e lo estrae in modo sicuro in una cartella temporanea.

Sicurezza (importante per un deploy pubblico):
* sono ammessi solo host noti (github.com) -> mitiga SSRF;
* owner/repo sono validati con una whitelist di caratteri;
* il download è limitato in dimensione;
* l'estrazione rifiuta path assoluti o traversal ("..") e limita numero di
  file e byte totali (mitiga "tar bomb").
"""

from __future__ import annotations

import io
import os
import re
import tarfile
import tempfile
import urllib.error
import urllib.request
from typing import Optional, Tuple
from urllib.parse import urlparse

ALLOWED_HOSTS = {"github.com", "www.github.com"}
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

# Limiti di sicurezza per l'ambiente hosted.
MAX_DOWNLOAD_BYTES = 30 * 1024 * 1024     # 30 MB di tarball compresso
MAX_EXTRACTED_BYTES = 200 * 1024 * 1024   # 200 MB estratti
MAX_EXTRACTED_FILES = 6000
DOWNLOAD_TIMEOUT = 20                       # secondi


class FetchError(Exception):
    """Errore "amichevole" da mostrare all'utente."""


def parse_github_target(target: str) -> Optional[Tuple[str, str]]:
    """Estrae (owner, repo) da un URL GitHub o da una scorciatoia owner/repo."""
    target = (target or "").strip()
    if not target:
        return None

    # Scorciatoia "owner/repo" (senza schema e senza spazi).
    if "://" not in target and "@" not in target and target.count("/") == 1:
        owner, repo = target.split("/")
        repo = repo[:-4] if repo.endswith(".git") else repo
        if _NAME_RE.match(owner) and _NAME_RE.match(repo):
            return owner, repo
        return None

    # URL completo.
    url = target if "://" in target else "https://" + target
    parsed = urlparse(url)
    if parsed.hostname not in ALLOWED_HOSTS:
        return None
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1]
    repo = repo[:-4] if repo.endswith(".git") else repo
    if _NAME_RE.match(owner) and _NAME_RE.match(repo):
        return owner, repo
    return None


def _download(owner: str, repo: str, token: Optional[str]) -> bytes:
    api_url = f"https://api.github.com/repos/{owner}/{repo}/tarball"
    headers = {
        "User-Agent": "GreenIndex",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(api_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT) as resp:
            data = b""
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                data += chunk
                if len(data) > MAX_DOWNLOAD_BYTES:
                    raise FetchError(
                        "Il repository è troppo grande per la demo online "
                        f"(> {MAX_DOWNLOAD_BYTES // (1024 * 1024)} MB)."
                    )
            return data
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise FetchError("Repository non trovato (o privato).") from exc
        if exc.code in (403, 429):
            raise FetchError(
                "Limite di richieste a GitHub raggiunto. Riprova più tardi "
                "(o configura la variabile d'ambiente GITHUB_TOKEN)."
            ) from exc
        raise FetchError(f"Errore da GitHub: HTTP {exc.code}.") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise FetchError(f"Download non riuscito: {exc}.") from exc


def _safe_extract(data: bytes, dest: str) -> None:
    total = 0
    count = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        for member in tar:
            if not (member.isfile() or member.isdir()):
                continue  # salta link simbolici/hard e device
            name = member.name
            # Rifiuta path assoluti o traversal.
            if name.startswith("/") or ".." in name.split("/"):
                continue
            target_path = os.path.realpath(os.path.join(dest, name))
            if not target_path.startswith(os.path.realpath(dest) + os.sep) and target_path != os.path.realpath(dest):
                continue
            if member.isdir():
                os.makedirs(target_path, exist_ok=True)
                continue
            count += 1
            total += member.size
            if count > MAX_EXTRACTED_FILES:
                raise FetchError("Il repository contiene troppi file per la demo online.")
            if total > MAX_EXTRACTED_BYTES:
                raise FetchError("Il repository è troppo grande una volta estratto.")
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            with open(target_path, "wb") as fh:
                fh.write(extracted.read())


def fetch_github_repo(target: str, token: Optional[str] = None) -> Tuple[str, str]:
    """Scarica ed estrae un repo GitHub. Restituisce (percorso_locale, etichetta).

    Il chiamante è responsabile della rimozione della cartella temporanea.
    """
    parsed = parse_github_target(target)
    if parsed is None:
        raise FetchError(
            "Indica un repository GitHub valido (es. "
            "https://github.com/utente/repo oppure utente/repo)."
        )
    owner, repo = parsed
    data = _download(owner, repo, token)
    tmp = tempfile.mkdtemp(prefix="greenindex_gh_")
    _safe_extract(data, tmp)
    return tmp, f"github.com/{owner}/{repo}"
