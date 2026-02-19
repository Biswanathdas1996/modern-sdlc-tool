"""Database connection management - backward compatibility wrapper.

This module re-exports from core.db for backward compatibility.
New code should import from core.db directly.
"""
from core.db.mongo import MongoDatabase, mongo_db, get_mongo_db

get_db = get_mongo_db

__all__ = [
    "MongoDatabase",
    "mongo_db",
    "get_db",
    "get_mongo_db",
]
