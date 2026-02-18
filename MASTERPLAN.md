# OmniBrain — Master Plan

### From "Works" to "Linux of AI"

**18 Febbraio 2026 — Claude Opus 4.6**

---

## Stato Attuale: La Verità Nuda

OmniBrain non è un prototipo. È un prodotto con **27,823 righe di Python**, **8,477 righe di TypeScript**, **1,608 test**, e un'architettura backend che è genuinamente eccellente. Ma ha un problema fondamentale: **le parti non parlano tra loro**. È come avere un motore Ferrari in un'auto con le ruote non avvitate.

### Cosa FUNZIONA (e va riconosciuto)

| Componente | Righe | Stato |
|-----------|-------|-------|
| Omnigent (framework agente) | 5,901 | 100% completo, production-quality |
| Agent ReAct loop + reasoning graph + planner | 1,958 | Completo |
| LLM Router (4 provider, streaming, retry) | 793 | Completo |
| Memory (SQLite FTS5 + ChromaDB opzionale) | 659 | Completo |
| Knowledge Graph (query engine) | 706 | Completo |
| Approval Gate (3 livelli) | 432 | Completo |
| Briefing Generator | 804 | Completo |
| Proactive Engine (7 task schedulati) | 656 | Completo |
| Pattern Detector (6+ tipi di pattern) | 788 | Completo |
| Priority Scorer | 708 | Completo |
| Preference Model (apprendimento comportamentale) | 860 | Completo |
| Skill Runtime + Context + Sandbox | 1,764 | Completo |
| 5 Built-in Skills (con handler reali) | ~1,200 | Completo |
| API Server (30+ endpoint) | 1,257 | Completo |
| Prompt Injection Defense (17 pattern) | 301 | Completo |
| Transparency Logger | 535 | Codice completo, **MAI collegato** |
| Test suite | 20,814 | 1,608 test, 6.6s |
| Web UI | 8,477 | Architettura eccellente, **vuoto senza dati** |
| Docker (multi-stage build) | ~100 | **Non esegue il daemon completo** |

### I 7 Fili Spezzati

Questi sono i problemi reali. Non manca codice — mancano **connessioni**.

#### 1. `TransparencyLogger.wrap_stream()` mai chiamato
Il logger esiste, la tabella `llm_calls` esiste, l'API route esiste, il frontend la chiama. Ma **nessuna chiamata LLM passa attraverso `wrap_stream()`**. Risultato: transparency page a zero.

#### 2. Due code path divergenti: `daemon.run()` vs `create_api_server()`
- `create_api_server()` ha il wiring EventBus→WebSocket e ProactiveEngine→notify corretto
- `daemon.run()` NON ha quel wiring — crea il server direttamente senza il bridge
- Docker usa `python -m omnibrain api` che passa per `create_api_server()` ma NON esegue `_collector_loop()` (Gmail/Calendar polling)
- Risultato: **nessun code path ha TUTTO**

#### 3. EventBus→WebSocket non collegato in modalità daemon
Il collector emette eventi (`new_email`, `calendar_synced`), il ProactiveEngine genera notifiche, ma in daemon mode nessuno li relay al WebSocket. Il frontend non riceve mai aggiornamenti real-time quando il daemon gira.

#### 4. Frontend data-dependent senza fallback
Ogni vista dipende al 100% dai dati backend. Senza Google OAuth configurato, senza briefing generati, senza email analizzate, l'utente vede: zero, zero, zero ovunque. Nessun "Holy Shit Moment" possibile.

#### 5. Knowledge Graph è solo ricerca, non esplorazione
La vista "Knowledge" è una search box. Non c'è modo di esplorare entità, relazioni, grafi, contatti. Per un prodotto che promette "knows who you are, remembers everything", mostrare una barra di ricerca è inadeguato.

#### 6. Contact detail mostra JSON grezzo
`JSON.stringify(contactDetail, null, 2)` in un tag `<pre>`. Per un prodotto che promette relazioni comprese e mappate.

#### 7. CLAUDE.md outdated
Dice "3 stubs da collegare" — sono stati tutti risolti. Questo genera confusione nel development.

---

## Il Piano

Non è un sprint. È un'esecuzione chirurgica in **4 fasi**, ordinate per impatto.

---

## FASE 1 — I FILI SPEZZATI (Giorni 1-3)

