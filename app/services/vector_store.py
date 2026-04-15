import os
import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
from app.database.connection import SessionLocal
from app.models.db_models import QAPair

# Using a lightweight multilingual model for embeddings
_model = None

def get_embedding_model():
    global _model
    if _model is None:
        _model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    return _model

# Global FAISS index for simplicity, could persist to disk
_index = None
_qa_mapping = {}  # index_in_faiss -> qa_id

def init_index():
    """Initializes the FAISS index with existing data."""
    global _index, _qa_mapping
    model = get_embedding_model()
    dimension = model.get_sentence_embedding_dimension()
    _index = faiss.IndexFlatL2(dimension)
    
    db = SessionLocal()
    pairs = db.query(QAPair).all()
    if pairs:
        texts = [p.question + " " + p.answer for p in pairs]
        embeddings = model.encode(texts)
        _index.add(np.array(embeddings, dtype=np.float32))
        
        for i, p in enumerate(pairs):
            _qa_mapping[i] = p.id
    db.close()

def search_similar_qa(query: str, top_k: int = 3):
    global _index, _qa_mapping
    if _index is None or _index.ntotal == 0:
        return []
        
    model = get_embedding_model()
    query_vector = model.encode([query])
    
    # search
    distances, indices = _index.search(np.array(query_vector, dtype=np.float32), top_k)
    
    db = SessionLocal()
    results = []
    for idx in indices[0]:
        if idx != -1 and idx in _qa_mapping:
            qa_id = _qa_mapping[idx]
            from sqlalchemy.orm import joinedload
            qa = db.query(QAPair).options(joinedload(QAPair.video)).filter(QAPair.id == qa_id).first()
            if qa:
                results.append(qa)
    db.close()
    return results

def add_to_index(qa: QAPair):
    """Add a newly created QA pair to the index directly."""
    global _index, _qa_mapping
    if _index is None:
        init_index()
        return
        
    model = get_embedding_model()
    text = qa.question + " " + qa.answer
    embedding = model.encode([text])
    _index.add(np.array(embedding, dtype=np.float32))
    new_idx = _index.ntotal - 1
    _qa_mapping[new_idx] = qa.id
