"""Embedding provider for semantic search.

This module provides the EmbeddingProvider class which manages text embeddings
using FastEmbed (local) with optional API fallback. Uses lazy loading to avoid
downloading models at startup.
"""

from typing import Optional
import struct

from loguru import logger

from nanobot.config.schema import EmbeddingConfig


class EmbeddingProvider:
    """
    Provider for text embeddings using FastEmbed (local) with API fallback.
    
    Uses lazy loading - models are downloaded on first use, not at startup.
    This prevents delays during bot initialization.
    """
    
    def __init__(self, config: EmbeddingConfig):
        """
        Initialize the embedding provider.
        
        Args:
            config: Embedding configuration
        """
        self.config = config
        self._model = None  # Lazy loaded
        self._model_loaded = False
        
        logger.info(f"EmbeddingProvider initialized (lazy loading: {config.lazy_load})")
    
    def _ensure_model(self):
        """Ensure model is loaded (lazy loading)."""
        if self._model is None and self.config.provider == "local":
            try:
                from fastembed import TextEmbedding
                
                logger.info(f"Loading embedding model: {self.config.local_model}")
                self._model = TextEmbedding(self.config.local_model)
                self._model_loaded = True
                logger.info("Embedding model loaded successfully")
            except Exception as e:
                logger.error(f"Failed to load local embedding model: {e}")
                if self.config.api_fallback:
                    logger.info("Will fallback to API embeddings")
                else:
                    raise
    
    def embed(self, text: str) -> list[float]:
        """
        Generate embedding for text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        if not text or not text.strip():
            # Return zero vector for empty text
            return [0.0] * 384  # bge-small-en-v1.5 = 384 dimensions
        
        if self.config.provider == "local":
            return self._embed_local(text)
        else:
            return self._embed_api(text)
    
    def _embed_local(self, text: str) -> list[float]:
        """Generate embedding using local FastEmbed model."""
        self._ensure_model()
        
        if self._model is None and self.config.api_fallback:
            logger.warning("Local model not available, using API fallback")
            return self._embed_api(text)
        
        try:
            # FastEmbed returns a generator, get the first (and only) result
            embeddings = list(self._model.embed([text]))
            if embeddings:
                return embeddings[0].tolist()
            else:
                logger.error("FastEmbed returned empty result")
                return [0.0] * 384
        except Exception as e:
            logger.error(f"Local embedding failed: {e}")
            if self.config.api_fallback:
                return self._embed_api(text)
            raise
    
    def _embed_api(self, text: str) -> list[float]:
        """Generate embedding using API (fallback)."""
        # TODO: Implement API embedding using OpenRouter or other provider
        # For now, return zero vector
        logger.warning("API embedding not yet implemented, returning zero vector")
        return [0.0] * 384
    
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.
        
        Args:
            texts: List of texts to embed
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        # Filter out empty texts
        valid_texts = [t for t in texts if t and t.strip()]
        
        if self.config.provider == "local":
            self._ensure_model()
            
            if self._model is None:
                # Fallback to individual API calls
                return [self._embed_api(t) for t in valid_texts]
            
            try:
                embeddings = list(self._model.embed(valid_texts))
                return [e.tolist() for e in embeddings]
            except Exception as e:
                logger.error(f"Batch embedding failed: {e}")
                if self.config.api_fallback:
                    return [self._embed_api(t) for t in valid_texts]
                raise
        else:
            return [self._embed_api(t) for t in valid_texts]
    
    def is_ready(self) -> bool:
        """Check if the provider is ready to generate embeddings."""
        if self.config.provider == "api":
            return True  # API is always "ready" (will make HTTP call)
        
        # For local, check if model is loaded or can be loaded
        if self._model_loaded:
            return True
        
        # Try to load model
        try:
            self._ensure_model()
            return self._model is not None
        except Exception:
            return False


def pack_embedding(embedding: list[float]) -> bytes:
    """
    Pack embedding vector into bytes for storage.
    
    Args:
        embedding: List of floats
        
    Returns:
        Packed bytes
    """
    return struct.pack(f'{len(embedding)}f', *embedding)


def unpack_embedding(data: bytes) -> list[float]:
    """
    Unpack embedding vector from bytes.
    
    Args:
        data: Packed bytes
        
    Returns:
        List of floats
    """
    if not data:
        return []
    
    num_floats = len(data) // 4  # 4 bytes per float
    return list(struct.unpack(f'{num_floats}f', data))


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """
    Calculate cosine similarity between two vectors.
    
    Args:
        a: First vector
        b: Second vector
        
    Returns:
        Cosine similarity (-1 to 1)
    """
    if len(a) != len(b):
        raise ValueError(f"Vectors must have same length: {len(a)} vs {len(b)}")
    
    if len(a) == 0:
        return 0.0
    
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    
    if norm_a == 0 or norm_b == 0:
        return 0.0
    
    return dot_product / (norm_a * norm_b)