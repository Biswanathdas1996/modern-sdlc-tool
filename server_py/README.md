# Modern Backend Structure

This backend follows a clean, modern architecture with clear separation of concerns.

## 📁 Folder Structure

```
server_py/
├── api/                    # API layer - HTTP endpoints
│   └── v1/                # API version 1
│       ├── projects.py    # Projects endpoints
│       ├── knowledge_base.py
│       ├── brd.py
│       ├── test_cases.py
│       └── ...
├── core/                  # Core configuration
│   ├── config.py         # Settings management
│   ├── database.py       # Database connections
│   └── logging.py        # Logging setup
├── services/             # Business logic layer
│   ├── ai_service.py     # AI/GenAI operations
│   ├── jira_service.py   # JIRA integration
│   └── knowledge_base_service.py
├── repositories/         # Data access layer
│   ├── base.py          # Base repository
│   ├── project_repository.py
│   └── storage.py       # Storage manager
├── schemas/             # Pydantic models
│   ├── requests.py      # API request schemas
│   └── entities.py      # Domain entities
├── middleware/          # Custom middleware
│   └── logging.py       # Request logging
├── utils/              # Utilities
│   ├── exceptions.py   # Custom exceptions
│   ├── response.py     # Response helpers
│   └── text.py        # Text processing
├── app.py             # Modern FastAPI application
├── main.py           # Legacy entry point (deprecated)
└── requirements.txt  # Python dependencies
```

## 🏗️ Architecture Principles

### 1. **Layered Architecture**
- **API Layer**: FastAPI routers handling HTTP requests
- **Service Layer**: Business logic and external integrations
- **Repository Layer**: Data access and persistence
- **Schema Layer**: Request/response validation

### 2. **Dependency Injection**
- Configuration via `core.config.get_settings()`
- Database via `core.database.get_db()`
- Services via factory functions

### 3. **Separation of Concerns**
- **Routers**: Only handle HTTP, delegate to services
- **Services**: Contain business logic, no HTTP knowledge
- **Repositories**: Manage data, no business logic
- **Schemas**: Define data structure, validation

### 4. **Error Handling**
- Custom exceptions in `utils/exceptions.py`
- Consistent error responses
- Proper HTTP status codes

### 5. **Configuration Management**
- Environment-based settings
- Type-safe configuration via Pydantic
- Centralized in `core/config.py`

## 🚀 Running the Application

### Using the new entry point:
```bash
python server_py/app.py
```

### Using uvicorn directly:
```bash
uvicorn server_py.app:app --reload --host 0.0.0.0 --port 5000
```

## 🔧 Adding New Features

### 1. Create Schema (schemas/)
```python
# schemas/requests.py
class MyRequest(BaseModel):
    field: str
```

### 2. Create Service (services/)
```python
# services/my_service.py
class MyService:
    async def do_something(self, data):
        # Business logic here
        pass
```

### 3. Create Router (api/v1/)
```python
# api/v1/my_router.py
router = APIRouter(prefix="/my-resource", tags=["my-resource"])

@router.post("")
async def create_resource(request: MyRequest):
    service = MyService()
    return await service.do_something(request)
```

### 4. Register Router (app.py)
```python
from api.v1 import my_router
app.include_router(my_router.router, prefix="/api")
```

## 📝 Best Practices

1. **Use dependency injection** for services and database
2. **Keep routers thin** - delegate to services
3. **Type everything** - use Pydantic models
4. **Log appropriately** - use core.logging functions
5. **Handle errors gracefully** - use utils.exceptions
6. **Write async code** - use async/await everywhere
7. **Version your APIs** - use /api/v1/, /api/v2/
8. **Document endpoints** - use FastAPI docstrings

## 🔄 Migration from Legacy Code

The old `main.py` is deprecated. New code should:
- ✅ Use `app.py` as the entry point
- ✅ Import from `schemas/` instead of `models.py`
- ✅ Use services from `services/` instead of direct imports
- ✅ Use repositories from `repositories/` instead of `storage.py`
- ✅ Import config from `core.config` instead of `os.environ`

## 📊 Benefits of This Structure

1. **Scalability**: Easy to add new features without touching existing code
2. **Testability**: Each layer can be tested independently
3. **Maintainability**: Clear structure makes code easy to navigate
4. **Type Safety**: Pydantic ensures runtime type checking
5. **Documentation**: FastAPI auto-generates OpenAPI docs
6. **Performance**: Async/await for concurrent operations
