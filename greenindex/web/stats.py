"""Contatore persistente degli utilizzi della dashboard.

Tiene traccia di due numeri da mostrare in homepage:

* **repo analizzati**: quante analisi di repository sono state eseguite;
* **kWh "ottimizzati"**: la somma delle stime *illustrative* di consumo
  (``GreenIndexResult.illustrative_kwh``) rilevate nelle analisi. È lo stesso
  ordine di grandezza didattico spiegato nella pagina ``/rules``: NON una
  misura scientifica, ma il potenziale di risparmio che le violazioni
  segnalate rappresentano.

Backend (scelto automaticamente in base all'ambiente):

* **KV REST** (consigliato in produzione su Vercel): se sono presenti le
  variabili d'ambiente ``KV_REST_API_URL`` e ``KV_REST_API_TOKEN`` (convenzione
  Vercel KV / Upstash Redis) il contatore è condiviso e persistente tra le
  invocazioni serverless. Usa la REST API tramite ``urllib`` — nessuna
  dipendenza aggiuntiva.
* **File JSON** (default locale): scrive su ``GREENINDEX_STATS_FILE`` oppure in
  una posizione temporanea. Persiste in locale; su serverless è effimero (per
  istanza), quindi va inteso come fallback "best effort".
* **Memoria**: ultimo fallback se il file non è scrivibile.

In ogni caso la registrazione è "best effort": un errore dello store non deve
mai far fallire un'analisi (vedi :meth:`StatsStore.record`).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Stats:
    """Totali cumulativi mostrati in homepage."""

    repos: int = 0
    kwh: float = 0.0


# Chiavi usate dal backend KV.
_KEY_REPOS = "greenindex:stats:repos"
_KEY_KWH = "greenindex:stats:kwh"


class StatsStore:
    """Interfaccia comune dei backend."""

    def record(self, kwh: float) -> None:
        """Registra un'analisi (repo +1, kWh += ``kwh``). Best effort."""
        try:
            self._record(max(kwh, 0.0))
        except Exception:  # noqa: BLE001 - le statistiche non devono mai rompere l'analisi
            pass

    def snapshot(self) -> Stats:
        """Totali correnti. In caso di errore restituisce zeri."""
        try:
            return self._snapshot()
        except Exception:  # noqa: BLE001
            return Stats()

    # Da implementare nelle sottoclassi.
    def _record(self, kwh: float) -> None:  # pragma: no cover - interfaccia
        raise NotImplementedError

    def _snapshot(self) -> Stats:  # pragma: no cover - interfaccia
        raise NotImplementedError


class MemoryStatsStore(StatsStore):
    """Contatore in memoria di processo (si azzera al riavvio)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._repos = 0
        self._kwh = 0.0

    def _record(self, kwh: float) -> None:
        with self._lock:
            self._repos += 1
            self._kwh += kwh

    def _snapshot(self) -> Stats:
        with self._lock:
            return Stats(repos=self._repos, kwh=self._kwh)


class FileStatsStore(StatsStore):
    """Contatore su file JSON con scrittura atomica e lock di processo."""

    def __init__(self, path: str) -> None:
        self._path = path
        self._lock = threading.Lock()

    def _read(self) -> Stats:
        try:
            with open(self._path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return Stats(repos=int(data.get("repos", 0)),
                         kwh=float(data.get("kwh", 0.0)))
        except (OSError, ValueError, TypeError):
            return Stats()

    def _record(self, kwh: float) -> None:
        with self._lock:
            current = self._read()
            updated = Stats(repos=current.repos + 1, kwh=current.kwh + kwh)
            directory = os.path.dirname(self._path) or "."
            os.makedirs(directory, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=directory, prefix=".stats-", suffix=".json")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump({"repos": updated.repos, "kwh": updated.kwh}, fh)
                os.replace(tmp, self._path)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)

    def _snapshot(self) -> Stats:
        with self._lock:
            return self._read()


class KvStatsStore(StatsStore):
    """Backend basato su KV REST (Vercel KV / Upstash Redis).

    Usa i comandi atomici ``INCR`` e ``INCRBYFLOAT`` per evitare race tra
    istanze serverless. Le chiamate hanno un timeout breve: se il KV non
    risponde, la registrazione viene saltata silenziosamente (best effort).
    """

    def __init__(self, base_url: str, token: str, timeout: float = 3.0) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout

    def _call(self, *parts: str):
        from urllib.parse import quote
        from urllib.request import Request, urlopen

        url = self._base + "/" + "/".join(quote(str(p), safe="") for p in parts)
        req = Request(url, headers={"Authorization": f"Bearer {self._token}"})
        with urlopen(req, timeout=self._timeout) as resp:  # noqa: S310 - host da env affidabile
            payload = json.loads(resp.read().decode("utf-8"))
        return payload.get("result")

    def _record(self, kwh: float) -> None:
        self._call("incr", _KEY_REPOS)
        # INCRBYFLOAT con incremento 0 lascerebbe comunque traccia; saltiamo se 0.
        if kwh:
            self._call("incrbyfloat", _KEY_KWH, repr(float(kwh)))

    def _snapshot(self) -> Stats:
        result = self._call("mget", _KEY_REPOS, _KEY_KWH)
        repos_raw, kwh_raw = (result or [None, None])[:2]
        repos = int(repos_raw) if repos_raw not in (None, "") else 0
        kwh = float(kwh_raw) if kwh_raw not in (None, "") else 0.0
        return Stats(repos=repos, kwh=kwh)


def _default_file_path(hosted: bool) -> str:
    explicit = os.environ.get("GREENINDEX_STATS_FILE")
    if explicit:
        return explicit
    return os.path.join(tempfile.gettempdir(), "greenindex-stats.json")


def create_stats_store(config: Optional[dict] = None) -> StatsStore:
    """Sceglie il backend più adatto all'ambiente corrente."""
    config = config or {}
    kv_url = os.environ.get("KV_REST_API_URL")
    kv_token = os.environ.get("KV_REST_API_TOKEN")
    if kv_url and kv_token:
        return KvStatsStore(kv_url, kv_token)

    path = _default_file_path(bool(config.get("HOSTED")))
    store = FileStatsStore(path)
    # Verifica che il percorso sia scrivibile; altrimenti ripiega in memoria.
    try:
        directory = os.path.dirname(path) or "."
        os.makedirs(directory, exist_ok=True)
        if not os.access(directory, os.W_OK):
            raise OSError("directory non scrivibile")
    except OSError:
        return MemoryStatsStore()
    return store