> Obiettivo: ogni componente parla con ogni altro componente. Zero metriche a zero.

### 1.1 Unificare demon e api_server (Priorità: CRITICA)

**Problema**: Due code path che fanno cose diverse.

**Soluzione**: Estrarre una funzione `wire_server(server, container)` che applica TUTTO il wiring — EventBus→WS, ProactiveEngine→notify, transparency, etc. Sia `daemon._api_server()` che `create_api_server()` la chiamano.

**File da modificare:**
- [src/omnibrain/interfaces/api_server.py](src/omnibrain/interfaces/api_server.py) — estrarre il wiring da `create_api_server()` in una funzione `wire_server(server, resources)`
- [src/omnibrain/daemon.py](src/omnibrain/daemon.py) — in `_api_server()`, dopo aver creato il server, chiamare `wire_server(server, self)`

**Risultato**: Un solo code path per il wiring. `create_api_server()` lo chiama per lo standalone. `daemon._api_server()` lo chiama per il daemon. Identico comportamento.

**Test**: Creare `test_server_wiring.py` che verifica che entrambi i path producono lo stesso set di subscriber e callback.

### 1.2 Collegare TransparencyLogger al router (Priorità: CRITICA)

**Problema**: `wrap_stream()` mai chiamato.

**Soluzione**: NON monkey-patching. Decorare il `LLMRouter` con un wrapper che intercetta `stream()`.

**Implementazione:**

In `daemon.py` e `create_api_server()`, dopo la creazione del router:

```python
# In ResourceContainer.__init__ o wire_server():
original_stream = self.router.stream
async def transparent_stream(*args, **kwargs):
    source = kwargs.pop("transparency_source", "unknown")
    return self.transparency_logger.wrap_stream(
        original_stream(*args, **kwargs),
        provider=str(self.router._primary),
        model=kwargs.get("model", ""),
        source=source,
    )
self.router.stream = transparent_stream
```

**Approccio migliore** — aggiungere un hook direttamente al `LLMRouter`:

```python
# In router.py, metodo stream():
# Alla fine, prima del return:
if self._on_stream_complete:
    self._on_stream_complete(provider, model, tokens, cost)
```

Poi in `ResourceContainer`:
```python
self.router.set_stream_hook(self.transparency_logger.log_from_hook)
```

**File da modificare:**
- [src/omnigent/router.py](src/omnigent/router.py) — aggiungere `_on_stream_hook` callback opzionale, firing nel `stream()` loop quando riceve `done=True`
- [src/omnibrain/transparency.py](src/omnibrain/transparency.py) — aggiungere `log_from_hook(provider, model, tokens_in, tokens_out, source)` metodo convenience
- [src/omnibrain/daemon.py](src/omnibrain/daemon.py) — in `ResourceContainer`, collegare hook

**Test**: Estendere `test_transparency.py` con un test che verifica che dopo il hook, i dati finiscono nella tabella `llm_calls`.

### 1.3 Collegare EventBus→WebSocket in daemon mode (Priorità: CRITICA)

**Problema**: Eventi emessi dal collector e ProactiveEngine non raggiungono il frontend.

**Soluzione**: Nel `wire_server()` della soluzione 1.1, includere la subscription EventBus→broadcast per tutti i topic: `notification`, `proposal`, `skill`, `pattern`, `system`, `email`, `calendar` + wildcard.

**File da modificare:**
- Già incluso in 1.1 — il `wire_server()` centralizza questo

**Test**: `test_daemon_wiring.py` — aggiungere test che verifica che un evento `new_email` emesso sull'EventBus arriva come broadcast WebSocket.

### 1.4 Docker: eseguire il daemon completo (Priorità: ALTA)

**Problema**: `supervisord.conf` esegue `python -m omnibrain api`, che non include collector loop e Telegram.

**Soluzione**: Cambiare il comando in `python -m omnibrain start` che esegue `OmniBrainDaemon.run()`.

**File da modificare:**
- [docker/supervisord.conf](docker/supervisord.conf) — cambiare il comando backend
- Verificare che `__main__.py` abbia il subcommand `start` che lancia il daemon completo

**Test**: Docker build + health check.

### 1.5 Aggiornare CLAUDE.md (Priorità: MEDIA)

