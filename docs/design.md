# Design Document - Medical Entity & Relation Annotation Tool

## 1. Purpose & Scope
A lightweight annotation tool enabling medical subject matter experts to label entities (diseases, medications, symptoms, etc.) and binary relations (e.g., treats, causes) in short clinical / biomedical texts (sample abstracts). Output is JSON suitable for downstream NLP model training. Focus is minimal viable workflow within tight time constraints (hours, not weeks) while leaving clear seams for enhancement (LLM assistance, Azure deployment, richer UI).

## 2. High-Level Architecture
```
+-------------------+           HTTP (JSON)            +---------------------------+
|  Browser (UI)     |  <---->  FastAPI Backend  <----> |  File Persistence (JSON)  |
|  Static HTML/JS   |           (Uvicorn)              |  data/annotations/*.json  |
+-------------------+                                   +---------------------------+
          ^                                                ^
          | fetch()                                        | filesystem I/O
          |                                                |
          +---------------- Vocabulary & Raw Texts --------+
                                 data/vocab.json
                                 data/raw/*.txt
```
- No database (JSON file per document for durability & inspection).
- Stateless API except in-memory cache of documents (hydrated from JSON on bootstrap or first mutation).
- Heuristic suggestion service (stub) isolated for future LLM swap.

## 3. Data Model
### 3.1 Entity
| Field | Type | Description |
|-------|------|-------------|
| id | uuid (str) | Unique entity identifier |
| start | int | Inclusive character offset in document text |
| end | int | Exclusive character offset |
| text | str | Surface span |
| type | str | Controlled vocabulary (from vocab.json) |
| code | str? | Optional standardized code (future) |
| annotator | str? | Filled with default (APP_ANNOTATOR or 'anon') if absent |
| timestamp | datetime | Auto-populated UTC at creation |

### 3.2 Relation
| Field | Type | Description |
|-------|------|-------------|
| id | uuid (str) | Unique relation id |
| source_entity_id | str | Origin entity id |
| target_entity_id | str | Target entity id |
| relation_type | str | Controlled vocabulary (vocab.json) |
| direction | 'forward' | 'reverse' | Direction semantic (default forward) |
| annotator | str? | Auto-filled if absent |
| timestamp | datetime | Creation time |

### 3.3 Document
| Field | Type | Description |
|-------|------|-------------|
| id | str | Stable id (filename stem for bootstrapped docs) |
| text | str | Raw text content |
| status | str | Workflow state (in_progress, completed, etc.) |
| entities | [Entity] | Current entity annotations |
| relations | [Relation] | Current relation annotations |

### 3.4 Persistence File Layout (JSON example excerpt)
```json
{
  "id": "abstract1",
  "text": "Hypertension is treated with amlodipine.",
  "status": "in_progress",
  "entities": [ {"id": "...", "start":0, "end":12, "text":"Hypertension", "type":"Disease", "annotator":"anon", "timestamp":"..."} ],
  "relations": [ {"id": "...", "source_entity_id":"...", "target_entity_id":"...", "relation_type":"treats", "direction":"forward", "annotator":"anon", "timestamp":"..."} ]
}
```

## 4. Key Endpoints (FastAPI)
| Method | Path | Purpose |
|--------|------|---------|
| POST | /bootstrap | Load raw texts (creates docs if missing / loads saved JSON) |
| GET  | /documents | List documents in memory |
| POST | /documents | Create a new document (manual) |
| GET  | /documents/{id} | Retrieve full document state |
| POST | /documents/{id}/entities | Add entity |
| DELETE | /documents/{id}/entities/{entity_id} | Delete entity |
| POST | /documents/{id}/relations | Add relation |
| DELETE | /documents/{id}/relations/{relation_id} | Delete relation |
| PATCH | /documents/{id}/status | Update document status |
| GET | /documents/{id}/export | Export single document JSON |
| POST | /import | Import a previously exported document |
| POST | /save/all | Force persistence of all loaded docs |
| GET | /vocab | Retrieve vocab (entity & relation types) |
| GET | /suggest/entities?doc_id= | Heuristic entity suggestions |
| GET | /health | Liveness probe |

