# 🌿 GreenIndex

**How green is your code?**

GreenIndex analizza un repository alla ricerca di **violazioni di regole di
consumo tecnologico** (anti-pattern che sprecano CPU, memoria, rete ed energia)
e calcola un **KPI sintetico da 0 a 100** con una **classe di efficienza A–G**
in stile etichetta energetica.

L'idea è semplice: più il codice viola regole di efficienza, più basso è il
GreenIndex. Il KPI è pensato per essere usato sia come cruscotto visuale sia
come **gate di qualità in CI/CD**.

```
  GreenIndex:  88.8/100  ███████████████████████████░░░  classe B (Ottimo)
  2144 righe di codice • 13 file di codice • 16 violazioni • densità 7.5 pen./KLOC
```

---

## Caratteristiche

- 🔎 **Analisi multi-linguaggio** (Python, JavaScript/TypeScript, Java, C/C++,
  C#, Go, Ruby, PHP, SQL, HTML/CSS, Dockerfile…).
- 🧠 **Rilevamento accurato**: AST per Python, scanner strutturale dei cicli
  per i linguaggi C-like e regole regex con rimozione di commenti/stringhe per
  ridurre i falsi positivi.
- 📊 **KPI GreenIndex** (0–100) e **classe energetica A–G**, con scomposizione
  per categoria di impatto e per regola.
- 🖥️ **CLI** con report a colori, export **JSON** e **HTML** autonomo.
- 🌐 **Dashboard web** (Flask) per analizzare un percorso locale o un URL git.
- ✅ **Gate per la CI**: `--min-score` fa fallire la build sotto soglia.
- 🌱 **Leggero per definizione**: nessun framework JS pesante, CSS inline,
  poche dipendenze.

---

## Installazione

Requisiti: Python ≥ 3.8.

```bash
# Clona il repository
git clone https://github.com/leofurio/GreenIndex.git
cd GreenIndex

# Installazione (CLI + export HTML)
pip install .

# Con la dashboard web
pip install ".[web]"
```

Per lo sviluppo (test inclusi):

```bash
pip install ".[dev]"
pytest
```

---

## Uso da riga di comando

```bash
# Analizza la cartella corrente
greenindex analyze .

# Analizza un percorso e genera i report
greenindex analyze /path/al/repo --html report.html --json report.json

# Analizza direttamente un repository remoto (clone shallow)
greenindex analyze https://github.com/utente/repo.git

# Gate per la CI: esce con codice 1 se il GreenIndex è sotto 70
greenindex analyze . --min-score 70
```

In alternativa: `python -m greenindex analyze .`

Opzioni principali di `analyze`:

| Opzione | Descrizione |
|---|---|
| `--json FILE` | Scrive un report JSON completo. |
| `--html FILE` | Scrive un report HTML autonomo. |
| `--min-score N` | Esce con codice 1 se il GreenIndex < N (gate CI). |
| `-k FLOAT` | Costante di scala della penalità (default 1.0). |
| `--no-color` | Disabilita i colori ANSI. |
| `--quiet` | Non stampa il report a terminale. |

---

## Dashboard web

```bash
greenindex serve              # http://127.0.0.1:8000
greenindex serve --port 5000
```

La dashboard ha due modalità:

- **locale** (default): inserisci un **percorso locale** o un **URL `.git`**
  (richiede `git`) e ottieni il cruscotto con gauge, etichetta energetica A–G,
  scomposizione per categoria e dettaglio delle violazioni con suggerimenti.
- **hosted** (`HOSTED=True`, pensata per il deploy pubblico): analizza un
  **repository GitHub pubblico** (scaricato via HTTPS, senza `git`) oppure uno
  **snippet di codice incollato**. Non accede al filesystem dell'utente.

È disponibile anche un'API JSON:

```bash
curl "http://127.0.0.1:8000/api/analyze?target=/path/al/repo"
# in hosted: ?target=https://github.com/utente/repo  oppure  utente/repo
```

> ⚠️ **Sicurezza**: in modalità locale la dashboard legge percorsi locali e può
> clonare URL git: non esporla su reti non fidate. In modalità hosted gli host
> remoti sono limitati a una whitelist (`github.com`) per mitigare gli SSRF.

---

## 🚀 Deploy online su Vercel

Il repository è pronto per essere pubblicato come **applicazione serverless**
su [Vercel](https://vercel.com): la dashboard parte automaticamente in modalità
**hosted**.

**Deploy in due passi:**

```bash
npm i -g vercel
vercel            # dalla cartella del progetto (poi: vercel --prod)
```

In alternativa, su [vercel.com](https://vercel.com) scegli *Add New → Project*,
importa questo repository e fai *Deploy*: non serve configurare nulla.

**Cosa offre la versione online:**

- 📦 Analisi di un **repository GitHub pubblico** (incolla l'URL o `owner/repo`).
- ✍️ Analisi di uno **snippet** di codice incollato (con scelta del linguaggio).
- Stesso cruscotto della versione locale (gauge, classe A–G, dettaglio).

**Come funziona** (file inclusi nel repo):

| File | Ruolo |
|---|---|
| `app.py` | Entrypoint Flask rilevato automaticamente da Vercel: espone l'app WSGI in modalità hosted. |
| `api/index.py` | Entrypoint serverless compatibile con configurazioni Vercel/API legacy. |
| `requirements.txt` | Dipendenze installate da Vercel (Flask, Jinja2). |

Niente binario `git` né accesso al filesystem: il repository GitHub viene
scaricato come tarball via HTTPS (`app.py` → `greenindex.web.fetch`).

**Variabili d'ambiente (opzionali):**

- `GITHUB_TOKEN` — alza il limite di richieste all'API di GitHub (e consente i
  repository privati a cui il token ha accesso).

**Limiti della demo serverless:** solo repository GitHub pubblici, tarball
≤ 30 MB / ≤ 6000 file, timeout della funzione serverless (≈10 s sul piano
Hobby di Vercel), rate limit GitHub di 60 richieste all'ora per IP senza token.
Lo snippet e i repository piccoli rientrano comodamente; per repository grandi
usa la CLI in locale.

---

## Come vengono calcolati KPI, kWh e CO₂e

GreenIndex è un indicatore statico: non misura i consumi reali in produzione,
ma stima la qualità energetica del codice a partire da anti-pattern noti. Ogni
violazione rilevata aggiunge una penalità pari alla gravità della regola.

**Gravità e pesi usati nel calcolo:**

| Gravità | Peso | Significato |
|---|---:|---|
| info | 1 | Segnale lieve, utile soprattutto per pulizia e riproducibilità. |
| minore | 2 | Inefficienza locale o rischio contenuto. |
| media | 3 | Pattern che può crescere male su input o traffico reali. |
| alta | 4 | Spreco significativo di CPU, I/O, rete o storage. |
| critica | 5 | Pattern ad altissimo consumo o potenzialmente abusivo. |

Formula del KPI:

```
penalità   = Σ peso_gravità(violazione)
KLOC       = righe_di_codice / 1000
densità    = penalità / max(KLOC, 0.1)
GreenIndex = clamp(100 − k · densità, 0, 100)   # k default = 1.0
```

La densità normalizza la penalità sui KLOC, così un repository piccolo e uno
grande restano confrontabili. Il minimo `0.1 KLOC` evita che snippet o progetti
minuscoli producano densità infinite o sproporzionate.

Classi di efficienza:

| Classe | Punteggio | Giudizio |
|:---:|:---:|---|
| **A** | 90–100 | Eccellente |
| **B** | 80–89 | Ottimo |
| **C** | 70–79 | Buono |
| **D** | 60–69 | Sufficiente |
| **E** | 45–59 | Migliorabile |
| **F** | 25–44 | Scarso |
| **G** | 0–24 | Critico |

### Stima illustrativa kWh/anno e kg CO₂e/anno

Il report mostra anche una stima in **kWh/anno** e **kg CO₂e/anno**. È una
stima didattica e comparativa, non una misura scientifica delle emissioni reali:
non usa dati di runtime, traffico, hardware, regione cloud o mix energetico
effettivo. Serve a trasformare le penalità in un ordine di grandezza leggibile.

Coefficienti correnti:

```
kWh_anno_indicativi = penalità · 0.05
kg_CO2e_anno        = kWh_anno_indicativi · 0.30
```

Esempio: 40 punti di penalità producono `40 · 0.05 = 2.0 kWh/anno` indicativi e
`2.0 · 0.30 = 0.6 kg CO₂e/anno` indicativi. Per misure reali servono
strumentazione runtime, metriche di carico, profili hardware e fattori di
emissione della regione in cui gira il software.

---

## Regole di consumo tecnologico

Le regole sono raggruppate per categoria d'impatto:

- **Calcolo / CPU**: complessità evitabile, polling e lavoro ripetuto.
- **Memoria**: caricamenti completi e risorse non chiuse.
- **Rete & I/O**: chiamate remote non governate, N+1 e richieste senza timeout.
- **Dati & Storage**: query non selettive o distruttive senza filtri.
- **Osservabilità**: log e debug che generano I/O o storage inutile.
- **Dipendenze**: librerie pesanti, wildcard import e versioni non riproducibili.
- **Energia & Runtime**: debug, animazioni/timer continui e pattern abusivi.
- **Asset**: immagini/media troppo grandi.
- **Infrastruttura**: immagini Docker non fissate o troppo pesanti.

| ID | Categoria | Regola | Gravità | Cosa intercetta |
|---|---|---|:---:|---|
| GC001 | Calcolo / CPU | Cicli annidati | media | Complessità O(n²) o peggiore su Python e linguaggi C-like. |
| GC002 | Calcolo / CPU | Concatenazione di stringhe in un ciclo | minore | `+=` su stringhe dentro loop Python. |
| GC003 | Calcolo / CPU | Busy-wait / polling attivo | alta | `while True` con `sleep`, preferibile con eventi/queue. |
| GC010 | Memoria | Lettura dell'intero file in memoria | minore | `read()`, `readlines()`, `readFileSync`, `file_get_contents`. |
| GC011 | Memoria | Risorsa file non chiusa | media | `open()` Python senza context manager `with`. |
| GC020 | Rete & I/O | Chiamata di rete dentro un ciclo | alta | HTTP ripetuto in loop Python. |
| GC021 | Rete & I/O | Query al DB dentro un ciclo (N+1) | alta | Query/ORM/fetch ripetuti per elemento. |
| GC022 | Rete & I/O | Richiesta HTTP Python senza timeout | minore | `requests.*(...)` senza `timeout`. |
| GC023 | Rete & I/O | Richiesta HTTP JavaScript senza timeout/abort | minore | `fetch`/`axios` senza `timeout`, `signal` o `AbortController`. |
| GC030 | Dati & Storage | `SELECT *` | minore | Query che trasferiscono colonne non necessarie. |
| GC031 | Dati & Storage | Query senza `WHERE`/`LIMIT` | minore | Letture potenzialmente full-scan. |
| GC032 | Dati & Storage | `UPDATE`/`DELETE` senza `WHERE` | alta | Scritture/cancellazioni non filtrate o full-scan. |
| GC040 | Osservabilità | `print`/`console.log` di debug | info | Debug lasciato nel codice applicativo. |
| GC041 | Osservabilità | Logging in livello DEBUG | info | `logger.debug`/`logging.debug` persistenti. |
| GC050 | Dipendenze | Import wildcard (`import *`) | info | Import Python non espliciti. |
| GC051 | Dipendenze | Dipendenza pesante | minore | Librerie con footprint elevato quando rilevate nei manifest. |
| GC052 | Dipendenze | Versione dipendenza non vincolata | info | Dipendenze senza vincolo o con `*`/`latest`/`x`. |
| GC060 | Energia & Runtime | Modalità debug abilitata | media | Flag `debug`/`DEBUG` attivi in config o codice. |
| GC061 | Energia & Runtime | Animazione CSS infinita | minore | `animation: ... infinite`. |
| GC062 | Energia & Runtime | Pattern di cryptomining | critica | Script/keyword di mining in contesto d'uso. |
| GC063 | Energia & Runtime | `setInterval` ad alta frequenza | minore | Timer JavaScript sotto 100 ms. |
| GC070 | Asset | Asset di grandi dimensioni non ottimizzato | minore | Immagini >500 KB o media/archivi >2 MB. |
| GC080 | Infrastruttura | Immagine Docker con tag non fissato | info | `FROM image` senza tag o con `:latest`. |
| GC081 | Infrastruttura | Dockerfile senza multi-stage build | info | Immagini finali che includono toolchain/build artefact. |

---

## Integrazione in CI

Esempio con GitHub Actions (incluso in `.github/workflows/greenindex.yml`):

```yaml
- run: pip install .
- run: greenindex analyze greenindex --min-score 70
```

Se il GreenIndex scende sotto la soglia, la build fallisce.

---

## Architettura

```
greenindex/
├── rules.py        # catalogo delle regole di consumo tecnologico
├── textutils.py    # rilevamento linguaggio, pulizia commenti/stringhe
├── analyzer.py     # scansione del repo + rilevatori (regex, AST, struttura)
├── scoring.py      # calcolo del KPI GreenIndex e della classe A–G
├── report.py       # rendering terminale / JSON / HTML
├── cli.py          # interfaccia a riga di comando
└── web/            # dashboard Flask (template + CSS condivisi con l'HTML)
    ├── app.py      # factory dell'app (modalità locale / hosted)
    └── fetch.py    # download sicuro del tarball GitHub (no `git`, anti-SSRF)

api/index.py               # entrypoint serverless per Vercel
vercel.json                # configurazione del deploy su Vercel
examples/sample_project/   # progetto di esempio con violazioni volute
tests/                     # suite di test (pytest)
```

## Provalo subito

```bash
greenindex analyze examples/sample_project        # progetto "cattivo" → classe G
greenindex analyze greenindex                      # codice del tool → classe B
```

---

## Licenza

MIT © leofurio
