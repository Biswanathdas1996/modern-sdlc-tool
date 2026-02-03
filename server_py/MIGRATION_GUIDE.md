# Migration Guide: Old to New Structure

This guide helps you migrate from the old monolithic `main.py` to the new modular structure.

## 🎯 Overview

The old backend had everything in a few large files. The new structure separates concerns into logical layers:
- **API Layer**: HTTP endpoints
- **Service Layer**: Business logic
- **Repository Layer**: Data access
- **Schema Layer**: Type definitions

## 📋 Step-by-Step Migration

### Step 1: Update Imports

#### Old Way:
```python
from storage import storage
from models import Project, BRD, UserStory
from ai import generate_brd, analyze_repository
from jira_service import sync_stories_to_jira
```

#### New Way:
```python
from repositories import storage
from schemas import Project, BRD, UserStory
from services import ai_service, jira_service
```

### Step 2: Use Configuration

#### Old Way:
```python
import os

API_KEY = os.environ.get("PWC_GENAI_API_KEY", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL")
```

#### New Way:
```python
from core.config import get_settings

settings = get_settings()
api_key = settings.pwc_genai_api_key
jira_email = settings.jira_email
```

### Step 3: Use Structured Logging

#### Old Way:
```python
print(f"Error: {e}")
print(f"{datetime.now()} [express] Processing request")
```

#### New Way:
```python
from core.logging import log_error, log_info

log_error("Processing failed", "api", exc=e)
log_info("Processing request", "api")
```

### Step 4: Handle Errors Properly

#### Old Way:
```python
if not project:
    raise HTTPException(status_code=404, detail="Project not found")
    
raise HTTPException(status_code=500, detail="Failed to process")
```

#### New Way:
```python
from utils.exceptions import not_found, internal_error

if not project:
    raise not_found("Project")
    
raise internal_error("Failed to process")
```

### Step 5: Use Services for Business Logic

#### Old Way:
```python
# All in the route handler
@app.post("/api/brd/generate")
async def generate_brd_endpoint():
    # 50+ lines of business logic here
    feature_request = storage.get_current_feature_request()
    analysis = storage.get_analysis(project_id)
    # ... lots more code
    brd = await generate_brd(feature_request, analysis, ...)
    storage.create_brd(brd)
    return brd
```

#### New Way:
```python
# Thin router
@router.post("/brd/generate")
async def generate_brd_endpoint():
    service = BRDService()
    return await service.generate_brd()

# In services/brd_service.py
class BRDService:
    async def generate_brd(self):
        # All business logic here
        feature_request = storage.get_current_feature_request()
        analysis = storage.get_analysis(project_id)
        # ... logic ...
        brd = await ai_service.generate_brd(...)
        return storage.create_brd(brd)
```

## 🔄 Common Migration Patterns

### Pattern 1: Moving an Endpoint

**Old (`main.py`):**
```python
@app.get("/api/projects/{id}")
async def get_project(id: str):
    try:
        project = storage.get_project(id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project.model_dump()
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Failed")
```

**New (`api/v1/projects.py`):**
```python
from fastapi import APIRouter
from repositories import storage
from utils.exceptions import not_found, internal_error
from core.logging import log_error

router = APIRouter(prefix="/projects", tags=["projects"])

@router.get("/{id}")
async def get_project(id: str):
    try:
        project = storage.get_project(id)
        if not project:
            raise not_found("Project")
        return project.model_dump()
    except HTTPException:
        raise
    except Exception as e:
        log_error(f"Error fetching project {id}", "api", e)
        raise internal_error("Failed to fetch project")
```

### Pattern 2: Extracting Business Logic to Service

**Old (`main.py`):**
```python
@app.post("/api/jira/sync")
async def sync_to_jira():
    # Business logic mixed with HTTP handling
    creds = {
        "email": os.environ.get("JIRA_EMAIL"),
        "token": os.environ.get("JIRA_API_TOKEN")
    }
    auth = base64.b64encode(f"{creds['email']}:{creds['token']}".encode())
    # ... 100+ lines of JIRA logic ...
```

**New (`api/v1/jira.py` + `services/jira_service.py`):**
```python
# api/v1/jira.py (thin router)
@router.post("/sync")
async def sync_to_jira():
    try:
        service = jira_service
        stories = storage.get_user_stories(brd_id)
        return await service.sync_stories_to_jira(stories, storage)
    except ValueError as e:
        raise bad_request(str(e))

# services/jira_service.py (business logic)
class JiraService:
    def __init__(self):
        self.settings = get_settings()
    
    async def sync_stories_to_jira(self, stories, storage):
        # All JIRA logic here
        auth_header = self._get_auth_header()
        # ... JIRA operations ...
```

### Pattern 3: Using Type-Safe Schemas

**Old (`main.py`):**
```python
@app.post("/api/requirements")
async def create_requirements(request: Request):
    body = await request.json()
    title = body.get("title")  # Could be None!
    description = body.get("description")  # Could be wrong type!
    # No validation
```

**New (`api/v1/requirements.py`):**
```python
from schemas import RequirementsRequest

@router.post("")
async def create_requirements(request: RequirementsRequest):
    # Guaranteed to have validated fields
    title = request.title  # Always a string
    description = request.description  # Optional[str], validated
```

## 📚 Complete Endpoint Migration Example

Let's migrate the `/api/test-cases/generate` endpoint:

