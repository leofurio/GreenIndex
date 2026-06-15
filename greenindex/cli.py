"""Interfaccia a riga di comando di GreenIndex.

Esempi:
    greenindex analyze .                      analizza la cartella corrente
    greenindex analyze /path/to/repo --html report.html
    greenindex analyze https://github.com/u/r.git --json out.json
    greenindex analyze . --min-score 70       esce con codice 1 se sotto soglia (CI)
    greenindex serve                          avvia la dashboard web
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from typing import Iterator, Optional, Tuple

from . import __version__
from .analyzer import Analyzer
from .report import render_html, render_terminal, to_json_dict
from .scoring import compute_green_index


def _is_url(value: str) -> bool:
    return (
        value.startswith(("http://", "https://", "git://", "ssh://", "git@"))
        or value.endswith(".git")
    )


@contextmanager
def _resolve_repo(target: str) -> Iterator[Tuple[str, str]]:
    """Restituisce (percorso_locale, etichetta). Clona se è un URL git."""
    if _is_url(target):
        tmp = tempfile.mkdtemp(prefix="greenindex_")
        try:
            print(f"Clonazione di {target} …", file=sys.stderr)
            subprocess.run(
                ["git", "clone", "--depth", "1", "--quiet", target, tmp],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            yield tmp, target
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        yield target, os.path.abspath(target)


def _run_analyze(args: argparse.Namespace) -> int:
    try:
        with _resolve_repo(args.target) as (local_path, label):
            analyzer = Analyzer()
            result = analyzer.analyze(local_path)
            index = compute_green_index(result, k=args.k)

            # Etichetta più leggibile: per i path locali mostra il nome cartella.
            display = label if _is_url(args.target) else os.path.basename(os.path.normpath(local_path)) or local_path

            if not args.quiet:
                print(render_terminal(index, result, display, color=not args.no_color))

            if args.json:
                payload = to_json_dict(index, result, display)
                _write(args.json, json.dumps(payload, indent=2, ensure_ascii=False))
                print(f"Report JSON scritto in {args.json}", file=sys.stderr)

            if args.html:
                html = render_html(index, result, display)
                _write(args.html, html)
                print(f"Report HTML scritto in {args.html}", file=sys.stderr)

            if result.errors and not args.quiet:
                print(f"\n  ⚠ {len(result.errors)} avvisi durante l'analisi.", file=sys.stderr)

            if args.min_score is not None and index.score < args.min_score:
                print(
                    f"GreenIndex {index.score} < soglia {args.min_score}: build non superata.",
                    file=sys.stderr,
                )
                return 1
            return 0
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        print(f"Errore durante la clonazione del repository:\n{stderr}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print("Errore: 'git' non è installato o non è nel PATH.", file=sys.stderr)
        return 2


def _run_serve(args: argparse.Namespace) -> int:
    try:
        from .web.app import create_app
    except ImportError:
        print(
            "Flask non è installato. Installa con: pip install 'greenindex[web]'",
            file=sys.stderr,
        )
        return 2
    app = create_app()
    print(f"GreenIndex web su http://{args.host}:{args.port}", file=sys.stderr)
    app.run(host=args.host, port=args.port, debug=args.debug)
    return 0


def _write(path: str, content: str) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="greenindex",
        description="Calcola il KPI GreenIndex di un repository in base alle "
                    "violazioni di regole di consumo tecnologico.",
    )
    parser.add_argument("--version", action="version", version=f"greenindex {__version__}")
    sub = parser.add_subparsers(dest="command")

    analyze = sub.add_parser("analyze", help="Analizza un repository (path o URL git).")
    analyze.add_argument("target", help="Percorso locale o URL del repository.")
    analyze.add_argument("--json", metavar="FILE", help="Scrive un report JSON.")
    analyze.add_argument("--html", metavar="FILE", help="Scrive un report HTML.")
    analyze.add_argument("--min-score", type=float, metavar="N",
                         help="Esce con codice 1 se il GreenIndex è sotto questa soglia (per CI).")
    analyze.add_argument("-k", type=float, default=1.0,
                         help="Costante di scala della penalità (default 1.0).")
    analyze.add_argument("--no-color", action="store_true", help="Disabilita i colori ANSI.")
    analyze.add_argument("--quiet", action="store_true", help="Non stampa il report a terminale.")
    analyze.set_defaults(func=_run_analyze)

    serve = sub.add_parser("serve", help="Avvia la dashboard web.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--debug", action="store_true")
    serve.set_defaults(func=_run_serve)

    return parser


def main(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
