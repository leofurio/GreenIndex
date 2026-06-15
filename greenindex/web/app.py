"""Dashboard web di GreenIndex basata su Flask.

NOTA DI SICUREZZA: questo strumento legge percorsi locali e può clonare URL
git arbitrari. È pensato per l'uso in locale/CI da parte di sviluppatori.
Non esporlo su una rete non fidata senza adeguati controlli di accesso.
"""

from __future__ import annotations

import os
from typing import Optional

from ..analyzer import Analyzer
from ..cli import _is_url, _resolve_repo
from ..report import build_context, register_filters, to_json_dict
from ..scoring import compute_green_index


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
    if config:
        app.config.update(config)

    register_filters(app.jinja_env)

    def _analyze_target(target: str):
        with _resolve_repo(target) as (local_path, label):
            analyzer = Analyzer()
            result = analyzer.analyze(local_path)
            index = compute_green_index(result)
            display = label if _is_url(target) else (
                os.path.basename(os.path.normpath(local_path)) or local_path
            )
            return index, result, display

    @app.route("/")
    def home():
        return render_template("index.html", default_path=os.getcwd())

    @app.route("/analyze", methods=["POST"])
    def analyze():
        target = (request.form.get("target") or "").strip()
        if not target:
            return render_template(
                "index.html",
                default_path=os.getcwd(),
                error="Inserisci un percorso locale o un URL di repository.",
            )
        try:
            index, result, display = _analyze_target(target)
        except Exception as exc:  # noqa: BLE001
            return render_template(
                "index.html",
                default_path=os.getcwd(),
                error=f"Analisi non riuscita: {exc}",
            )
        context = build_context(index, result, display)
        context["standalone"] = False
        context["inline_css"] = None
        return render_template("report.html", **context)

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
            index, result, display = _analyze_target(target)
        except Exception as exc:  # noqa: BLE001
            return jsonify({"error": str(exc)}), 400
        return jsonify(to_json_dict(index, result, display))

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}

    return app


# Comodo per `flask --app greenindex.web.app run`.
app = None


def _get_app():  # pragma: no cover
    global app
    if app is None:
        app = create_app()
    return app
