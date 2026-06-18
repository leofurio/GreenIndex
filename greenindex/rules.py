"""Definizione delle regole di consumo tecnologico (green coding rules).

Ogni :class:`Rule` descrive un anti-pattern che ha un impatto su consumo di
risorse o energia. Le regole sono il riferimento unico per nome, categoria,
gravità (peso) e suggerimento di rimedio; sia gli analizzatori sia i report
le leggono da qui.

Tipi di detector (`Rule.detector`):
    "regex"          -> pattern applicato riga per riga sul sorgente senza commenti
    "python_ast"     -> rilevatore basato su AST, gestito in analyzer (solo .py)
    "nested_loops"   -> rilevatore strutturale di cicli annidati (multi-linguaggio)
    "dependency"     -> scansione dei file di dipendenze (requirements/package.json)
    "asset"          -> scansione di asset binari di grandi dimensioni
    "dockerfile"     -> analisi specifica dei Dockerfile
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --------------------------------------------------------------------------- #
# Gravità (pesi di penalità). Numeri interi 1..5.
# --------------------------------------------------------------------------- #
SEV_LOW = 1
SEV_MINOR = 2
SEV_MEDIUM = 3
SEV_MAJOR = 4
SEV_HIGH = 5

SEVERITY_LABELS = {
    SEV_LOW: "info",
    SEV_MINOR: "minore",
    SEV_MEDIUM: "media",
    SEV_MAJOR: "alta",
    SEV_HIGH: "critica",
}

# --------------------------------------------------------------------------- #
# Categorie di impatto (con metadati per i report e la UI).
# --------------------------------------------------------------------------- #
CATEGORIES: Dict[str, Dict[str, str]] = {
    "compute": {"label": "Calcolo / CPU", "icon": "🔁", "color": "#e4572e"},
    "memory": {"label": "Memoria", "icon": "🧠", "color": "#f3a712"},
    "network": {"label": "Rete & I/O", "icon": "🌐", "color": "#2e86ab"},
    "data": {"label": "Dati & Storage", "icon": "🗄️", "color": "#8d6a9f"},
    "observability": {"label": "Osservabilità", "icon": "📝", "color": "#5b8c5a"},
    "dependencies": {"label": "Dipendenze", "icon": "📦", "color": "#b07156"},
    "energy": {"label": "Energia & Runtime", "icon": "⚡", "color": "#d64550"},
    "assets": {"label": "Asset", "icon": "🖼️", "color": "#5e7ce2"},
    "infra": {"label": "Infrastruttura", "icon": "🐳", "color": "#3a7ca5"},
    "sci": {"label": "Software Carbon Intensity (SCI)", "icon": "🌍", "color": "#1b998b"},
}


@dataclass(frozen=True)
class Rule:
    """Una regola di consumo tecnologico."""

    id: str
    name: str
    category: str
    severity: int
    description: str
    remediation: str
    detector: str = "regex"
    # Filtra i linguaggi a cui la regola si applica; vuoto = tutti.
    languages: Tuple[str, ...] = ()
    pattern: Optional[str] = None
    # Se valorizzato, la riga deve corrispondere a `pattern` ma NON contenere
    # questo secondo pattern (utile per "chiamata senza timeout", ecc.).
    require_absent: Optional[str] = None
    flags: int = 0

    @property
    def severity_label(self) -> str:
        return SEVERITY_LABELS.get(self.severity, str(self.severity))

    @property
    def category_label(self) -> str:
        return CATEGORIES.get(self.category, {}).get("label", self.category)


@dataclass
class Violation:
    """Una singola occorrenza di violazione di una regola."""

    rule_id: str
    path: str
    line: int
    column: int = 0
    snippet: str = ""
    message: str = ""
    extra: Dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Catalogo delle regole di default.
# --------------------------------------------------------------------------- #
DEFAULT_RULES: List[Rule] = [
    # ----------------------------- COMPUTE -------------------------------- #
    Rule(
        id="GC001",
        name="Cicli annidati",
        category="compute",
        severity=SEV_MEDIUM,
        detector="nested_loops",
        description=(
            "Cicli annidati producono complessità quadratica o peggiore e "
            "fanno crescere il consumo di CPU con la dimensione dei dati."
        ),
        remediation=(
            "Valuta strutture dati a lookup costante (set/dict), join o "
            "vettorizzazione per evitare il prodotto cartesiano."
        ),
    ),
    Rule(
        id="GC002",
        name="Concatenazione di stringhe in un ciclo",
        category="compute",
        severity=SEV_MINOR,
        detector="python_ast",
        languages=("python",),
        description=(
            "Concatenare stringhe con += dentro un ciclo crea molti oggetti "
            "temporanei e copie, sprecando CPU e memoria."
        ),
        remediation="Accumula in una lista e usa ''.join(parti) alla fine.",
    ),
    Rule(
        id="GC003",
        name="Busy-wait / polling attivo",
        category="compute",
        severity=SEV_MAJOR,
        detector="python_ast",
        languages=("python",),
        description=(
            "Un ciclo 'while True' con sleep tiene la CPU occupata in polling "
            "invece di restare in attesa di un evento."
        ),
        remediation=(
            "Usa meccanismi event-driven (queue, condition, async, webhook) "
            "al posto del polling continuo."
        ),
    ),
    # ----------------------------- MEMORY --------------------------------- #
    Rule(
        id="GC010",
        name="Lettura dell'intero file in memoria",
        category="memory",
        severity=SEV_MINOR,
        detector="regex",
        languages=("python", "javascript", "typescript", "php", "ruby"),
        pattern=r"\.readlines\(|\.read\(\s*\)|readFileSync\(|file_get_contents\(",
        description=(
            "Caricare interamente un file in memoria non scala: il consumo "
            "cresce con la dimensione del file."
        ),
        remediation="Elabora il file in streaming, riga per riga o a blocchi.",
    ),
    Rule(
        id="GC011",
        name="Risorsa file non chiusa (manca context manager)",
        category="memory",
        severity=SEV_MEDIUM,
        detector="python_ast",
        languages=("python",),
        description=(
            "open() senza 'with' rischia di lasciare descrittori di file "
            "aperti, trattenendo memoria e risorse del sistema operativo."
        ),
        remediation="Usa 'with open(...) as f:' per garantire la chiusura.",
    ),
    # ----------------------------- NETWORK -------------------------------- #
    Rule(
        id="GC020",
        name="Chiamata di rete dentro un ciclo",
        category="network",
        severity=SEV_MAJOR,
        detector="python_ast",
        languages=("python",),
        description=(
            "Effettuare richieste HTTP in un ciclo moltiplica latenza, "
            "traffico ed energia di rete."
        ),
        remediation=(
            "Raggruppa le chiamate (batch/bulk endpoint), usa richieste "
            "concorrenti o una cache."
        ),
    ),
    Rule(
        id="GC021",
        name="Query al database dentro un ciclo (N+1)",
        category="network",
        severity=SEV_MAJOR,
        detector="python_ast",
        languages=("python",),
        description=(
            "Il pattern N+1 esegue una query per ogni elemento, generando "
            "un carico inutile sul database."
        ),
        remediation=(
            "Usa eager loading / join / query in bulk per recuperare i dati "
            "in un'unica operazione."
        ),
    ),
    Rule(
        id="GC022",
        name="Richiesta HTTP senza timeout",
        category="network",
        severity=SEV_MINOR,
        detector="regex",
        languages=("python",),
        pattern=r"\brequests\.(get|post|put|delete|patch|head)\s*\(",
        require_absent=r"timeout",
        description=(
            "Richieste senza timeout possono bloccare thread e risorse a "
            "tempo indeterminato in caso di servizi lenti."
        ),
        remediation="Imposta sempre un timeout esplicito sulle chiamate di rete.",
    ),
    Rule(
        id="GC023",
        name="Richiesta HTTP JavaScript senza timeout/abort",
        category="network",
        severity=SEV_MINOR,
        detector="regex",
        languages=("javascript", "typescript"),
        pattern=r"\b(fetch|axios\.(get|post|put|delete|patch|request))\s*\(",
        require_absent=r"(timeout|signal|AbortController)",
        description=(
            "Chiamate HTTP JavaScript senza timeout o AbortController possono "
            "restare appese e trattenere risorse lato client/server."
        ),
        remediation=(
            "Configura un timeout esplicito o passa un AbortController/signal "
            "alla richiesta."
        ),
    ),
    # ------------------------------ DATA ---------------------------------- #
    Rule(
        id="GC030",
        name="SELECT * (query non selettiva)",
        category="data",
        severity=SEV_MINOR,
        detector="regex",
        languages=("sql", "python", "javascript", "typescript", "java", "php",
                   "ruby", "go", "csharp", "c", "cpp", "kotlin", "scala", "rust"),
        pattern=r"select\s+\*\s+from",
        flags=re.IGNORECASE,
        description=(
            "SELECT * trasferisce colonne non necessarie, aumentando I/O, "
            "rete e memoria."
        ),
        remediation="Seleziona esplicitamente solo le colonne necessarie.",
    ),
    Rule(
        id="GC031",
        name="Query senza WHERE/LIMIT",
        category="data",
        severity=SEV_MINOR,
        detector="regex",
        languages=("sql", "python", "javascript", "typescript", "java", "php",
                   "ruby", "go", "csharp", "c", "cpp", "kotlin", "scala", "rust"),
        pattern=r"select\s+.+\s+from\s+\w+\s*(;|\"|')",
        flags=re.IGNORECASE,
        description=(
            "Scansionare intere tabelle senza WHERE/LIMIT spreca I/O e "
            "memoria, specialmente su dataset grandi."
        ),
        remediation="Aggiungi clausole WHERE/LIMIT e indici appropriati.",
    ),
    Rule(
        id="GC032",
        name="UPDATE/DELETE senza WHERE",
        category="data",
        severity=SEV_MAJOR,
        detector="regex",
        languages=("sql", "python", "javascript", "typescript", "java", "php",
                   "ruby", "go", "csharp", "c", "cpp", "kotlin", "scala", "rust"),
        pattern=r"\b(update\s+\w+\s+set|delete\s+from\s+\w+)\b(?![^;\n]*(\bwhere\b|\blimit\b))",
        flags=re.IGNORECASE,
        description=(
            "UPDATE o DELETE non filtrati possono modificare/scansionare intere "
            "tabelle, generando I/O elevato e rischi operativi."
        ),
        remediation="Aggiungi WHERE/LIMIT e verifica che esistano indici adeguati.",
    ),
    # -------------------------- OBSERVABILITY ----------------------------- #
    Rule(
        id="GC040",
        name="Print/console.log di debug lasciato nel codice",
        category="observability",
        severity=SEV_LOW,
        detector="regex",
        languages=("python", "javascript", "typescript"),
        pattern=r"^\s*print\s*\(|console\.(log|debug|info)\s*\(",
        description=(
            "Output di debug in produzione genera I/O continuo e log "
            "voluminosi che consumano CPU e storage."
        ),
        remediation="Usa un logger configurabile e rimuovi i print di debug.",
    ),
    Rule(
        id="GC041",
        name="Logging in livello DEBUG/verboso",
        category="observability",
        severity=SEV_LOW,
        detector="regex",
        pattern=r"\b(logging|logger|log)\.debug\s*\(",
        description=(
            "Logging verboso lasciato attivo aumenta I/O su disco/rete e "
            "il volume di dati da conservare."
        ),
        remediation="Mantieni il livello DEBUG solo in sviluppo.",
    ),
    # --------------------------- DEPENDENCIES ----------------------------- #
    Rule(
        id="GC050",
        name="Import wildcard",
        category="dependencies",
        severity=SEV_LOW,
        detector="regex",
        languages=("python",),
        pattern=r"^\s*from\s+[\w\.]+\s+import\s+\*",
        description=(
            "'import *' carica simboli non necessari, aumentando memoria e "
            "tempo di import."
        ),
        remediation="Importa esplicitamente solo ciò che serve.",
    ),
    Rule(
        id="GC051",
        name="Dipendenza pesante",
        category="dependencies",
        severity=SEV_MINOR,
        detector="dependency",
        description=(
            "Alcune dipendenze hanno un footprint elevato (dimensione, "
            "memoria, tempo di avvio) e andrebbero usate solo se necessarie."
        ),
        remediation=(
            "Verifica se serve l'intera libreria o se esiste un'alternativa "
            "più leggera o un modulo della standard library."
        ),
    ),
    Rule(
        id="GC052",
        name="Versione dipendenza non vincolata",
        category="dependencies",
        severity=SEV_LOW,
        detector="dependency",
        description=(
            "Dipendenze senza vincolo o con wildcard/latest rendono le build "
            "meno riproducibili e possono causare download/ricostruzioni inutili."
        ),
        remediation=(
            "Fissa una versione o un range compatibile e aggiorna in modo "
            "controllato con lockfile."
        ),
    ),
    # ----------------------------- ENERGY --------------------------------- #
    Rule(
        id="GC060",
        name="Modalità debug abilitata",
        category="energy",
        severity=SEV_MEDIUM,
        detector="regex",
        languages=("python", "javascript", "typescript", "json", "yaml", "ini", "toml"),
        pattern=r"DEBUG\s*=\s*True|debug\s*=\s*True|[\"']debug[\"']\s*:\s*true",
        flags=re.IGNORECASE,
        description=(
            "La modalità debug in produzione disabilita ottimizzazioni e "
            "aumenta logging e consumo di risorse."
        ),
        remediation="Disabilita il debug in produzione tramite configurazione.",
    ),
    Rule(
        id="GC061",
        name="Animazione CSS infinita",
        category="energy",
        severity=SEV_MINOR,
        detector="regex",
        languages=("css", "html"),
        pattern=r"animation(-iteration-count)?\s*:[^;]*\binfinite\b",
        flags=re.IGNORECASE,
        description=(
            "Animazioni infinite tengono attivo il rendering della GPU/CPU "
            "anche quando non servono, consumando batteria."
        ),
        remediation=(
            "Limita la durata delle animazioni o sospendile quando non "
            "visibili (prefers-reduced-motion)."
        ),
    ),
    Rule(
        id="GC063",
        name="setInterval ad alta frequenza",
        category="energy",
        severity=SEV_MINOR,
        detector="regex",
        languages=("javascript", "typescript", "html"),
        pattern=r"setInterval\s*\([^,]+,\s*([0-9]{1,2})\s*\)",
        description=(
            "Timer con intervalli molto brevi (<100ms) impediscono alla CPU "
            "di restare idle e consumano energia."
        ),
        remediation=(
            "Aumenta l'intervallo o usa requestAnimationFrame/eventi al "
            "posto del polling continuo."
        ),
    ),
    Rule(
        id="GC062",
        name="Pattern di cryptomining",
        category="energy",
        severity=SEV_HIGH,
        detector="regex",
        # Richiede un contesto d'uso (keyword seguita da '.' o '/', es.
        # "CoinHive.Anonymous", "coinhive.min.js") per non segnalare semplici
        # elenchi di parole chiave.
        pattern=r"(coinhive|coin-hive|cryptonight|webminepool|coinimp|deepminer)\s*[./]",
        flags=re.IGNORECASE,
        description=(
            "Script di mining sfruttano la CPU dell'utente al massimo, con "
            "consumo energetico estremo."
        ),
        remediation="Rimuovi qualsiasi codice di mining non autorizzato.",
    ),
    # ----------------------------- ASSETS --------------------------------- #
    Rule(
        id="GC070",
        name="Asset di grandi dimensioni non ottimizzato",
        category="assets",
        severity=SEV_MINOR,
        detector="asset",
        description=(
            "Immagini e asset binari di grandi dimensioni aumentano banda, "
            "tempi di caricamento ed energia di trasferimento."
        ),
        remediation=(
            "Comprimi/ridimensiona le immagini e usa formati moderni "
            "(WebP/AVIF) o il lazy loading."
        ),
    ),
    # ------------------------------ INFRA --------------------------------- #
    Rule(
        id="GC080",
        name="Immagine Docker con tag non fissato (:latest)",
        category="infra",
        severity=SEV_LOW,
        detector="dockerfile",
        languages=("dockerfile",),
        description=(
            "Usare ':latest' (o nessun tag) rende le build non riproducibili "
            "e provoca download/ricostruzioni inutili."
        ),
        remediation="Fissa una versione specifica dell'immagine base.",
    ),
    Rule(
        id="GC081",
        name="Dockerfile senza multi-stage build",
        category="infra",
        severity=SEV_LOW,
        detector="dockerfile",
        languages=("dockerfile",),
        description=(
            "Senza multi-stage build l'immagine finale include toolchain e "
            "file di build, risultando più grande del necessario."
        ),
        remediation=(
            "Usa una multi-stage build per copiare nell'immagine finale solo "
            "gli artefatti necessari."
        ),
    ),
    # ===================================================================== #
    # Regole aggiuntive.
    # ===================================================================== #
    # ----------------------------- COMPUTE -------------------------------- #
    Rule(
        id="GC004",
        name="Regex (ri)compilata dentro un ciclo",
        category="compute",
        severity=SEV_MINOR,
        detector="python_ast",
        languages=("python",),
        description=(
            "Compilare o usare una regex (re.compile/search/match/sub/findall) "
            "dentro un ciclo ricompila il pattern a ogni iterazione, sprecando CPU."
        ),
        remediation=(
            "Compila la regex UNA volta con re.compile() fuori dal ciclo e "
            "riusa l'oggetto pattern al suo interno."
        ),
    ),
    Rule(
        id="GC005",
        name="time.sleep() in una funzione async",
        category="compute",
        severity=SEV_MEDIUM,
        detector="python_ast",
        languages=("python",),
        description=(
            "time.sleep() è bloccante: dentro una funzione 'async' ferma "
            "l'intero event loop, impedendo l'esecuzione di altre coroutine."
        ),
        remediation="Usa 'await asyncio.sleep(...)' al posto di time.sleep().",
    ),
    Rule(
        id="GC006",
        name="Iterazione pandas con iterrows()",
        category="compute",
        severity=SEV_MINOR,
        detector="regex",
        languages=("python",),
        pattern=r"\.iterrows\s*\(",
        description=(
            "iterrows() itera un DataFrame riga per riga in Python puro: è "
            "ordini di grandezza più lento (e più energivoro) delle operazioni "
            "vettorizzate."
        ),
        remediation=(
            "Usa operazioni vettorizzate di pandas/NumPy; se proprio necessario "
            "itera con itertuples(), più veloce di iterrows()."
        ),
    ),
    Rule(
        id="GC007",
        name="Ordinamento dentro un ciclo",
        category="compute",
        severity=SEV_MINOR,
        detector="python_ast",
        languages=("python",),
        description=(
            "Chiamare sorted() o list.sort() dentro un ciclo riordina i dati a "
            "ogni iterazione, con costo inutile O(n·m·log m)."
        ),
        remediation=(
            "Sposta l'ordinamento fuori dal ciclo (ordina una sola volta) o "
            "mantieni la struttura già ordinata."
        ),
    ),
    Rule(
        id="GC008",
        name="Appartenenza a lista/tupla letterale in un ciclo",
        category="compute",
        severity=SEV_LOW,
        detector="python_ast",
        languages=("python",),
        description=(
            "Il test 'x in [..]'/'x in (..)' su una lista o tupla è O(n); "
            "dentro un ciclo diventa O(n·m). Un set offre lookup O(1)."
        ),
        remediation=(
            "Definisci un set FUORI dal ciclo (es. VALIDI = {...}) e usa "
            "'x in VALIDI'."
        ),
    ),
    Rule(
        id="GC009",
        name="Ricorsione senza memoizzazione",
        category="compute",
        severity=SEV_MINOR,
        detector="python_ast",
        languages=("python",),
        description=(
            "Una funzione che richiama se stessa più volte senza cache può "
            "avere complessità esponenziale, ricalcolando gli stessi "
            "sottoproblemi."
        ),
        remediation=(
            "Aggiungi @functools.lru_cache/@cache, usa la programmazione "
            "dinamica o riscrivi in forma iterativa."
        ),
    ),
    # ----------------------------- MEMORY --------------------------------- #
    Rule(
        id="GC012",
        name="Materializzazione inutile di una lista",
        category="memory",
        severity=SEV_MINOR,
        detector="python_ast",
        languages=("python",),
        description=(
            "Passare una list-comprehension a sum/any/all/min/max/join crea "
            "una lista temporanea in memoria invece di consumare un generatore."
        ),
        remediation=(
            "Togli le parentesi quadre per usare una generator expression: "
            "es. sum(x for x in dati) invece di sum([x for x in dati])."
        ),
    ),
    Rule(
        id="GC013",
        name="copy.deepcopy() dentro un ciclo",
        category="memory",
        severity=SEV_MINOR,
        detector="python_ast",
        languages=("python",),
        description=(
            "deepcopy() alloca e copia ricorsivamente: dentro un ciclo "
            "moltiplica le allocazioni e la pressione sul garbage collector."
        ),
        remediation=(
            "Copia una sola volta fuori dal ciclo, usa una copia superficiale "
            "se sufficiente, o evita del tutto la copia."
        ),
    ),
    # ------------------------------ DATA ---------------------------------- #
    Rule(
        id="GC033",
        name="LIKE con wildcard iniziale",
        category="data",
        severity=SEV_MINOR,
        detector="regex",
        languages=("sql", "python", "javascript", "typescript", "java", "php",
                   "ruby", "go", "csharp", "c", "cpp", "kotlin", "scala", "rust"),
        pattern=r"like\s+['\"]%",
        flags=re.IGNORECASE,
        description=(
            "Un LIKE che inizia con '%' non può usare gli indici "
            "(non-sargable) e forza una scansione completa della tabella."
        ),
        remediation=(
            "Evita il wildcard iniziale, oppure usa un indice full-text/trigram "
            "per le ricerche di sottostringa."
        ),
    ),
    # -------------------------- OBSERVABILITY ----------------------------- #
    Rule(
        id="GC042",
        name="Messaggio di log formattato in modo eager",
        category="observability",
        severity=SEV_LOW,
        detector="regex",
        languages=("python",),
        pattern=r"\b(logging|logger|log)\.(debug|info|warning|error|critical|exception)\s*\(\s*f[\"']",
        description=(
            "Usare una f-string come messaggio di log costruisce la stringa "
            "anche quando quel livello è disattivato, sprecando CPU."
        ),
        remediation=(
            "Usa il logging lazy con i placeholder: logger.debug('x=%s', x) "
            "invece di logger.debug(f'x={x}')."
        ),
    ),
    # ----------------------------- ENERGY --------------------------------- #
    Rule(
        id="GC064",
        name="Media HTML in autoplay",
        category="energy",
        severity=SEV_MINOR,
        detector="regex",
        languages=("html",),
        pattern=r"<(video|audio)[^>]*\bautoplay\b",
        flags=re.IGNORECASE,
        description=(
            "L'autoplay di video/audio avvia decodifica e rete senza "
            "interazione dell'utente, consumando CPU/GPU, banda e batteria."
        ),
        remediation=(
            "Evita autoplay; avvia la riproduzione su interazione e usa "
            "preload='none' per non scaricare in anticipo."
        ),
    ),
    # ----------------------------- ASSETS --------------------------------- #
    Rule(
        id="GC071",
        name='Immagine senza loading="lazy"',
        category="assets",
        severity=SEV_LOW,
        detector="regex",
        languages=("html",),
        pattern=r"<img\b(?![^>]*\bloading\s*=)[^>]*>",
        flags=re.IGNORECASE,
        description=(
            "Senza loading='lazy' il browser scarica anche le immagini fuori "
            "schermo, sprecando banda ed energia di trasferimento."
        ),
        remediation=(
            "Aggiungi loading='lazy' alle immagini non critiche (lascia "
            "'eager' solo per quelle above-the-fold)."
        ),
    ),
    Rule(
        id="GC072",
        name="Bundle JS/CSS non minificato di grandi dimensioni",
        category="assets",
        severity=SEV_MINOR,
        detector="asset",
        description=(
            "Servire file JS/CSS grandi e non minificati aumenta banda, tempo "
            "di caricamento ed energia, soprattutto su mobile."
        ),
        remediation=(
            "Minifica e comprimi (gzip/brotli) gli asset in build e abilita il "
            "code splitting per ridurre il payload iniziale."
        ),
    ),
    # ------------------------------ INFRA --------------------------------- #
    Rule(
        id="GC082",
        name="Installazione pacchetti senza pulizia cache (Docker)",
        category="infra",
        severity=SEV_LOW,
        detector="dockerfile",
        languages=("dockerfile",),
        description=(
            "pip senza --no-cache-dir o apt senza --no-install-recommends "
            "lasciano cache e pacchetti superflui nell'immagine, ingrandendola."
        ),
        remediation=(
            "Usa 'pip install --no-cache-dir', 'apt-get install "
            "--no-install-recommends' e 'rm -rf /var/lib/apt/lists/*' nello "
            "stesso RUN."
        ),
    ),
    Rule(
        id="GC083",
        name="Immagine base Docker non-slim",
        category="infra",
        severity=SEV_LOW,
        detector="dockerfile",
        languages=("dockerfile",),
        description=(
            "Immagini base complete (es. 'node', 'python', 'ubuntu') sono molto "
            "più grandi delle varianti '-slim'/'-alpine': più storage, banda e "
            "tempi di pull."
        ),
        remediation=(
            "Usa una variante '-slim' o '-alpine' (o un'immagine distroless) "
            "quando possibile."
        ),
    ),
    Rule(
        id="GC084",
        name="ADD usato al posto di COPY (Docker)",
        category="infra",
        severity=SEV_LOW,
        detector="dockerfile",
        languages=("dockerfile",),
        description=(
            "ADD ha comportamenti impliciti (download remoto, estrazione "
            "archivi) che possono gonfiare l'immagine e ridurne la "
            "riproducibilità."
        ),
        remediation=(
            "Usa COPY per i file locali; riserva ADD ai casi che ne richiedono "
            "esplicitamente le funzioni speciali."
        ),
    ),
    # ===================================================================== #
    # Software Carbon Intensity (SCI) — Green Software Foundation /
    # ISO/IEC 21031:2024.
    #
    #   SCI = ((E · I) + M) / R
    #     E = energia consumata dal software (kWh)
    #     I = intensità di carbonio della rete elettrica (gCO2e/kWh)
    #     M = emissioni "incorporate" dell'hardware (embodied carbon)
    #     R = unità funzionale (per utente, per richiesta, ...)
    #
    # Le regole seguenti intercettano anti-pattern che fanno crescere uno dei
    # tre fattori riducibili dell'SCI, secondo i tre pilastri del green
    # software: efficienza energetica (E), efficienza hardware (M) e
    # consapevolezza del carbonio / carbon awareness (I).
    # ===================================================================== #
    Rule(
        id="GC090",
        name="Schedulazione cron ad altissima frequenza (ogni minuto)",
        category="sci",
        severity=SEV_MINOR,
        detector="regex",
        languages=("yaml", "ini", "toml"),
        pattern=r"\*\s+\*\s+\*\s+\*\s+\*",
        description=(
            "Una pianificazione 'ogni minuto' (* * * * *) risveglia di continuo "
            "CPU e risorse, impedendo agli host di restare idle e ignorando le "
            "finestre a bassa intensità di carbonio (carbon awareness, fattore I)."
        ),
        remediation=(
            "Riduci la frequenza del job, passa a un modello event-driven o "
            "spostalo in fasce orarie con energia più pulita (carbon-aware "
            "scheduling)."
        ),
    ),
    Rule(
        id="GC091",
        name="Container sempre attivo (restart: always)",
        category="sci",
        severity=SEV_LOW,
        detector="regex",
        languages=("yaml",),
        pattern=r"\brestart(policy)?\s*:\s*[\"']?always\b",
        flags=re.IGNORECASE,
        description=(
            "Un servizio configurato come sempre attivo riserva CPU e memoria "
            "24/7 anche quando è inattivo, aumentando l'energia di idle e la "
            "quota di emissioni incorporate dell'hardware (embodied carbon, "
            "fattore M dell'SCI)."
        ),
        remediation=(
            "Usa 'on-failure'/'unless-stopped' dove possibile e adotta lo "
            "scale-to-zero (autoscaler, serverless, KEDA) per non tenere "
            "risorse allocate quando non servono."
        ),
    ),
    Rule(
        id="GC092",
        name="Caching HTTP disabilitato (no-store)",
        category="sci",
        severity=SEV_LOW,
        detector="regex",
        languages=("python", "javascript", "typescript", "java", "php", "ruby",
                   "go", "csharp", "html", "yaml", "json", "ini"),
        pattern=r"cache[-_ ]?control\b[^\n]*\bno-store\b",
        flags=re.IGNORECASE,
        description=(
            "Disabilitare la cache (Cache-Control: no-store) forza client, "
            "proxy e CDN a riscaricare e ricalcolare la risposta a ogni "
            "richiesta, sprecando energia di rete e di calcolo (efficienza "
            "energetica, fattore E dell'SCI)."
        ),
        remediation=(
            "Abilita la cache per le risorse cacheabili (Cache-Control con "
            "max-age/ETag) e riserva 'no-store' ai soli contenuti sensibili."
        ),
    ),
    Rule(
        id="GC093",
        name="Numero fisso ed elevato di repliche senza autoscaling",
        category="sci",
        severity=SEV_LOW,
        detector="regex",
        languages=("yaml",),
        pattern=r"\breplicas\s*:\s*([4-9]|\d{2,})\b",
        flags=re.IGNORECASE,
        description=(
            "Fissare molte repliche sempre accese sovradimensiona l'allocazione "
            "hardware indipendentemente dal carico reale, aumentando energia di "
            "idle ed emissioni incorporate (efficienza hardware, fattore M "
            "dell'SCI)."
        ),
        remediation=(
            "Dimensiona le repliche sul carico effettivo e usa l'autoscaling "
            "orizzontale (HPA/KEDA) con scale-to-zero quando possibile."
        ),
    ),
]


def rules_by_id(rules: Optional[List[Rule]] = None) -> Dict[str, Rule]:
    """Restituisce un dizionario {id: Rule}."""
    return {r.id: r for r in (rules if rules is not None else DEFAULT_RULES)}


def get_rule(rule_id: str, rules: Optional[List[Rule]] = None) -> Optional[Rule]:
    return rules_by_id(rules).get(rule_id)
