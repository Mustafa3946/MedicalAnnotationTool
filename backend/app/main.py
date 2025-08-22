from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import json
import uuid

app = FastAPI(title="Medical Annotation API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    direction: str = "forward"
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

# --- API Endpoints ---
@app.post("/documents", response_model=Document)
def create_document(doc: Document):
    DOCUMENTS[doc.id] = doc
    return doc

@app.get("/documents", response_model=List[Document])
def list_documents():
    return list(DOCUMENTS.values())

@app.get("/documents/{doc_id}", response_model=Document)
def get_document(doc_id: str):
    return DOCUMENTS[doc_id]

@app.post("/documents/{doc_id}/entities", response_model=Entity)
def add_entity(doc_id: str, entity: Entity):
    DOCUMENTS[doc_id].entities.append(entity)
    return entity

@app.post("/documents/{doc_id}/relations", response_model=Relation)
def add_relation(doc_id: str, relation: Relation):
    DOCUMENTS[doc_id].relations.append(relation)
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
    return {"status": "imported", "document_id": doc.id}

@app.get("/health")
def health():
    return {"status": "ok"}
