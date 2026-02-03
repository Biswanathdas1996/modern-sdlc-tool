"""Project repository."""
from typing import List, Optional
from repositories.base import BaseRepository
from schemas.entities import Project


class ProjectRepository(BaseRepository[Project]):
    """Repository for project entities."""
    
    def __init__(self):
        super().__init__(Project)
        
    def get_all_sorted(self) -> List[Project]:
        """Get all projects sorted by analyzed date."""
        projects = self.get_all()
        return sorted(projects, key=lambda p: p.analyzedAt, reverse=True)
        
    def get_by_repo_url(self, repo_url: str) -> Optional[Project]:
        """Get project by repository URL."""
        for project in self._storage.values():
            if project.repoUrl == repo_url:
                return project
        return None
