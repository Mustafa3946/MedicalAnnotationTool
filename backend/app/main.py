from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse
from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime
import json
from .suggestion_service import suggest_entities
import os
import glob
from pathlib import Path
import uuid

app = FastAPI(title="Medical Annotation API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Consider restricting in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend static under /ui to avoid clobbering API routes
app.mount("/ui", StaticFiles(directory="frontend", html=True), name="frontend")

@app.get("/")
def root_index():
    # Redirect to UI index
    return RedirectResponse(url="/ui/")

# --- Data Models ---
class Entity(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    start: int
    end: int
    text: str
    type: str
    code: Optional[str] = None
    annotator: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class Relation(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_entity_id: str
    target_entity_id: str
    relation_type: str
    direction: Literal["forward", "reverse"] = "forward"
    annotator: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class Document(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    status: str = "in_progress"
    entities: List[Entity] = []
    relations: List[Relation] = []

# In-memory store (replace with persistent storage later)
DOCUMENTS: dict[str, Document] = {}

# Default annotator (can be overridden via environment variable APP_ANNOTATOR)
DEFAULT_ANNOTATOR = os.getenv("APP_ANNOTATOR", "anon")

# --- Persistence (Step 1: directory + save on create) ---
ANNOTATIONS_DIR = Path("data") / "annotations"
try:
    ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:  # pragma: no cover
    print(f"[warn] unable to create annotations dir: {e}")

def save_document(doc: Document):
    """Persist a single document to JSON (minimal; overwrites)."""
    try:
        path = ANNOTATIONS_DIR / f"{doc.id}.json"
        with open(path, "w", encoding="utf-8") as f:
            f.write(doc.json())
    except Exception as e:  # pragma: no cover
        print(f"[warn] save failed for {doc.id}: {e}")

# Load vocab (lazy or at startup)
_VOCAB_CACHE: dict | None = None

def load_vocab() -> dict:
    global _VOCAB_CACHE
    if _VOCAB_CACHE is not None:
        return _VOCAB_CACHE
    # Search typical locations: running inside repo root or inside Docker /app
    candidates = [
        os.path.join("data", "vocab.json"),               # repo root while running locally
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "vocab.json"),  # relative traversal
    ]
    for path in candidates:
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as f:
                _VOCAB_CACHE = json.load(f)
                return _VOCAB_CACHE
    # Fallback minimal default if file not found
    _VOCAB_CACHE = {
        "entity_types": ["Disease", "Medication", "Symptom", "Procedure"],
        "relation_types": ["treats", "causes", "indicates"],
    }
    return _VOCAB_CACHE

# --- API Endpoints ---
@app.post("/documents", response_model=Document)
def create_document(doc: Document):
    DOCUMENTS[doc.id] = doc
    save_document(doc)  # initial persistence
    return doc

@app.get("/documents", response_model=List[Document])
def list_documents():
    return list(DOCUMENTS.values())

@app.get("/documents/{doc_id}", response_model=Document)
def get_document(doc_id: str):
    return DOCUMENTS[doc_id]

@app.post("/documents/{doc_id}/entities", response_model=Entity)
def add_entity(doc_id: str, entity: Entity):
    # Auto-populate annotator if not provided
    if entity.annotator is None:
        entity.annotator = DEFAULT_ANNOTATOR
    DOCUMENTS[doc_id].entities.append(entity)
    save_document(DOCUMENTS[doc_id])
    return entity

@app.post("/documents/{doc_id}/relations", response_model=Relation)
def add_relation(doc_id: str, relation: Relation):
    if relation.annotator is None:
        relation.annotator = DEFAULT_ANNOTATOR
    DOCUMENTS[doc_id].relations.append(relation)
    save_document(DOCUMENTS[doc_id])
    return relation

@app.get("/documents/{doc_id}/export")
def export_document(doc_id: str):
    doc = DOCUMENTS[doc_id]
    return json.loads(doc.json())

@app.post("/import")
def import_annotations(file: UploadFile = File(...)):
    data = json.loads(file.file.read())
    doc = Document(**data)
    DOCUMENTS[doc.id] = doc
    save_document(doc)
    return {"status": "imported", "document_id": doc.id}

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/vocab")
def get_vocab():
    return load_vocab()

@app.get("/suggest/entities")
def suggest_entities_endpoint(doc_id: str):
    if doc_id not in DOCUMENTS:
        return {"error": "document not found"}
    doc = DOCUMENTS[doc_id]
    existing = [(e.start, e.end) for e in doc.entities]
    suggestions = suggest_entities(doc.text, existing)
    # Log suggestions (simple stdout log)
    print(f"[suggest] doc={doc_id} count={len(suggestions)}")
    return {"document_id": doc_id, "suggestions": suggestions}

@app.post("/save/all")
def save_all():
    for doc in DOCUMENTS.values():
        save_document(doc)
    return {"status": "saved", "count": len(DOCUMENTS)}
# --- Bootstrap abstracts ---
def _extract_core_text(raw: str) -> str:
    # Try to extract quoted main text if present
    if raw.count("\"") >= 2:
        first = raw.find("\"")
        last = raw.rfind("\"")
        if last - first > 20:  # ensure non-trivial length
            return raw[first+1:last].strip()
    # Fallback: remove lines starting with 'Entities'/'Relations' examples
    lines = [ln for ln in raw.splitlines() if not ln.startswith("Entities") and not ln.startswith("Relations") and not ln.startswith("Use Case")]
    return "\n".join(lines).strip()

@app.post("/bootstrap", response_model=List[Document])
@app.get("/bootstrap", response_model=List[Document])
def bootstrap():
    """Load raw abstracts from data/raw/*.txt into memory (id = filename stem)."""
    base_candidates = [
        Path("data") / "raw",
        Path(__file__).resolve().parent / ".." / ".." / "data" / "raw",
    ]
    loaded_docs: List[Document] = []
    for folder in base_candidates:
        if folder.is_dir():
            for path in folder.glob("*.txt"):
                doc_id = path.stem
                # If already in memory, reuse
                if doc_id in DOCUMENTS:
                    loaded_docs.append(DOCUMENTS[doc_id])
                    continue
                # If persisted JSON exists, load it instead of raw
                persisted = ANNOTATIONS_DIR / f"{doc_id}.json"
                if persisted.is_file():
                    try:
                        with open(persisted, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        doc = Document(**data)
                        DOCUMENTS[doc.id] = doc
                        loaded_docs.append(doc)
                        continue
                    except Exception as e:  # pragma: no cover
                        print(f"[warn] failed to load persisted {persisted}: {e}")
                # Fall back to raw text ingestion
                raw = path.read_text(encoding="utf-8")
                core = _extract_core_text(raw)
                doc = Document(id=doc_id, text=core)
                DOCUMENTS[doc.id] = doc
                loaded_docs.append(doc)
            break  # stop after first existing folder processed
    return loaded_docs
