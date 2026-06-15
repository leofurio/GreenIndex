"""Entrypoint serverless per Vercel (runtime @vercel/python).

Vercel rileva la variabile WSGI ``app`` a livello di modulo e la serve.
Tutte le richieste vengono instradate qui da ``vercel.json``.
"""

import os
import sys

# Rende importabile il pacchetto `greenindex` situato alla radice del progetto.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from greenindex.web.app import create_app  # noqa: E402

# Modalità hosted: nessun accesso al filesystem dell'utente, CSS inlineato.
app = create_app({"HOSTED": True, "INLINE_CSS": True})

# Alias comune per alcuni handler.
application = app
