"""Database connection management."""
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database
from core.config import get_settings


class MongoDatabase:
    """MongoDB database manager."""
    
    def __init__(self):
        self.client: Optional[MongoClient] = None
        self.db: Optional[Database] = None
        self.settings = get_settings()
        
    def connect(self) -> Database:
        """Connect to MongoDB and return database instance."""
        if self.db is not None:
            return self.db
            
        if not self.settings.mongodb_uri:
            raise ValueError("MONGODB_URI environment variable is not set")
            
        try:
            self.client = MongoClient(self.settings.mongodb_uri)
            self.db = self.client[self.settings.mongodb_db_name]
            print(f"✓ Connected to MongoDB: {self.settings.mongodb_db_name}")
            self._ensure_indexes()
            return self.db
        except Exception as error:
            print(f"✗ Failed to connect to MongoDB: {error}")
            raise
            
    def _ensure_indexes(self):
        """Ensure required indexes exist."""
        if self.db is None:
            return
            
        chunks_collection = self.db["knowledge_chunks"]
        
        try:
            indexes = list(chunks_collection.list_indexes())
            has_text_index = any(
                idx.get("name") == "text_search_index" 
                for idx in indexes
            )
            
            if not has_text_index:
                print("Creating text search index...")
                chunks_collection.create_index(
                    [("content", "text")], 
                    name="text_search_index"
                )
                print("✓ Text search index created")
        except Exception as error:
            print(f"Index setup note: {error}")
            
    def disconnect(self):
        """Disconnect from MongoDB."""
        if self.client is not None:
            self.client.close()
            self.client = None
            self.db = None
            print("✓ Disconnected from MongoDB")
            
    def get_database(self) -> Database:
        """Get the database instance, connecting if necessary."""
        if self.db is None:
            return self.connect()
        return self.db


# Global database instance
mongo_db = MongoDatabase()


def get_db() -> Database:
    """Dependency for getting database instance."""
    return mongo_db.get_database()
