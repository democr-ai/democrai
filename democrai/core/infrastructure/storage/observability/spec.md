Principio guida

Observability come “first-class data”, non come servizio esterno

A. Unifica tutto in Eventi

Definisci un Event Envelope comune:

timestamp

level (INFO/WARN/ERROR)

category (system / model / agent / vector / graph)

scope (user_id, session_id, agent_id)

payload (JSON)

duration_ms (opzionale)

correlation_id (fondamentale)

Ogni cosa importante emette un evento.

B. Storage default: SQLite

una tabella eventi append-only

indici su (timestamp, category, user_id, correlation_id)

Pro:

zero dipendenze

local-first

replay possibile

audit/debug potentissimo

Questo è il tuo “black box recorder”.

C. Metriche derivate (non primarie)

Le metriche (p95 latency, error rate, tokens/sec):

derivano dagli eventi

non sono la fonte primaria

Questo ti permette:

di cambiare metriche senza cambiare runtime

di fare analisi retroattive

D. Exporters (opzionali)

Implementa solo adapter di export, non integrazioni strette:

OpenTelemetry exporter

Prometheus metrics exporter

Langfuse exporter (se l’utente lo vuole)

Democrai resta indipendente.

4. Come appare in pratica (esempio)

Evento agente:

{
  "ts": 1739200123,
  "level": "INFO",
  "category": "agent",
  "user_id": "u123",
  "session_id": "s456",
  "agent_id": "doc_analyzer",
  "event": "tool_call",
  "tool": "vector_search",
  "duration_ms": 37,
  "payload": {
    "top_k": 10,
    "index": "documents"
  },
  "correlation_id": "c789"
}


Da qui puoi:

ricostruire flussi

capire colli di bottiglia

spiegare “perché l’agente ha fatto X”

5. Cosa evitare assolutamente

❌ Tracing distribuito “full” subito
❌ Dipendere da SaaS cloud-only
❌ Metriche senza contesto
❌ Log testuali non strutturati
❌ Tool diversi per ogni layer

6. Strategia consigliata (netta)

V1

Event bus interno

SQLite event store

UI base per timeline + filtri

correlation_id ovunque

V2

Metriche aggregate

Export OpenTelemetry

Debugger agenti visuale