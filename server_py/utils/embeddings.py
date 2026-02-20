"""Embedding generation utility using TF-IDF vectorization.

Since the available AI endpoints (PWC GenAI and Replit modelfarm) do not support
embedding endpoints, this module implements TF-IDF-based vectorization for
semantic similarity search. TF-IDF captures term importance within documents
relative to the corpus, providing effective semantic matching without external APIs.
"""
import math
import re
from typing import List, Dict, Optional, Tuple
from collections import Counter
from core.logging import log_info, log_error


STOP_WORDS = frozenset({
    'the', 'and', 'for', 'with', 'this', 'that', 'from', 'are', 'was', 'were',
    'been', 'have', 'has', 'not', 'but', 'its', 'can', 'will', 'would', 'could',
    'should', 'may', 'might', 'shall', 'must', 'need', 'does', 'did', 'had',
    'being', 'having', 'doing', 'than', 'then', 'when', 'where', 'which', 'who',
    'whom', 'what', 'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most',
    'other', 'some', 'such', 'only', 'own', 'same', 'too', 'very', 'just', 'also',
    'into', 'over', 'after', 'before', 'between', 'under', 'above', 'below',
    'out', 'off', 'about', 'around', 'through', 'during', 'without', 'again',
    'further', 'once', 'here', 'there', 'any', 'nor', 'yet', 'while',
})


def _tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase words, removing stop words and short tokens."""
    words = re.findall(r'[a-zA-Z][a-zA-Z0-9_]*', text.lower())
    return [w for w in words if len(w) > 2 and w not in STOP_WORDS]


def _compute_tf(tokens: List[str]) -> Dict[str, float]:
    """Compute term frequency (normalized by document length)."""
    if not tokens:
        return {}
    counts = Counter(tokens)
    total = len(tokens)
    return {term: count / total for term, count in counts.items()}


def _compute_idf(documents_tokens: List[List[str]]) -> Dict[str, float]:
    """Compute inverse document frequency across a corpus."""
    n_docs = len(documents_tokens)
    if n_docs == 0:
        return {}
    
    doc_freq: Dict[str, int] = {}
    for tokens in documents_tokens:
        unique_terms = set(tokens)
        for term in unique_terms:
            doc_freq[term] = doc_freq.get(term, 0) + 1
    
    return {
        term: math.log((n_docs + 1) / (df + 1)) + 1
        for term, df in doc_freq.items()
    }


def generate_tfidf_vectors(texts: List[str]) -> Tuple[List[Optional[List[float]]], List[str]]:
    """Generate TF-IDF vectors for a list of texts.
    
    Args:
        texts: List of text strings to vectorize
    
    Returns:
        Tuple of (list of vectors, list of vocabulary terms)
    """
    if not texts:
        return [], []
    
    all_tokens = [_tokenize(text) for text in texts]
    
    idf = _compute_idf(all_tokens)
    
    vocab = sorted(idf.keys())
    vocab_index = {term: i for i, term in enumerate(vocab)}
    vocab_size = len(vocab)
    
    if vocab_size == 0:
        return [None] * len(texts), []
    
    vectors: List[Optional[List[float]]] = []
    
    for tokens in all_tokens:
        if not tokens:
            vectors.append(None)
            continue
        
        tf = _compute_tf(tokens)
        
        vec = [0.0] * vocab_size
        for term, tf_val in tf.items():
            if term in vocab_index:
                vec[vocab_index[term]] = tf_val * idf[term]
        
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        
        vectors.append(vec)
    
    log_info(f"Generated TF-IDF vectors for {len(texts)} texts (vocab size: {vocab_size})", "embeddings")
    return vectors, vocab


def generate_query_vector(query: str, vocab: List[str], idf: Dict[str, float]) -> Optional[List[float]]:
    """Generate a TF-IDF vector for a query using existing vocabulary.
    
    Args:
        query: The search query text
        vocab: The vocabulary terms from the corpus
        idf: The IDF values from the corpus
    
    Returns:
        Normalized TF-IDF vector for the query, or None if empty
    """
    tokens = _tokenize(query)
    if not tokens:
        return None
    
    tf = _compute_tf(tokens)
    vocab_index = {term: i for i, term in enumerate(vocab)}
    
    vec = [0.0] * len(vocab)
    for term, tf_val in tf.items():
        if term in vocab_index:
            vec[vocab_index[term]] = tf_val * idf.get(term, 1.0)
    
    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    else:
        return None
    
    return vec


def generate_embeddings_batch(texts: List[str]) -> List[Optional[List[float]]]:
    """Generate embeddings for multiple texts using TF-IDF vectorization.
    
    This is the main entry point used by the knowledge base service.
    Generates self-contained TF-IDF vectors for a batch of texts.
    
    Args:
        texts: List of texts to embed
    
    Returns:
        List of embedding vectors (or None for failed items)
    """
    if not texts:
        return []
    
    vectors, vocab = generate_tfidf_vectors(texts)
    
    success_count = sum(1 for v in vectors if v is not None)
    log_info(f"Batch embedding complete: {success_count}/{len(texts)} successful", "embeddings")
    
    return vectors


def generate_embedding(text: str) -> Optional[List[float]]:
    """Generate an embedding vector for a single text string.
    
    Note: For single query embeddings against an existing corpus, prefer
    using generate_query_vector() with the corpus vocabulary for consistency.
    
    Args:
        text: The text to embed
    
    Returns:
        TF-IDF vector or None on error
    """
    if not text or not text.strip():
        return None
    
    vectors, _ = generate_tfidf_vectors([text])
    return vectors[0] if vectors else None


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two vectors.
    
    Handles vectors of different lengths by using the shorter length.
    """
    min_len = min(len(vec_a), len(vec_b))
    if min_len == 0:
        return 0.0
    
    dot_product = sum(vec_a[i] * vec_b[i] for i in range(min_len))
    norm_a = math.sqrt(sum(vec_a[i] * vec_a[i] for i in range(min_len)))
    norm_b = math.sqrt(sum(vec_b[i] * vec_b[i] for i in range(min_len)))
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)


def compute_corpus_similarity(query: str, corpus_texts: List[str]) -> List[float]:
    """Compute similarity between a query and a corpus of texts.
    
    Builds a unified TF-IDF space from query + corpus for accurate comparison.
    
    Args:
        query: The search query
        corpus_texts: List of corpus texts to compare against
    
    Returns:
        List of similarity scores (one per corpus text)
    """
    if not query or not corpus_texts:
        return [0.0] * len(corpus_texts)
    
    all_texts = [query] + corpus_texts
    all_tokens = [_tokenize(text) for text in all_texts]
    
    idf = _compute_idf(all_tokens)
    vocab = sorted(idf.keys())
    
    if not vocab:
        return [0.0] * len(corpus_texts)
    
    vocab_index = {term: i for i, term in enumerate(vocab)}
    vocab_size = len(vocab)
    
    def make_vector(tokens):
        tf = _compute_tf(tokens)
        vec = [0.0] * vocab_size
        for term, tf_val in tf.items():
            if term in vocab_index:
                vec[vocab_index[term]] = tf_val * idf[term]
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            vec = [v / norm for v in vec]
        return vec
    
    query_vec = make_vector(all_tokens[0])
    
    scores = []
    for i in range(1, len(all_tokens)):
        doc_vec = make_vector(all_tokens[i])
        similarity = sum(q * d for q, d in zip(query_vec, doc_vec))
        scores.append(similarity)
    
    return scores
