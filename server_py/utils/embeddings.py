"""Embedding generation utility using fastembed (ONNX-based local embeddings).

Uses BAAI/bge-small-en-v1.5 model via ONNX runtime for generating 384-dimensional
embedding vectors locally without requiring external API calls.
"""
import math
from typing import List, Optional
from core.logging import log_info, log_error


_model = None


def _get_model():
    """Lazy-load the embedding model singleton."""
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        log_info("Loading embedding model BAAI/bge-small-en-v1.5...", "embeddings")
        _model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        log_info("Embedding model loaded successfully (384 dimensions)", "embeddings")
    return _model


def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate an embedding vector for a single text string.
    
    Args:
        text: The text to embed
    
    Returns:
        List of floats representing the 384-dim embedding vector, or None on error
    """
    try:
        clean_text = text.strip()
        if not clean_text:
            return None
        
        model = _get_model()
        embeddings = list(model.embed([clean_text]))
        return embeddings[0].tolist()
        
    except Exception as e:
        log_error(f"Embedding generation error: {e}", "embeddings")
        return None


def generate_embeddings_batch(texts: List[str], batch_size: int = 32) -> List[Optional[List[float]]]:
    """Generate embeddings for multiple texts in batches.
    
    Args:
        texts: List of texts to embed
        batch_size: Number of texts per batch
    
    Returns:
        List of embedding vectors (or None for failed/empty items)
    """
    if not texts:
        return []
    
    all_embeddings: List[Optional[List[float]]] = [None] * len(texts)
    
    clean_texts = []
    valid_indices = []
    for i, text in enumerate(texts):
        clean = text.strip()
        if clean:
            clean_texts.append(clean)
            valid_indices.append(i)
    
    if not clean_texts:
        return all_embeddings
    
    log_info(f"Generating embeddings for {len(clean_texts)} texts using BAAI/bge-small-en-v1.5", "embeddings")
    
    try:
        model = _get_model()
        embeddings = list(model.embed(clean_texts, batch_size=batch_size))
        
        for j, embedding in enumerate(embeddings):
            original_idx = valid_indices[j]
            all_embeddings[original_idx] = embedding.tolist()
        
        success_count = sum(1 for e in all_embeddings if e is not None)
        log_info(f"Embedding generation complete: {success_count}/{len(texts)} successful (384 dimensions each)", "embeddings")
        
    except Exception as e:
        log_error(f"Batch embedding error: {e}", "embeddings")
    
    return all_embeddings


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


def compute_corpus_similarity(query: str, corpus_texts: List[str]) -> List[float]:
    """Compute similarity between a query and a corpus of texts using embeddings.
    
    Args:
        query: The search query
        corpus_texts: List of corpus texts to compare against
    
    Returns:
        List of similarity scores (one per corpus text)
    """
    if not query or not corpus_texts:
        return [0.0] * len(corpus_texts)
    
    try:
        query_embedding = generate_embedding(query)
        if query_embedding is None:
            return [0.0] * len(corpus_texts)
        
        corpus_embeddings = generate_embeddings_batch(corpus_texts)
        
        scores = []
        for emb in corpus_embeddings:
            if emb is not None:
                scores.append(cosine_similarity(query_embedding, emb))
            else:
                scores.append(0.0)
        
        return scores
    except Exception as e:
        log_error(f"Corpus similarity error: {e}", "embeddings")
        return [0.0] * len(corpus_texts)