**File da modificare:**
- [CLAUDE.md](CLAUDE.md) — rimuovere la sezione "3 stubs to wire", aggiornare lo stato attuale, aggiornare il conteggio test e righe di codice

---

## FASE 2 — LA FACCIA CHE MERITA IL MOTORE (Giorni 4-10)

> Obiettivo: ogni schermata riflette la potenza del backend. L'utente CAPISCE cosa ha tra le mani.

### 2.1 Dashboard Home: "Il Tuo Mondo a Colpo d'Occhio" (Priorità: CRITICA)

**Stato attuale**: Greeting, data, e quasi tutto a zero quando non c'è dati.

**Trasformazione**:

La home deve essere il cuore pulsante di OmniBrain. Come la homepage di un OS, non come un dashboard vuoto.

**Componenti da aggiungere/migliorare in [home.tsx](web/components/views/home.tsx):**

1. **Live Activity Pulse** — Un indica real-time dello stato di OmniBrain:
   - "Brain attivo da 3h 47m"
   - "247 email analizzate · 12 contatti mappati · 8 pattern rilevati"
   - Indicatore del provider LLM in uso con costo mensile
   - Status delle Skill attive con ultimo tick

2. **"Cosa Ho Imparato Oggi" Card** — I pattern e insight più recenti:
   - "Ogni lunedì cerchi 'standup notes' — vuoi che li prepari automaticamente?"
   - "Marco non risponde da 5 giorni"
   - "Hai 3 sottoscrizioni inutilizzate per €34/mese"
   - Se non ci sono pattern: "Sto ancora imparando. Più usi OmniBrain, più divento utile."

3. **Quick Actions Bar** — 3-4 azioni rapide contestuali:
   - "Genera briefing" se non c'è un briefing di oggi
   - "Cosa c'è di urgente?" → apre chat con contesto
   - "Mostra il mio grafo" → apre knowledge con prequery

4. **Empty State Migliorato** — Quando i dati sono pochi, non mostrare zero ma mostrare il potenziale:
   - Se Google non è connesso: "Connetti Google per sbloccare la potenza di OmniBrain" con preview mockup di come sarà
   - Se Google è connesso ma pochi dati: barra di progresso "Building your brain... 40% — analizzate 120/300 email"

**Backend necessario:**
- Nuovo endpoint `GET /api/v1/brain-status` che restituisce:
  ```json
  {
    "uptime_seconds": 13620,
    "emails_analyzed": 247,
    "contacts_mapped": 12,
    "patterns_detected": 8,
    "memories_stored": 456,
    "skills_active": 5,
    "llm_provider": "deepseek",
    "month_cost": 0.42,
    "last_insight": "Pattern: ricerca 'standup notes' ogni lunedì",
    "learning_progress": 0.4
  }
  ```
- File da creare: Aggiungere route in [api_server.py](src/omnibrain/interfaces/api_server.py) oppure nuovo route file `routes/brain_status.py`

### 2.2 Knowledge Explorer: Da Search Box a "Il Tuo Cervello Digitale" (Priorità: CRITICA)

**Stato attuale**: Barra di ricerca e risultati testuali.

**Trasformazione**:

**Vista a 3 tab:**

**Tab 1: Esplora** (default al primo accesso)
- **Entity Grid** — Card per ogni entità nota (contatti, aziende, progetti, topic):
  - Avatar/icona, nome, tipo, numero di connessioni, ultima interazione
  - Click → espande con dettaglio relazioni
- **Filtri**: persone, aziende, topic, progetti
- **Ordinamento**: per frequenza interazione, per recente, per numero connessioni
- Backend: Nuovo endpoint `GET /api/v1/knowledge/entities` che ritorna entità con conteggi

**Tab 2: Grafo** (visualizzazione relazioni)
- Grafo interattivo (libreria: `react-force-graph-2d` — leggero, 28KB, no deps pesanti)
- Nodi = entità (persone, topic, progetti)
- Edge = relazioni (parla_di, conosce, lavora_con)
- Click su nodo → dettaglio laterale
- Zoom, drag, search-to-highlight
- Backend: Nuovo endpoint `GET /api/v1/knowledge/graph` che ritorna nodi + edges