## 5. Frontend (Minimal Static UI)
- Single `index.html` served from `/ui`.
- Features: document selection, span-based entity creation (using DOM selection offsets), relation creation (checkbox selection of two entities), deletion, export view, manual save-all, suggestions acceptance.
- No framework: pure DOM & fetch for minimal footprint and clarity.

## 6. Suggestion Service Abstraction
`backend/app/suggestion_service.py`: heuristic pattern extraction (capitalization + keyword list). Accepts existing spans to avoid duplicates. Future swap-in point for real LLM (OpenAI/HuggingFace). Logging via stdout; can evolve into structured logging + provenance (model name, prompt hash).

## 7. Persistence Strategy & Rationale
- JSON per document keeps version-control friendly artifacts, simplifies manual inspection & diff.
- Auto-save on mutation reduces accidental loss; explicit `/save/all` + UI button acts as reassurance.
- Trade-off: No concurrent edit resolution. Acceptable for single-user / demo scope. Future: move to DB (PostgreSQL) or lightweight embedded (SQLite) and optimistic versioning.

## 8. Environment & Configuration
| Variable | Purpose | Default |
|----------|---------|---------|
| APP_ANNOTATOR | Default annotator identifier | anon |
| APP_ENV | Environment flag (dev) | dev |

## 9. Non-Goals (Current Iteration)
- Authentication & multi-user concurrency.
- Ontology/code lookup integration (SNOMED / RxNorm) — placeholder `code` field only.
- UI editing of entity spans (delete & re-create instead).
- Bulk relation creation or advanced relation types (only simple directional binary).
- Rich labeling UX (color-coded tags, drag handles, overlapping spans).

## 10. Error Handling & Edge Cases
| Case | Current Behavior | Future Hardening |
|------|------------------|------------------|
| Invalid document id | KeyError (FastAPI 500) | Return 404 with message |
| Overlapping entities | Allowed; UI may visually double-highlight | Add validation / warning |
| Deleting non-existent entity | Returns deleted: 0 | Distinguish 404 |
| Large documents | Linear scan for highlight; acceptable for small abstracts | Virtualize / index |
| Simultaneous writes | Last write wins, file overwrite | Introduce version field |

## 11. Security Considerations
- CORS wide open (`*`) for ease of local testing.
- No auth: assume trusted local environment.
- Potential path traversal not exposed (no arbitrary file reads). Future: tighten allowed origins, add auth header/token.

## 12. Extensibility Points
| Area | Extension |
|------|-----------|
| Suggestions | Replace heuristic with LLM call (OpenAI/HF) + caching / fallback |
| Persistence | Swap JSON for DB adapter interface (implement repository pattern) |
| Vocab | Add dynamic vocab endpoint (POST/PUT) with validation |
| Exports | Aggregate export (/export/all) or CSV transformation layer |
| UI | Framework migration (React/Vue) and richer annotation controls |
| Codes | Add code lookup microservice or local terminology file |
| Azure | Containerize & deploy (App Service or Container Apps) + Terraform IaC reintroduction |

## 13. Future Improvements (Short List)
1. Aggregate export endpoint (/export/all) & simple dataset packaging.
2. 404 error normalization + Pydantic response models for errors.
3. Optional overlapping-span prevention toggle.
4. Basic user identity (annotator) selection in UI.
5. Real LLM suggestion integration with prompt & response audit trail.
6. Screenshot / video generation automation (scripted browser capture).

## 14. Trade-offs & Rationale
- Chose JSON persistence over DB to minimize setup and emphasize transparency for assessment reviewers.
- Kept UI frameworkless to reduce build complexity and time; easier to extend later.
- Single file `main.py` for speed; acceptable given size, but modularization (routers/services) recommended post-MVP.
- Limited validation to maintain velocity; flagged in improvement list.

---
Minimal, auditable, and intentionally simple — ready for incremental enhancement.
