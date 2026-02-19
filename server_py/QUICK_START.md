# 🚀 Quick Start Guide

Get up and running with the modernized backend in 5 minutes!

## 📋 Prerequisites

- Python 3.9+
- pip
- (Optional) Virtual environment

## ⚡ Quick Setup

### 1. Install Dependencies

```bash
cd server_py
pip install -r requirements.txt
```

### 2. Configure Environment

Create a `.env` file in the project root:

```env
# AI/GenAI Configuration
PWC_GENAI_ENDPOINT_URL=your_endpoint_url
PWC_GENAI_API_KEY=your_api_key
PWC_GENAI_BEARER_TOKEN=your_bearer_token

# GitHub (Optional)
GITHUB_PERSONAL_ACCESS_TOKEN=your_github_token

# JIRA Integration (Optional)
JIRA_EMAIL=your@email.com
JIRA_API_TOKEN=your_jira_token
JIRA_INSTANCE_URL=yourcompany.atlassian.net
JIRA_PROJECT_KEY=PROJ

# MongoDB (Optional)
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGODB_DB_NAME=docugen_knowledge

# Server
PORT=5000
NODE_ENV=development
```

### 3. Run the Server

```bash
# Option 1: Using the app directly
python app.py

# Option 2: Using uvicorn
uvicorn app:app --reload --host 0.0.0.0 --port 5000

# Option 3: Using the old entry point (legacy)
python main.py
```

You should see:
```
🚀 Defuse 2.O API v1.0.0
📝 Environment: development
🌐 Server: http://0.0.0.0:5000
✓ Connected to MongoDB: docugen_knowledge
```

### 4. Test the API

Open your browser to: http://localhost:5000/docs

You'll see the auto-generated Swagger UI!

## 🎯 Your First API Call

### Health Check
```bash
curl http://localhost:5000/health
```

Response:
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

### Get Projects
```bash
curl http://localhost:5000/api/projects
```

### Analyze a Repository
```bash
curl -X POST http://localhost:5000/api/projects/analyze \
  -H "Content-Type: application/json" \
  -d '{"repoUrl": "https://github.com/username/repo"}'
```

## 📁 Explore the Structure

```
server_py/
├── app.py              ← Start here! Modern entry point
├── api/                ← HTTP endpoints
│   └── v1/
│       ├── projects.py
│       └── knowledge_base.py
├── services/           ← Business logic
│   ├── ai_service.py
│   ├── jira_service.py
│   └── knowledge_base_service.py
├── repositories/       ← Data access
│   └── storage.py
├── schemas/            ← Type definitions
│   ├── requests.py
│   └── entities.py
└── core/              ← Configuration
    ├── config.py
    ├── database.py
    └── logging.py
```

## 🔍 What's Different?

| Old Way | New Way |
|---------|---------|
| `main.py` (1105 lines) | Multiple focused files |
| `os.environ.get()` everywhere | `core.config.get_settings()` |
| `print()` for logging | `core.logging` functions |
| No validation | Pydantic schemas |
| Mixed concerns | Clean separation |

## 📚 Key Files to Know

1. **app.py** - Application entry point
2. **core/config.py** - All configuration settings
3. **api/v1/** - Where endpoints live
4. **services/** - Where business logic lives
5. **repositories/storage.py** - Where data is stored

## 🛠️ Common Tasks

### Add a New Endpoint

1. Create router in `api/v1/my_resource.py`
2. Register in `app.py`:
   ```python
   from api.v1 import my_resource
   app.include_router(my_resource.router, prefix="/api")
   ```

### Add Configuration

Edit `core/config.py`:
```python
class Settings(BaseSettings):
    my_new_setting: str = "default_value"
```

Access it:
```python
from core.config import get_settings
settings = get_settings()
value = settings.my_new_setting
```

### Add a Service

Create `services/my_service.py`:
```python
class MyService:
    async def do_something(self):
        # Your logic here
        pass

my_service = MyService()
```

Use it:
```python
from services.my_service import my_service
result = await my_service.do_something()
```

## 🐛 Troubleshooting

### Port Already in Use
```bash
# Kill the process using port 5000
# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# Linux/Mac
lsof -ti:5000 | xargs kill -9
```

### MongoDB Connection Issues
- Check your `MONGODB_URI` in `.env`
- Make sure MongoDB is accessible
- The app will work without MongoDB (uses in-memory storage)

### Import Errors
```bash
# Make sure you're in the right directory
cd server_py
python app.py

# Or use the module syntax
python -m server_py.app
```

### Missing Dependencies
```bash
pip install -r requirements.txt --upgrade
```

## 📖 Learn More

- [README.md](README.md) - Complete documentation
- [ARCHITECTURE.md](ARCHITECTURE.md) - Architecture details
- [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) - Migrating old code
- [BEFORE_AFTER.md](BEFORE_AFTER.md) - See the improvements

## 🎉 You're Ready!

The server is running and you understand the basics. Now:

1. Explore the auto-generated docs: http://localhost:5000/docs
2. Check out the example routers in `api/v1/`
3. Read the architecture documentation
4. Start building! 🚀

## 💡 Pro Tips

- Use the `/docs` endpoint for interactive API testing
- Check logs for structured output
- All endpoints validate input automatically
- Configuration is type-safe via Pydantic
- Services are reusable and testable

---

**Need help?** Check the documentation files or ask questions! 😊