### Old Code (`main.py`):
```python
@app.post("/api/test-cases/generate")
async def generate_test_cases_endpoint():
    try:
        brd = storage.get_current_brd()
        if not brd:
            raise HTTPException(status_code=400, detail="No BRD found")
        
        projects = storage.get_all_projects()
        analysis = storage.get_analysis(projects[0].id) if projects else None
        documentation = storage.get_documentation(projects[0].id) if projects else None
        
        test_cases = await generate_test_cases(
            brd.model_dump(),
            analysis.model_dump() if analysis else None,
            documentation.model_dump() if documentation else None
        )
        
        if not test_cases:
            raise HTTPException(status_code=500, detail="Failed to generate")
        
        saved_test_cases = storage.create_test_cases(test_cases)
        return [tc.model_dump() for tc in saved_test_cases]
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error: {e}")
        raise HTTPException(status_code=500, detail="Failed")
```

### New Code:

**1. Create Service (`services/test_case_service.py`):**
```python
from typing import List, Dict, Any, Optional
from repositories import storage
from services import ai_service
from core.logging import log_info, log_error
from utils.exceptions import ValidationError


class TestCaseService:
    """Service for test case generation and management."""
    
    async def generate_test_cases(self) -> List[Dict[str, Any]]:
        """Generate test cases from current BRD."""
        # Get BRD
        brd = storage.get_current_brd()
        if not brd:
            raise ValidationError("No BRD found. Please generate a BRD first.")
        
        # Get context
        projects = storage.get_all_projects()
        analysis = None
        documentation = None
        
        if projects:
            analysis = storage.get_analysis(projects[0].id)
            documentation = storage.get_documentation(projects[0].id)
        
        log_info("Generating test cases from BRD", "test-cases")
        
        # Generate using AI service
        test_cases = await self._generate_with_ai(brd, analysis, documentation)
        
        if not test_cases:
            raise ValidationError("Failed to generate test cases")
        
        # Save to storage
        saved_test_cases = storage.create_test_cases(test_cases)
        
        log_info(f"Generated {len(saved_test_cases)} test cases", "test-cases")
        return [tc.model_dump() for tc in saved_test_cases]
    
    async def _generate_with_ai(
        self,
        brd,
        analysis: Optional[Any],
        documentation: Optional[Any]
    ) -> List[Dict[str, Any]]:
        """Generate test cases using AI service."""
        from ai import generate_test_cases
        
        return await generate_test_cases(
            brd.model_dump(),
            analysis.model_dump() if analysis else None,
            documentation.model_dump() if documentation else None
        )
```

**2. Create Router (`api/v1/test_cases.py`):**
```python
from fastapi import APIRouter
from typing import List
from services.test_case_service import TestCaseService
from utils.exceptions import bad_request, internal_error
from core.logging import log_error


router = APIRouter(prefix="/test-cases", tags=["test-cases"])


@router.get("")
async def get_test_cases():
    """Get all test cases."""
    try:
        from repositories import storage
        brd = storage.get_current_brd()
        if not brd:
            return []
        test_cases = storage.get_test_cases(brd.id)
        return [tc.model_dump() for tc in test_cases]
    except Exception as e:
        log_error("Error fetching test cases", "api", e)
        raise internal_error("Failed to fetch test cases")


@router.post("/generate")
async def generate_test_cases():
    """Generate test cases from BRD."""
    try:
        service = TestCaseService()
        return await service.generate_test_cases()
    except ValidationError as e:
        raise bad_request(str(e))
    except Exception as e:
        log_error("Error generating test cases", "api", e)
        raise internal_error("Failed to generate test cases")
```

**3. Register Router (`app.py`):**
```python
from api.v1 import test_cases

app.include_router(test_cases.router, prefix="/api")
```

## 🎯 Quick Reference

| Old Location | New Location | Purpose |
|-------------|--------------|---------|
| `main.py` endpoints | `api/v1/*.py` | HTTP routes |
| `main.py` business logic | `services/*.py` | Business logic |
| `storage.py` | `repositories/storage.py` | Data access |
| `models.py` | `schemas/*.py` | Type definitions |
| `ai.py` | `services/ai_service.py` | AI operations |
| `jira_service.py` | `services/jira_service.py` | JIRA integration |
| `mongodb_client.py` | `services/knowledge_base_service.py` | MongoDB operations |

## ✅ Migration Checklist

For each endpoint you migrate:

- [ ] Extract business logic to a service
- [ ] Create a thin router in `api/v1/`
- [ ] Use Pydantic schemas for validation
- [ ] Import from new module locations
- [ ] Use `core.config` for settings
- [ ] Use `core.logging` for logging
- [ ] Use `utils.exceptions` for errors
- [ ] Register router in `app.py`
- [ ] Test the endpoint
- [ ] Remove from old `main.py`

## 🚀 Testing Your Migration

After migrating an endpoint:

```bash
# 1. Start the new server
python server_py/app.py

# 2. Test the endpoint
curl -X POST http://localhost:5000/api/test-cases/generate

# 3. Check logs for proper logging
# Should see structured logs like:
# 10:15:30 AM [INFO] [test-cases] Generating test cases from BRD

# 4. Verify error handling
# Try with no BRD - should get proper 400 error
```

## 💡 Pro Tips

1. **Migrate incrementally**: One endpoint at a time
2. **Keep old code**: Don't delete until new code is tested
3. **Test thoroughly**: Ensure same behavior as before
4. **Use type hints**: Let Pydantic catch errors early
5. **Extract reusable logic**: Create utility functions
6. **Document as you go**: Update docstrings

## 🎓 Best Practices

1. **Routers should be thin**: Just validation and delegation
2. **Services contain business logic**: No HTTP knowledge
3. **Repositories handle data**: No business logic
4. **Use dependency injection**: Make code testable
5. **Log at service layer**: Not in routers
6. **Handle errors gracefully**: Use custom exceptions

---

Happy migrating! 🚀
