"""Dashboard web di GreenIndex basata su Flask.

Due modalità:

* **locale** (default): analizza un percorso del filesystem o clona un URL git
  (richiede il binario `git`). Pensata per uso da sviluppatore/CI in locale.
* **hosted** (``HOSTED=True``): pensata per un deploy pubblico serverless
  (es. Vercel). Non legge il filesystem dell'utente: analizza un repository
  **GitHub pubblico** scaricandone il tarball via HTTPS, oppure uno **snippet**
  di codice incollato. Il CSS è inlineato (``INLINE_CSS=True``) per non dipendere
  dal serving dei file statici.

NOTA DI SICUREZZA: in modalità locale lo strumento legge percorsi locali e può
clonare URL git. Non esporlo su reti non fidate. In modalità hosted gli host
remoti sono limitati a una whitelist (vedi ``web/fetch.py``).
"""

from __future__ import annotations

import os
import shutil
from contextlib import contextmanager
from typing import Iterator, Optional, Tuple

from ..analyzer import Analyzer
from ..report import build_context, register_filters, to_json_dict
from ..scoring import compute_green_index
from .fetch import FetchError, fetch_github_repo, parse_github_target

# Linguaggi selezionabili per l'analisi di uno snippet.
SNIPPET_LANGUAGES = [
    ("python", "Python"), ("javascript", "JavaScript"), ("typescript", "TypeScript"),
    ("java", "Java"), ("c", "C"), ("cpp", "C++"), ("csharp", "C#"),
    ("go", "Go"), ("ruby", "Ruby"), ("php", "PHP"), ("sql", "SQL"),
    ("css", "CSS"), ("html", "HTML"),
]
MAX_SNIPPET_BYTES = 200_000


def create_app(config: Optional[dict] = None):
    try:
        from flask import Flask, jsonify, render_template, request
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Flask è richiesto per la dashboard web. Installa con: "
            "pip install 'greenindex[web]'"
        ) from exc

    here = os.path.dirname(__file__)
    app = Flask(
        __name__,
        template_folder=os.path.join(here, "templates"),
        static_folder=os.path.join(here, "static"),
    )
    app.config.setdefault("HOSTED", os.environ.get("GREENINDEX_HOSTED") == "1")
    app.config.setdefault("INLINE_CSS", app.config["HOSTED"])
    if config:
        app.config.update(config)

    register_filters(app.jinja_env)

    # CSS letto una sola volta per l'inlining (modalità hosted).
    css_text = ""
    css_path = os.path.join(here, "static", "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as fh:
            css_text = fh.read()

    @app.context_processor
    def _inject_globals():
        return {
            "hosted": app.config.get("HOSTED", False),
            "inline_css": css_text if app.config.get("INLINE_CSS") else None,
        }

    # ------------------------------------------------------------------ #
    @contextmanager
    def _resolve(target: str) -> Iterator[Tuple[str, str]]:
        """Risolve il target in (percorso_locale, etichetta) e fa pulizia."""
        if app.config.get("HOSTED"):
            path, label = fetch_github_repo(target, token=os.environ.get("GITHUB_TOKEN"))
            try:
                yield path, label
            finally:
                shutil.rmtree(path, ignore_errors=True)
        else:
            from ..cli import _is_url, _resolve_repo
            with _resolve_repo(target) as (path, raw_label):
                label = raw_label if _is_url(target) else (
                    os.path.basename(os.path.normpath(path)) or path
                )
                yield path, label

    def _analyze_repo(target: str):
        with _resolve(target) as (path, label):
            result = Analyzer().analyze(path)
            return compute_green_index(result), result, label

    # ------------------------------------------------------------------ #
    @app.route("/")
    def home():
        return render_template(
            "index.html",
            default_path=("" if app.config.get("HOSTED") else os.getcwd()),
            snippet_languages=SNIPPET_LANGUAGES,
        )

    @app.route("/analyze", methods=["POST"])
    def analyze():
        target = (request.form.get("target") or "").strip()
        if not target:
            return _home_error("Inserisci un repository da analizzare.")
        try:
            index, result, label = _analyze_repo(target)
        except FetchError as exc:
            return _home_error(str(exc))
        except Exception as exc:  # noqa: BLE001
            return _home_error(f"Analisi non riuscita: {exc}")
        return _render_report(index, result, label)

    @app.route("/analyze-snippet", methods=["POST"])
    def analyze_snippet():
        code = request.form.get("code") or ""
        language = (request.form.get("language") or "python").strip()
        if not code.strip():
            return _home_error("Incolla del codice da analizzare.")
        if len(code.encode("utf-8", "replace")) > MAX_SNIPPET_BYTES:
            return _home_error("Lo snippet è troppo grande (max ~200 KB).")
        valid = {v for v, _ in SNIPPET_LANGUAGES}
        if language not in valid:
            language = "python"
        ext = {"python": "py", "javascript": "js", "typescript": "ts", "java": "java",
               "c": "c", "cpp": "cpp", "csharp": "cs", "go": "go", "ruby": "rb",
               "php": "php", "sql": "sql", "css": "css", "html": "html"}.get(language, "txt")
        result = Analyzer().analyze_source(f"snippet.{ext}", code, language=language)
        index = compute_green_index(result)
        return _render_report(index, result, f"snippet · {language}")

    @app.route("/api/analyze", methods=["GET", "POST"])
    def api_analyze():
        if request.method == "POST":
            data = request.get_json(silent=True) or {}
            target = (data.get("target") or "").strip()
        else:
            target = (request.args.get("target") or "").strip()
        if not target:
            return jsonify({"error": "parametro 'target' mancante"}), 400
        try:
            index, result, label = _analyze_repo(target)
        except FetchError as exc:
            return jsonify({"error": str(exc)}), 400
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 400
        return jsonify(to_json_dict(index, result, label))

    @app.route("/healthz")
    def healthz():
        return {"status": "ok", "hosted": bool(app.config.get("HOSTED"))}

    # ------------------------------------------------------------------ #
    def _home_error(message: str):
        return render_template(
            "index.html",
            default_path=("" if app.config.get("HOSTED") else os.getcwd()),
            snippet_languages=SNIPPET_LANGUAGES,
            error=message,
        ), 400

    def _render_report(index, result, label):
        context = build_context(index, result, label)
        context["standalone"] = False
        return render_template("report.html", **context)

    return app


# Istanza pronta per server WSGI (es. Vercel / gunicorn).
def _make_default_app():  # pragma: no cover
    return create_app()
