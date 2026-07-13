"""Servicio de base de datos vectorial (Qdrant).

Maneja la conexión con Qdrant y provee un VectorStore de LangChain
para indexar y buscar embeddings generados por Ollama.
"""
import logging
from typing import Optional

from qdrant_client import QdrantClient
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore

from app.core.config import settings

logger = logging.getLogger(__name__)

# Singleton del cliente Qdrant
_qdrant_client: Optional[QdrantClient] = None


def get_qdrant_client() -> QdrantClient:
    """Retorna el cliente base de Qdrant (singleton)."""
    global _qdrant_client

    if _qdrant_client is not None:
        return _qdrant_client

    try:
        _qdrant_client = QdrantClient(url=settings.qdrant_url)
        logger.info(f"Conectado a Qdrant en {settings.qdrant_url}")
        return _qdrant_client
    except Exception as e:
        logger.warning(f"Error conectando a Qdrant en {settings.qdrant_url}: {e}. Usando in-memory.")
        _qdrant_client = QdrantClient(":memory:")
        return _qdrant_client


def get_embeddings() -> GoogleGenerativeAIEmbeddings:
    """Retorna el modelo de embeddings de Google."""
    return GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-2",
        google_api_key=settings.gemini_api_key,
    )


def get_vector_store() -> QdrantVectorStore:
    """
    Configura y retorna el VectorStore de LangChain para Qdrant.
    Usa el modelo de embeddings de Google.
    """
    embeddings = get_embeddings()
    client = get_qdrant_client()
    collection_name = settings.qdrant_collection_name

    try:
        sample_embedding = embeddings.embed_query("test")
        vector_size = len(sample_embedding)

        if not client.collection_exists(collection_name):
            logger.info(f"La colección '{collection_name}' no existe. Creándola con dimensión {vector_size}...")
            from qdrant_client.models import VectorParams, Distance
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
            )
            logger.info(f"Colección '{collection_name}' creada.")
        else:
            # Verificar si la dimensión coincide
            collection_info = client.get_collection(collection_name)
            current_size = collection_info.config.params.vectors.size
            if current_size != vector_size:
                logger.warning(f"Mismatch de dimensiones: Qdrant tiene {current_size}, el modelo {settings.embeddings_model} usa {vector_size}. Recreando colección para evitar errores...")
                client.delete_collection(collection_name)
                from qdrant_client.models import VectorParams, Distance
                client.create_collection(
                    collection_name=collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
                )
                logger.info(f"Colección recreada con dimensión {vector_size}.")
    except Exception as e:
        logger.error(f"Error al verificar/crear la colección en Qdrant: {e}")

    vector_store = QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        embedding=embeddings,
    )

    return vector_store


def get_knowledge_vector_store() -> QdrantVectorStore:
    """
    Configura y retorna el VectorStore de LangChain para la Base de Conocimientos (sga_knowledge_base).
    """
    embeddings = get_embeddings()
    client = get_qdrant_client()
    collection_name = "sga_knowledge_base"

    try:
        sample_embedding = embeddings.embed_query("test")
        vector_size = len(sample_embedding)

        if not client.collection_exists(collection_name):
            logger.info(f"La colección '{collection_name}' no existe. Creándola con dimensión {vector_size}...")
            from qdrant_client.models import VectorParams, Distance
            client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE)
            )
            logger.info(f"Colección '{collection_name}' creada.")
    except Exception as e:
        logger.error(f"Error al verificar/crear la colección {collection_name} en Qdrant: {e}")

    vector_store = QdrantVectorStore(
        client=client,
        collection_name=collection_name,
        embedding=embeddings,
    )

    return vector_store