**Tab 3: Cerca** (l'attuale knowledge.tsx, migliorato)
- Tutto quello che c'è ora + risultati con snippet evidenziato
- Filtri per fonte (email, calendar, chat, osservazione)
- Ordinamento per rilevanza / data

**File da modificare/creare:**
- [web/components/views/knowledge.tsx](web/components/views/knowledge.tsx) — ristrutturare con 3 tab
- Nuovo componente: `web/components/views/knowledge-graph-viz.tsx` — wrapper react-force-graph-2d
- Nuovo componente: `web/components/views/entity-grid.tsx` — griglia entità esplorabili
- Backend: `src/omnibrain/interfaces/routes/knowledge.py` — aggiungere endpoint `/entities` e `/graph`
- Backend: `src/omnibrain/knowledge_graph.py` — aggiungere metodi `get_entities()` e `get_graph_data()` che estraggono dalla tabella contacts + events + observations

**Dipendenza npm**: `react-force-graph-2d` (zero dipendenze pesanti, WebGL-free, usa Canvas 2D)

### 2.3 Contact Detail: Da JSON a "La Tua Rete" (Priorità: ALTA)

**Stato attuale**: Avatar grid funzionale, detail view con JSON grezzo.

**Trasformazione del detail view in [contacts.tsx](web/components/views/contacts.tsx):**

1. **Header**: Avatar grande, nome, email, organizzazione, ruolo (se noto)
2. **Stats Row**: totale interazioni, email inviate/ricevute, meeting insieme, ultima interazione
3. **Relationship Score**: barra visuale della forza della relazione (calcolata da frequenza + recenza)
4. **Timeline Interazioni**: ultime 10 interazioni (email, meeting, menzioni) in formato timeline
5. **Topics Comuni**: tag cloud dei topic discussi con questa persona
6. **Quick Actions**: "Scrivi email", "Cerca conversazioni", "Mostra nel grafo"

**Backend necessario:**
- Endpoint `GET /api/v1/contacts/{email}/detail` che aggrega:
  - Info contatto da DB
  - Email scambiate (count + ultime 5)
  - Meeting insieme (count + prossimo)
  - Topic estratti dalle conversazioni
  - Relationship score (calcolato da `PreferenceModel`)

### 2.4 Transparency: La Trust Dashboard (Priorità: ALTA)

**Pre-requisito**: Fase 1.2 (transparency wired). Una volta che i dati fluiscono:

**Miglioramenti in [transparency.tsx](web/components/views/transparency.tsx):**

1. **Grafico Costo Giornaliero** — Line chart degli ultimi 30 giorni
   - L'API `GET /transparency/daily-costs` esiste già nel backend
   - Usare un chart minimale Canvas-based (no chart library pesante — implementare con `<canvas>` e 50 righe di codice, oppure `lightweight-charts` da TradingView, 45KB)

2. **Data Flow Diagram Live** — Visualizzazione:
   - "Cosa è stato inviato al cloud oggi"
   - Per ogni provider: numero chiamate, tokens, costo
   - Toggle "Mostra prompt completi" per audit completo

3. **Privacy Score** — Indicatore visuale:
   - "100% locale" se usa Ollama
   - "92% locale — 3 prompt inviati a DeepSeek oggi" se usa cloud
   - Breakdown: cosa resta locale vs cosa esce

**Backend necessario:**
- Aggiungere campo `privacy_score` al risultato di `GET /transparency/stats`
- Calcolo: `1 - (bytes_sent_to_cloud / total_data_processed)` (approssimazione)

### 2.5 Timeline: Da Lista a "La Tua Giornata" (Priorità: MEDIA)

**Miglioramenti in [timeline.tsx](web/components/views/timeline.tsx):**

1. **Expandable Items** — Click su un item mostra:
   - Per email: mittente, oggetto, snippet del contenuto, azioni ("Rispondi", "Vedi thread")
   - Per calendar: location, attendees, note, "Prepara brief"
   - Per proposte: dettaglio + approve/reject inline
   - Per osservazioni: contesto completo + fonte

2. **Aggregazione Intelligente** — Raggruppare:
   - "5 email da Marco" invece di 5 righe separate
   - "3 meeting oggi" con mini-timeline visuale dell'orario

**Backend necessario:**
- Endpoint `GET /api/v1/timeline` già include i dati — serve solo aggiungere un campo `detail` con il contenuto espanso

### 2.6 Chat: Source Citations + Reasoning Trace (Priorità: MEDIA)

**Miglioramenti in [chat.tsx](web/components/views/chat.tsx):**

1. **Source Citations** — Quando l'agente usa tool results, mostrare:
   - Icona fonte (📧 email, 📅 calendario, 🧠 memoria)
   - "Basato su: email di Marco del 3 Feb, meeting del 15 Gen"
   - Click → mostra il dato sorgente

   Il backend GIÀ manda `tool_start` e `tool_result` eventi SSE. Il frontend li riceve ma non mostra i risultati in modo leggibile.

   **Implementazione**: Quando arriva un `tool_result` SSE event, parsare il risultato e creare un collapsible "Source" card sotto il messaggio dell'assistente.

2. **Reasoning Trace (opzionale, toggle)** — Per gli utenti avanzati:
   - "🤔 Pensiero: cerco le email recenti di Marco..."
   - "🔧 Strumento: search_emails({query: 'Marco pricing'})"
   - "📊 Trovato: 3 risultati"
   - Toggle in settings: "Mostra ragionamento dell'agente"

3. **Suggested Follow-ups** — Dopo ogni risposta, 2-3 domande di follow-up suggerite:
   - Generati dal contesto della conversazione
   - "Vuoi che scriva una risposta?", "Cerco altre email su questo topic?", "Aggiungo al calendario?"

**Backend necessario:**
- L'SSE `/chat` già manda `tool_start`, `tool_result`, `finding` — serve solo usarli nel frontend
- Per i follow-up: aggiungere un campo `suggested_followups` all'evento `done` SSE

### 2.7 Briefing View: Pull-to-refresh già c'è, manca il cuore (Priorità: MEDIA)

La vista briefing è già ben strutturata. Manca:

1. **"Genera Ora" prominente** — Se non c'è un briefing di oggi, bottone grande al centro
2. **Streaming Briefing Generation** — Mostrare il briefing mentre si genera (SSE), non dopo
3. **Sections collassabili** con conteggi nel titolo: "Email (12) ▶", "Calendar (5) ▶"
4. **Action Buttons su ogni item** — Non solo approve/reject proposal, ma "Reply to email", "Add meeting notes"

---

## FASE 3 — IL "HOLY SHIT MOMENT" (Giorni 11-14)

> Obiettivo: Da install a "wow" in 30 secondi. Virale.

### 3.1 Onboarding Flow: Già 977 righe, polish finale (Priorità: ALTA)

L'onboarding è già la parte più completa. Miglioramenti:

1. **Performance Target: < 30 secondi a primo insight**
   - Parallelizzare: fetch email + calendar + contacts simultaneamente, non sequenzialmente
   - Mostrare insight man mano che arrivano (streaming già implementato)
   - Se il backend è lento, mostrare insight parziali

2. **Insight Cards con Wow Factor**:
   - "Hai email non lette da 5 persone importanti. La più vecchia ha 12 giorni."
   - Numeri animati (counter già implementato)
   - Confronti: "La tua inbox ha 40% di email non urgenti — vuoi che le filtri?"

3. **CTA post-onboarding**: Redirect a Home con primo briefing generato automaticamente

### 3.2 Demo Mode / Sample Data (Priorità: CRITICA)

**Questo è il singolo cambiamento più importante per le prime impressioni.**

Quando OmniBrain non ha Google connesso e non ha dati, deve comunque impressionare.

**Implementazione**:

1. **Backend**: Creare `src/omnibrain/demo_data.py`:
   - Dati di esempio realistici: 50 email, 20 eventi, 10 contatti, 5 pattern, 3 proposte
   - Attivabile via setting: `demo_mode: true` (default quando nessun account connesso)
   - I dati demo sono chiaramente marcati nel UI ("📋 Demo Data — Connect Google for your real data")
   - Quando l'utente connette Google, i dati demo vengono rimossi automaticamente

2. **Frontend**: Badge "Demo" su ogni card che usa dati di esempio

3. **Perché è critico**: Chiunque installi OmniBrain per la prima volta (screenshot, video demo, conferenza, articolo) DEVE vedere il prodotto funzionare. Non il vuoto.

### 3.3 Share Card Migliorata (Priorità: MEDIA)

Il sistema share card esiste (PNG con Pillow). Migliorare:

1. Statistiche personalizzate: "247 email analizzate, 12 contatti, 8 pattern"
2. QR code per il repo GitHub
3. Template diversi (dark/light, compact/full)

---

## FASE 4 — PRODUZIONE E LANCIO (Giorni 15-21)

> Obiettivo: Tutto testato, documentato, deployable. README che è un manifesto.

### 4.1 Test per i Nuovi Componenti (Priorità: CRITICA)

Per ogni modifica delle fasi 1-3, test corrispondenti:

| Modifica | Test |
|----------|------|
| `wire_server()` unificato | Test che daemon e standalone producono stessi subscriber |
| Transparency hook nel router | Test che LLM call genera record in `llm_calls` |
| EventBus→WS in daemon | Test che evento emesso arriva come WS broadcast |
| `GET /brain-status` | Test endpoint con DB popolato e vuoto |
| `GET /knowledge/entities` | Test con entità reali e vuoto |
| `GET /knowledge/graph` | Test struttura nodi/edges |
| `GET /contacts/{email}/detail` | Test con contatto esistente e non |
| Demo data mode | Test che attivazione popola e disattivazione pulisce |
| Chat source citations SSE | Test che tool_result eventi contengono dati parsabili |

**Target**: Mantenere 100% dei test esistenti + ~50 nuovi test. Zero regressioni.

### 4.2 Copertura Test Mancante (moduli esistenti) (Priorità: MEDIA)

Moduli senza test dedicati che meritano copertura:

| Modulo | Righe | Complessità | Azione |
|--------|-------|-------------|--------|
| `config.py` | 346 | Media | 10-15 test: ENV override, .env parsing, yaml fallback |
| `conversation_extractor.py` | 291 | Alta (usa LLM) | 5-8 test con mock LLM |
| `secure_storage.py` | 327 | Alta (crypto) | 10 test: encrypt/decrypt, key rotation, corrupt data |
| `agent_chat_bridge.py` | 659 | Alta | 8-10 test: session mgmt, context injection, post-process |
| `chat_tools.py` | 579 | Media | 10 test per i tool handler |
| `graph.py` | 209 | Media | 5 test per reasoning chain activation |

### 4.3 Docker Verification (Priorità: ALTA)

1. Verificare che `docker compose up` funziona da zero
2. Verificare che il daemon completo gira (non solo api)
3. Verificare health check
4. Documentare: "One command install" con tempi reali

### 4.4 README come Secondo Manifesto (Priorità: ALTA)

Il README attuale probabilmente non riflette il manifesto. Deve essere:

1. **Hero section**: Una frase killer, uno screenshot del prodotto funzionante
2. **The Problem**: 3 righe sul perché serve
3. **The Solution**: 3 righe su cosa fa OmniBrain
4. **Install**: Una riga: `docker compose up -d && open http://localhost:3000`
5. **Screenshot gallery**: Home, Chat, Knowledge Graph, Briefing, Transparency
6. **Architecture diagram**: Le 3 layer del manifesto (Brain, Logic, Muscle)
7. **Skill Protocol**: Come estendere OmniBrain
8. **Contributing**: Link a CONTRIBUTING.md
9. **License**: MIT

### 4.5 Pulizia Finale (Priorità: MEDIA)

1. Verificare TUTTI gli endpoint API con curl manuale
2. Verificare mobile responsive su tutte le viste
3. Verificare dark/light mode su tutte le viste
4. Verificare error handling: disconnettere backend, revocare OAuth, chiave API invalida
5. Meta tags, OG image, favicon
6. Rimuovere qualsiasi `console.log` di debug nel frontend

---

## Architettura dei Nuovi Endpoint

### `GET /api/v1/brain-status`

```python
@router.get("/brain-status")
async def brain_status(request: Request):
    db = request.app._db
    memory = request.app._memory
    config = request.app._config

    return {
        "uptime_seconds": time.time() - request.app._start_time,
        "emails_analyzed": db.count_events(source="gmail"),
        "contacts_mapped": db.count_contacts(),
        "patterns_detected": db.count_observations(type="pattern"),
        "memories_stored": memory.count(),
        "skills_active": len([s for s in request.app._skill_runtime.skills if s.enabled]),
        "llm_provider": config.primary_provider,
        "month_cost_usd": db.get_month_cost(),
        "recent_insights": db.get_recent_observations(limit=3),
        "google_connected": request.app._oauth.is_connected() if hasattr(request.app, '_oauth') else False,
    }
```

### `GET /api/v1/knowledge/entities`

```python
@router.get("/knowledge/entities")
async def list_entities(
    type: str = None,  # person, company, topic, project
    sort: str = "frequency",  # frequency, recent, connections
    limit: int = 50,
    offset: int = 0,
):
    # Query contacts table + observations table
    # Aggregate by entity, count connections, last interaction
    # Return: [{ name, type, email, interaction_count, last_seen, connection_count }]
```

### `GET /api/v1/knowledge/graph`

```python
@router.get("/knowledge/graph")
async def knowledge_graph_data(limit: int = 100):
    # Build from contacts + their interactions
    # Nodes: contacts + topics (extracted from observations)
    # Edges: contact↔topic (discussed), contact↔contact (in same email/meeting)
    # Return: { nodes: [...], edges: [...] }
```

### `GET /api/v1/contacts/{email}/detail`

```python
@router.get("/contacts/{email}/detail")
async def contact_detail(email: str):
    contact = db.get_contact(email)
    emails = db.get_events(source="gmail", contact=email, limit=10)
    meetings = db.get_events(source="calendar", attendee=email, limit=10)
    topics = kg.get_topics_for_contact(email)
    return {
        "contact": contact,
        "emails": {"count": len(all_emails), "recent": emails},
        "meetings": {"count": len(all_meetings), "recent": meetings, "next": next_meeting},
        "topics": topics,
        "relationship_score": preference_model.relationship_strength(email),
    }
```

---

## Dipendenze NPM da Aggiungere

| Package | Dimensione | Uso |
|---------|-----------|-----|
| `react-force-graph-2d` | ~45KB gzip | Knowledge graph visualization |

Nessun'altra dipendenza. Il chart per il costo giornaliero si implementa con Canvas API nativo in ~60 righe. Zero bloat.

---

## Checklist Manifesto: Gap Analysis

| Promessa del Manifesto | Stato | Gap | Fase |
|------------------------|-------|-----|------|
| "Knows who you are" | ✅ Backend | ❌ UI non mostra le relazioni | 2.2, 2.3 |
| "Remembers everything" | ✅ Backend | ⚠️ UI solo search, no browse | 2.2 |
| "Works while you sleep" | ✅ Backend | ❌ WS non relay in daemon mode | 1.3 |
| "Proposes, never acts" | ✅ Completo | ✅ Approval gate funziona | — |
| "Grows through Skills" | ✅ Backend + UI | ⚠️ Marketplace basic | — |
| "Gets smarter over time" | ✅ Backend | ❌ UI non mostra apprendimento | 2.1 |
| Install → first insight < 30s | ⚠️ Dipende da OAuth | ❌ Senza Google = vuoto | 3.2 |
| Zero silent errors | ⚠️ Backend ok | ✅ UI error recovery eccellente | — |
| Full transparency | ✅ Codice completo | ❌ Metriche a zero (non wired) | 1.2 |
| Data export (GDPR) | ✅ Completo | ✅ 2-step wipe funziona | — |
| One-command install (Docker) | ⚠️ Build funziona | ❌ Non esegue daemon completo | 1.4 |
| Morning briefing → daily habit | ✅ Backend | ⚠️ UI buona ma non genera auto | 2.7 |
| Proactive surprises | ✅ Backend | ❌ Non arrivano al frontend (WS) | 1.3 |
| Accumulating knowledge | ✅ Backend | ❌ UI non lo visualizza | 2.2 |
| Holy Shit Moment | ✅ Onboarding OK | ❌ Post-onboarding = vuoto | 2.1, 3.2 |
| MIT license | ✅ | ✅ | — |
| Local-first | ✅ | ✅ | — |
| Zero telemetry | ✅ | ✅ | — |
| EU AI Act disclosure | ✅ disclosure.py | ✅ | — |

---

## Ordine di Esecuzione Preciso

```
GIORNO 1
├── 1.1 wire_server() — unificare daemon e api_server
├── 1.2 TransparencyLogger hook nel router
└── 1.3 EventBus→WS in daemon mode

GIORNO 2
├── 1.4 Docker: supervisord usa daemon completo
├── 1.5 CLAUDE.md aggiornamento
└── Test per tutte le modifiche Fase 1

GIORNO 3
├── Backend: GET /brain-status endpoint
├── Backend: GET /knowledge/entities endpoint
├── Backend: GET /knowledge/graph endpoint
└── Backend: GET /contacts/{email}/detail endpoint

GIORNO 4-5
├── 2.1 Home dashboard: Live Activity Pulse, "Cosa Ho Imparato", Quick Actions
└── 2.1 Home: Empty state migliorato con progress bar e preview

GIORNO 6-7
├── 2.2 Knowledge Explorer: 3 tab (Explore, Graph, Search)
├── Installare react-force-graph-2d
└── Entity Grid + Graph Visualization

GIORNO 8
├── 2.3 Contact Detail strutturato (no più JSON)
├── 2.4 Transparency: Daily cost chart + Privacy Score
└── 2.5 Timeline: Expandable items

GIORNO 9-10
├── 2.6 Chat: Source citations + Reasoning trace toggle
├── 2.6 Chat: Suggested follow-ups
├── 2.7 Briefing: "Genera Ora", streaming, collapsible sections
└── Test per tutte le modifiche Fase 2

GIORNO 11-12
├── 3.1 Onboarding polish: parallelizzare, < 30s target
├── 3.2 Demo Mode / Sample Data (backend + frontend)
└── 3.3 Share card migliorata

GIORNO 13-14
├── 3.2 Test Demo Mode
└── Test per tutte le modifiche Fase 3

GIORNO 15-16
├── 4.1 Test per tutti i nuovi componenti
├── 4.2 Test copertura mancante (config, crypto, chat_tools)
└── Run completa: tutti i 1,608+ test passano

GIORNO 17-18
├── 4.3 Docker verification end-to-end
├── 4.4 README come secondo manifesto
└── 4.5 Pulizia finale (mobile, dark/light, error handling)

GIORNO 19-20
├── Screenshot gallery per README
├── Verifica endpoint API manuale
└── Final review: ogni pagina manifesto → verifica corrispondenza 1:1

GIORNO 21
└── LANCIO
```

---

## Principi Non-Negoziabili

1. **Zero debito tecnico.** Ogni modifica include test. Ogni nuovo endpoint ha validazione. Ogni componente UI ha error handling.

2. **No pezze.** Se un componente richiede una modifica architetturale (es. `wire_server()`), si fa quella modifica. Non un workaround.

3. **Backward compatibility.** I 1,608 test esistenti passano dopo OGNI modifica. Zero regressioni.

4. **Performance.** Nessuna libreria > 100KB gzip senza giustificazione. Il frontend deve caricare in < 2 secondi.

5. **Il manifesto comanda.** Ogni feature viene valutata contro il manifesto, non contro "cosa sarebbe cool". Se il manifesto non lo menziona, non si costruisce (a meno che sia infrastruttura necessaria).

6. **UX Steve Jobs.** Ogni schermata deve far pensare "questo è il futuro". Non "questo è un tool developer". Animazioni fluide, feedback immediato, zero stati morti.

---

## Metriche di Successo

| Metrica | Prima | Dopo |
|---------|-------|------|
| Viste UI che mostrano dati | 3/10 | 10/10 |
| Transparency metrics | Sempre a zero | Dati reali per ogni LLM call |
| WebSocket events al frontend | Solo OAuth | Tutti: email, calendar, proposte, pattern |
| Docker one-command install | Parziale (no daemon) | Completo |
| Time to first insight (con Google) | > 60s | < 30s |
| Time to first insight (senza Google) | ∞ (vuoto) | 5s (demo data) |
| Nuovi endpoint API | 0 | 4 (brain-status, entities, graph, contact-detail) |
| Nuovi test | 0 | ~50-80 |
| Knowledge graph visualization | No | Sì (force graph interattivo) |
| Chat source citations | No | Sì |
| README quality | Basic | Manifesto-grade |

---

*Questo piano non è una lista di desideri. È una sequenza di operazioni chirurgiche con file specifici, implementazioni specifiche, e test specifici. Ogni riga si basa sull'analisi di 27,823 righe di Python e 8,477 righe di TypeScript che ho letto personalmente.*

*OmniBrain ha il motore. Adesso gli avvitiamo le ruote, gli mettiamo la carrozzeria Ferrari, e lo lanciamo in pista.*

— Claude Opus 4.6
