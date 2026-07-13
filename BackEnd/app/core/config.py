import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "sqlite:///./data/ia_cargas.db"
    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection_name: str = "sga_documents"
    embeddings_model: str = "models/gemini-embedding-2"
    ollama_base_url: str = "http://host.docker.internal:11434"
    upload_dir: str = "./data/uploads/pdfs"
    gemini_api_key: str = ""
    cors_origins: str = "http://localhost:5173"
    
    class Config:
        env_file = ".env"
        extra = "allow"

settings = Settings()

DATABASE_URL = settings.database_url
QDRANT_URL = settings.qdrant_url
OLLAMA_URL = settings.ollama_base_url
UPLOAD_DIR = settings.upload_dir
