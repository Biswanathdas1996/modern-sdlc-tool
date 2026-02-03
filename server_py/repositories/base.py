"""Base repository with common CRUD operations."""
from typing import Dict, List, Optional, TypeVar, Generic, Type
from datetime import datetime
import uuid
from pydantic import BaseModel


T = TypeVar('T', bound=BaseModel)


class BaseRepository(Generic[T]):
    """Base repository for in-memory storage."""
    
    def __init__(self, model_class: Type[T]):
        self.model_class = model_class
        self._storage: Dict[str, T] = {}
        
    def get_by_id(self, id: str) -> Optional[T]:
        """Get entity by ID."""
        return self._storage.get(id)
        
    def get_all(self) -> List[T]:
        """Get all entities."""
        return list(self._storage.values())
        
    def create(self, data: dict) -> T:
        """Create a new entity."""
        if 'id' not in data:
            data['id'] = str(uuid.uuid4())
        if 'createdAt' not in data:
            data['createdAt'] = datetime.utcnow().isoformat()
            
        entity = self.model_class(**data)
        self._storage[entity.id] = entity
        return entity
        
    def update(self, id: str, updates: dict) -> Optional[T]:
        """Update an entity."""
        entity = self._storage.get(id)
        if not entity:
            return None
            
        entity_dict = entity.model_dump()
        entity_dict.update(updates)
        
        if 'updatedAt' in self.model_class.model_fields:
            entity_dict['updatedAt'] = datetime.utcnow().isoformat()
            
        updated = self.model_class(**entity_dict)
        self._storage[id] = updated
        return updated
        
    def delete(self, id: str) -> bool:
        """Delete an entity."""
        if id in self._storage:
            del self._storage[id]
            return True
        return False
        
    def clear(self):
        """Clear all entities."""
        self._storage.clear()
