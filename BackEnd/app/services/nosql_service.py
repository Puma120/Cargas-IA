from pymongo import MongoClient
from typing import Any, Dict
import os
import logging

logger = logging.getLogger(__name__)

class NoSQLService:
    def __init__(self):
        # Conexión al servicio 'mongodb' definido en docker-compose
        self.url = os.getenv("NOSQL_URL", "mongodb://mongodb:27017")
        self.db_name = "CargasIA_Migration"
        try:
            self.client = MongoClient(self.url, serverSelectionTimeoutMS=5000)
            self.db = self.client[self.db_name]
            # Verificar conexión
            self.client.server_info()
            logger.info(f"Connected to NoSQL database at {self.url}")
        except Exception as e:
            logger.warning(f"Initial connection check to NoSQL failed, will retry lazily: {e}")

    def list_collections(self):
        """Returns a list of existing collections in the database."""
        return self.db.list_collection_names()

    def save_document(self, collection_name: str, document: Dict[str, Any]):
        """
        Saves a document into a collection, dynamically creating/matching it.
        """
        try:
            # 1. Resolver colección
            # Normalización simple: snake_case sugerido
            normalized_name = collection_name.lower().replace(" ", "_")
            
            # Simple match por existencia
            existing_collections = self.list_collections()
            
            target_collection = "generic_migration"
            if normalized_name in existing_collections:
                target_collection = normalized_name
                print(f"[NOSQL] Match encontrado: {target_collection}")
            else:
                # Si es una propuesta válida, usamos el nombre propuesto para crearla
                if normalized_name and normalized_name != "generic_migration":
                    target_collection = normalized_name
                    print(f"[NOSQL] Creando nueva colección: {target_collection}")
                else:
                    print(f"[NOSQL] Usando fallback: generic_migration")

            collection = self.db[target_collection]
            result = collection.insert_one(document)
            
            # Audit log
            print(f"[NOSQL] Guardado en: {target_collection}")
            return str(result.inserted_id), target_collection
        except Exception as e:
            logger.error(f"Error saving to NoSQL: {e}")
            raise e
