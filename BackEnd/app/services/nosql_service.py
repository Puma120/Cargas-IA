from pymongo import MongoClient
from typing import Any, Dict
import os
import logging

logger = logging.getLogger(__name__)

class NoSQLService:
    def __init__(self):
        # Use host.docker.internal to connect to MongoDB running on the host machine from inside Docker
        self.url = os.getenv("NOSQL_URL", "mongodb://host.docker.internal:27017")
        self.db_name = "CargasIA_Migration"
        try:
            self.client = MongoClient(self.url)
            self.db = self.client[self.db_name]
            logger.info(f"Connected to NoSQL database at {self.url}")
        except Exception as e:
            logger.error(f"Could not connect to NoSQL: {e}")
            raise e

    def save_document(self, collection_name: str, document: Dict[str, Any]):
        """
        Saves a document into a specific collection.
        """
        try:
            print(f"[NOSQL] Guardando documento en colección '{collection_name}'...")
            collection = self.db[collection_name]
            result = collection.insert_one(document)
            return str(result.inserted_id)
        except Exception as e:
            print(f"[NOSQL] ERROR guardando en colección {collection_name}: {e}")
            logger.error(f"Error saving to NoSQL collection {collection_name}: {e}")
            raise e
