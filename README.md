# SynthoCAD - AI-Powered CAD Generation Platform

**Convert natural language descriptions into parametric CAD models with automatic error recovery, cleanup, and FreeCAD integration.**

---

## 🚀 Quick Start

### Command Line
```bash
# Natural language to CAD
python backend/llm_cli.py -p "Create a cylinder 10mm radius, 20mm tall"

# Interactive mode
python backend/llm_cli.py
```

### Web Interface (Recommended)
```bash
# Start the server (serves both frontend and API)
cd backend
python api/app.py

# Open in browser
# http://localhost:5000
```

**Note:** The Flask backend automatically serves the frontend on port 5000. You don't need a separate frontend server.

### Web Interface (Development Mode - Optional)
```bash
# Only needed for frontend development with hot-reload
# Terminal 1: Backend API
cd backend
python api/app.py

# Terminal 2: Frontend dev server
cd frontend
python -m http.server 8000
# Open http://localhost:8000 in browser
# (Frontend will still call API at localhost:5000)
```

---

## ✨ Features

### 🎨 CAD Generation
- **Prompt -> SCL JSON -> CadQuery -> STEP** end-to-end pipeline
- **RAG-assisted retrieval** for template-guided generation
- **Schema repair + validation retry loop** for robust JSON generation
- **JSON-first generation path** for direct structured workflows

### 🧩 B-Rep Workflows
- **Dedicated B-Rep generation loop** (`/api/v1/generate/brep`)
- **Operation-sequence execution** via isolated worker subprocesses
- **Step-by-step operation history** with generated STEP states

### ✏️ STEP Editing & Preview
- **7-view preview pipeline** (isometric/top/bottom/front/back/left/right)
- **Feature extraction** (cylinders, planes, cones, bounding boxes)
- **Natural-language STEP edits** (`/api/v1/edit/from-step`)
- **Semantic B-Rep edit path** (`/api/v1/edit/brep`)

### 🧰 Template Toolkit & Assets
- **Catalog-driven template browser** with categories and build status
- **Template asset rebuild APIs** for STEP + thumbnail generation
- **Thumbnail fallback handling** and catalog summary endpoints

### ⚙️ Parameters, Cleanup & Reliability
- **AI/intelligent/legacy parameter extraction modes**
- **Regenerate from updated parameters** through API endpoints
- **Cleanup by age/count/model** with dry-run support
- **Retry/error telemetry** and health/status endpoints

---

## 🔄 Pipeline Overview

### Standard Prompt Pipeline
1. Prompt validation (`validators/prompt_validator.py`)
2. RAG/template context retrieval (`backend/rag/` + template index)
3. LLM JSON synthesis and schema repair/validation (`validators/json_validator.py`)
4. CadQuery code generation (`core/cadquery_generator.py`)
5. STEP generation + optional parameter extraction

### B-Rep Generation Pipeline
1. Prompt-to-operation-sequence planning (`core/brep_generator.py`)
2. Isolated per-operation execution (`core/brep_engine.py`)
3. Iterative STEP state outputs + final artifact response

### STEP Edit Pipeline
1. Upload STEP (`/api/v1/edit/preview` or `/api/v1/edit/from-step`)
2. Geometric analysis (`step_editor/step_analyzer.py`)
3. 7-view rendering (`step_editor/step_renderer.py`)
4. Edit synthesis (`step_editor/edit_pipeline.py`)
5. Regenerated STEP output + feature payload

---

## 📁 Project Structure

```
SynthoCAD/
├── frontend/                           # Web interface (served by Flask)
│   ├── index.html                      # Main UI
│   ├── README.md                       # Frontend notes
│   ├── css/
│   │   └── style.css                   # Unified UI styling
│   └── js/
│       ├── api.js                      # API client wrapper
│       └── app.js                      # Application logic
│
├── backend/                            # Backend services and pipelines
│   ├── requirements.txt                # Python dependencies
│   │
│   ├── api/                            # REST API
│   │   ├── app.py                      # Flask app
│   │   └── routes/
│   │       ├── generation_routes.py    # Prompt/JSON/B-Rep generation
│   │       ├── edit_routes.py          # STEP preview + edit endpoints
│   │       ├── parameter_routes.py     # Parameter extraction/update
│   │       ├── template_routes.py      # Catalog + assets endpoints
│   │       ├── cleanup_routes.py       # Storage management
│   │       └── viewer_routes.py        # FreeCAD integration
│   │
│   ├── core/                           # Core Logic
│   │   ├── main.py                     # Pipeline orchestrator
│   │   ├── cadquery_generator.py       # Code generation
│   │   ├── brep_generator.py           # B-Rep planning loop
│   │   ├── brep_engine.py              # Isolated B-Rep executor
│   │   ├── scl_schema.json             # Schema definition
│   │   └── config.py                   # Configuration
│   │
│   ├── step_editor/                    # STEP analysis/edit/render stack
│   │   ├── edit_pipeline.py
│   │   ├── step_analyzer.py
│   │   └── step_renderer.py
│   │
│   ├── rag/                            # Retrieval-Augmented Generation
│   │   ├── db.py
│   │   ├── ingest.py
│   │   ├── provider.py
│   │   └── query.py
│   │
│   ├── services/                       # Business Logic
│   │   ├── gemini_service.py           # LLM integration (with retry)
│   │   ├── ollama_service.py           # Local LLM provider
│   │   ├── freecad_instance_generator.py    # FreeCAD launcher
│   │   ├── template_catalog_service.py # Template catalog state
│   │   ├── template_asset_builder.py   # Build STEP + thumbnails
│   │   ├── parameter_extractor.py      # Extract params
│   │   ├── parameter_updater.py        # Update & regenerate
│   │   ├── file_cleanup_service.py     # Storage management
│   │   └── error_recovery_service.py   # Retry logic
│   │
│   ├── scripts/                        # Utilities and batch jobs
│   │   ├── build_template_assets.py
│   │   └── description_generator.py
│   │
│   ├── validators/                     # Input Validation
│   │   ├── prompt_validator.py         # Prompt checking
│   │   └── json_validator.py           # Schema validation
│   │
│   └── utils/                          # Utilities
│       ├── logger.py                   # Logging
│       └── errors.py                   # Error classes
│
├── templates/                          # Source template JSON hierarchy
├── data/                               # Runtime uploads/cache
│   └── uploads/
│
├── outputs/                            # Generated Files
│   ├── json/                           # SCL JSON
│   ├── py/                             # Python code
│   ├── step/                           # STEP files
│   ├── previews/                       # 7-view preview renders
│   ├── glb/                            # Optional GLB exports
│   └── logs/                           # Runtime logs
│
└── data_set/                           # Large CAD dataset shards
```

---

## 🛠️ Installation & Setup

### 1. Prerequisites

- **Python 3.10+**
- **Git**
- **FreeCAD** (optional, for visualization)
- **Google Gemini API Key** ([Get one here](https://aistudio.google.com/))

### 2. Clone Repository

```bash
git clone <repository-url>
cd SynthoCAD
```

### 3. Install Backend Dependencies

```bash
cd backend
pip install -r requirements.txt
```

**Key Dependencies:**
- `cadquery==2.4.0` - CAD kernel
- `flask>=2.3.0` - REST API
- `flask-cors>=4.0.0` - CORS support
- `requests>=2.28.0` - HTTP client
- `python-dotenv>=1.0.0` - Environment variables
- `jsonschema==4.20.0` - Schema validation
- `numpy<2.0` - CadQuery compatibility

### 4. Configure Environment

Create `.env` file in backend directory:

```env
# LLM Configuration
USE_OLLAMA=false
GEMINI_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash

# Optional: Custom FreeCAD path
FREECAD_PATH=C:\Program Files\FreeCAD 0.21\bin\FreeCAD.exe
```

### 5. Start Backend API

```bash
cd backend
python api/app.py
```

Backend will run on `http://localhost:5000`

### 6. Access the Application

**The Flask backend automatically serves the frontend on port 5000. Just open:**

```
http://localhost:5000
```

**Optional: Separate Frontend Server (for development only)**

```bash
cd frontend

# Option 1: Python http server
python -m http.server 8000
# Open http://localhost:8000 (still calls API at :5000)

# Option 2: Node.js serve
npx serve
# Open http://localhost:3000

# Option 3: VS Code Live Server
# Right-click index.html -> "Open with Live Server"
```

---

## 💻 Usage Examples

### Web Interface (Recommended)

1. **Open** `http://localhost:5000` in browser
2. **Workflow Mode**: Generate or edit from prompt, upload STEP, preview 7 views
3. **B-Rep Mode**: Run iterative B-Rep generation from natural language
4. **Prebuilt Templates**: Browse categories, drag/drop templates into viewer
5. **Right Rail Parameters**: Inspect features, group faces, and regenerate

### Frontend UI Tuning

- The default UI scale is controlled in [frontend/css/style.css](frontend/css/style.css) using `--ui-scale`.
- Current value is `0.9`, so normal browser zoom (100%) looks like your preferred 90% density.
- You can tweak this safely:
  - `1.0` for native size
  - `0.9` for compact workspace
  - `1.1` for larger UI
- Prebuilt Models now scroll inside their own section (`template-tree` and `template-grid`) with visible scrollbar thumbs.

### Command Line Interface

```bash
# Basic generation
python backend/llm_cli.py -p "Create a box 50mm x 30mm x 10mm"

# Without FreeCAD
python backend/llm_cli.py --no-freecad -p "cylinder 20mm diameter, 50mm tall"

# Interactive mode
python backend/llm_cli.py

# Direct JSON to STEP
python backend/scl_to_step.py outputs/json/sample.json
```

### Python API

```python
from backend.core.main import SynthoCadPipeline

# Initialize pipeline
pipeline = SynthoCadPipeline()

# Generate from natural language
result = pipeline.process_from_prompt(
    "Create a cylinder 10mm radius, 20mm tall",
    open_freecad=True
)
print(f"STEP file: {result['step_file']}")
print(f"Parameters: {result['parameters']['total_count']}")

# Generate from JSON
import json
with open('model.json') as f:
    json_data = json.load(f)
result = pipeline.process_from_json(json_data, open_freecad=True)

# Extract and update parameters
params = pipeline.extract_parameters("output_generated.py")
pipeline.update_parameters("output_generated.py", {"radius": 15.0})
pipeline.regenerate_from_updated_python("output_generated.py", "output")
```

### REST API

```bash
# Generate from prompt
curl -X POST http://localhost:5000/api/v1/generate/from-prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create a cylinder 10mm radius, 20mm tall", "open_freecad": true}'

# Generate via B-Rep operation loop
curl -X POST http://localhost:5000/api/v1/generate/brep \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create a base plate and add a central boss"}'

# Extract parameters
curl http://localhost:5000/api/v1/parameters/extract/Cylinder_10x20_generated.py

# Preview STEP in 7 views
curl -X POST http://localhost:5000/api/v1/edit/preview \
  -F "file=@part.step"

# Get storage statistics
curl http://localhost:5000/api/v1/cleanup/stats

# Run cleanup (dry run)
curl -X POST http://localhost:5000/api/v1/cleanup/cleanup \
  -H "Content-Type: application/json" \
  -d '{"max_age_days": 30, "dry_run": true}'

# Check system health
curl http://localhost:5000/api/v1/health
```

---

## 📡 API Endpoints

### Generation
```
POST   /api/v1/generate/from-prompt      # Generate from natural language
POST   /api/v1/generate/from-json        # Generate from JSON
POST   /api/v1/generate/validate-prompt  # Validate prompt
POST   /api/v1/generate/brep             # Run B-Rep generation loop
```

### Parameters
```
GET    /api/v1/parameters/extract/<file>       # Extract parameters
POST   /api/v1/parameters/update/<file>        # Update parameters
POST   /api/v1/parameters/regenerate/<file>    # Update & regenerate
GET    /api/v1/parameters/view/json/<file>     # Read generated JSON
GET    /api/v1/parameters/view/python/<file>   # Read generated Python
GET    /api/v1/parameters/view/step/<file>     # Read generated STEP text
```

### STEP Edit & Preview
```
POST   /api/v1/edit/preview              # Upload STEP + return 7-view preview
POST   /api/v1/edit/analyze              # Upload STEP + return feature analysis
POST   /api/v1/edit/from-step            # Upload STEP + edit prompt -> new STEP
POST   /api/v1/edit/brep                 # Semantic B-Rep edit path
POST   /api/v1/edit/upload               # Upload STEP for reuse
POST   /api/v1/edit/preview-by-name      # Preview existing output STEP
```

### FreeCAD Viewer
```
GET    /api/v1/viewer/check      # Check FreeCAD installation
POST   /api/v1/viewer/open       # Open STEP in FreeCAD
POST   /api/v1/viewer/reload     # Reload STEP file
```

### Cleanup & Monitoring
```
GET    /api/v1/cleanup/stats              # Storage statistics
POST   /api/v1/cleanup/cleanup            # Run cleanup
POST   /api/v1/cleanup/cleanup/by-age     # Cleanup by age
POST   /api/v1/cleanup/cleanup/by-count   # Cleanup by count
DELETE /api/v1/cleanup/<model>            # Delete specific model
GET    /api/v1/cleanup/retry-stats        # Retry statistics
```

### Templates
```
GET    /api/v1/templates/                         # List all templates
GET    /api/v1/templates/catalog                  # Full template catalog
GET    /api/v1/templates/categories               # Category tree
GET    /api/v1/templates/by-category/<path>       # Templates by category
POST   /api/v1/templates/rebuild-assets           # Rebuild STEP/thumbnail assets
GET    /api/v1/templates/asset-status             # Catalog build status
GET    /api/v1/templates/item/<path:template_id>  # Template by full ID
```

### Health
```
GET    /api/v1/health            # API health check
```

---

## ⚙️ Configuration

### Backend Config (`backend/core/config.py`)

```python
# Execution
EXECUTION_TIMEOUT = 60  # seconds

# Cleanup
CLEANUP_ENABLED = True
CLEANUP_MAX_AGE_DAYS = 30
CLEANUP_MAX_FILES_PER_TYPE = 100
CLEANUP_AUTO_RUN = False  # Set True for production

# Retry/Error Recovery
RETRY_ENABLED = True
RETRY_MAX_ATTEMPTS = 3
RETRY_INITIAL_DELAY = 1.0  # seconds
RETRY_MAX_DELAY = 60.0
RETRY_EXPONENTIAL_BASE = 2.0
```

### Frontend Config (`frontend/js/api.js`)

```javascript
const API_BASE_URL = 'http://localhost:5000/api/v1';
```

---

## 🏗️ Architecture

### Complete Pipeline

```
1. Prompt Validation          → CAD keywords, length constraints
2. LLM → JSON Generation      → Google Gemini converts to SCL JSON (with retry)
3. JSON Schema Validation     → Validates against scl_schema.json
4. CadQuery Code Generation   → JSON to executable Python
5. STEP File Export           → Subprocess execution (with retry)
6. Parameter Extraction       → Identify editable dimensions
7. FreeCAD Integration        → Auto-open in viewer
8. Error Recovery             → Automatic retry with backoff
9. Cleanup Management         → Storage optimization
```

### Technology Stack

**Backend:**
- Python 3.10+
- Flask REST API
- Google Gemini API
- CadQuery 2.4.0
- FreeCAD (optional viewer)

**Frontend:**
- Vanilla JavaScript (no frameworks)
- Modern CSS with responsive design
- REST API integration
- Real-time updates

---

## 📊 LLM Integration Details

**Model:** Google Gemini 2.5 Flash

**What it does:**
- Converts natural language → SCL JSON
- Uses schema + concrete examples for guidance
- Temperature: 0.2 (balance consistency/reasoning)
- Max tokens: 8192
- **Automatic retry** on failures with exponential backoff

**Dimension Scaling Formula:**
```
User: "10mm radius cylinder, 20mm tall"

Sketch (normalized 0-1):
  Center: [0.5, 0.5], Radius: 0.5

Scale to real dimensions:
  sketch_scale = diameter = 2 * radius = 20.0
  extrude_depth = height / sketch_scale = 20 / 20 = 1.0

Result dimensions:
  length: 20.0, width: 20.0, height: 20.0
```

**System Prompt Location:** `backend/core/main.py` (lines 27-82)

---

## 📝 Output Files

After generation, check:

```
outputs/
├── json/
│   └── Cylinder_10x20.json         # Generated SCL JSON
├── py/
│   └── Cylinder_10x20_generated.py # CadQuery Python code
├── step/
│   └── Cylinder_10x20.step         # Final STEP file
└── logs/
    ├── pipeline_YYYYMMDD.log       # Pipeline logs
    └── api_YYYYMMDD.log            # API request logs
```

---

## 🔧 Error Handling & Recovery

### Automatic Retry

The system automatically retries on:
- Connection errors
- Timeouts  
- Rate limits (429)
- Server errors (500, 502, 503, 504)
- Temporary resource issues

**Retry Behavior:**
- Attempt 1: Immediate
- Attempt 2: Wait 1.0s
- Attempt 3: Wait 2.0s
- Max attempts: 3 (configurable)

### Manual Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| Backend offline | API not running | Start with `python backend/api/app.py` |
| 404 from Gemini | Invalid model name | Check `.env` GEMINI_MODEL |
| Rate limit (429) | Quota exhausted | Wait or use new API key (auto-retry enabled) |
| JSON validation fails | Non-conforming output | Check logs, adjust prompt |
| STEP generation fails | CadQuery errors | Check generated Python code |
| FreeCAD not opening | Not installed | Install FreeCAD or set FREECAD_PATH |
| CORS errors | Different ports | Backend handles CORS automatically |

**View Logs:**
```bash
tail -f outputs/logs/pipeline_*.log
tail -f outputs/logs/api_*.log
```

**Check Health:**
```bash
curl http://localhost:5000/api/v1/health
curl http://localhost:5000/api/v1/viewer/check
```

---

## 🧪 Testing

### Test Generation
```bash
# Test CLI
python backend/llm_cli.py -p "Create a cylinder 20mm diameter, 50mm tall"

# Test API
python backend/api/app.py &
curl -X POST http://localhost:5000/api/v1/generate/from-prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Create a box 50x30x10mm"}'
```

### Test Cleanup
```bash
# Dry run (preview only)
curl -X POST http://localhost:5000/api/v1/cleanup/cleanup \
  -H "Content-Type: application/json" \
  -d '{"max_age_days": 7, "dry_run": true}'
```

### Test Error Recovery
```python
from backend.services.error_recovery_service import ErrorRecoveryService

service = ErrorRecoveryService()
stats = service.get_retry_statistics()
print(f"Success rate: {stats['success_rate']}%")
```

---

## 📚 Documentation

- **Frontend Guide**: [frontend/README.md](frontend/README.md) - Complete UI documentation
- **SCL Schema**: [backend/core/scl_schema.json](backend/core/scl_schema.json) - Schema definition
- **API Documentation**: See endpoint descriptions above
- **Templates**: [templates/](templates/) - Example models

---

## 🎯 Features in Detail

### ✅ Completed Features

1. ✅ **Natural Language Generation** - LLM-powered CAD creation
2. ✅ **JSON Schema Validation** - Robust input validation
3. ✅ **Parameter Extraction** - Automatic dimension detection
4. ✅ **Parameter Editing** - Real-time model updates
5. ✅ **FreeCAD Integration** - Automatic visualization
6. ✅ **Web Interface** - Full-featured frontend
7. ✅ **REST API** - Complete backend API
8. ✅ **Automatic Cleanup** - Storage management
9. ✅ **Error Recovery** - Retry with exponential backoff
10. ✅ **Monitoring** - Statistics and diagnostics

### 🚧 Future Enhancements

1. **RAG System** - Vector search over data_set/ for semantic template matching
2. **More Templates** - Expand templates library with mechanical parts
3. **3D Preview** - Browser-based model visualization
4. **MCP/VLM Validation** - Geometric correctness checking
5. **Export Formats** - STL, IGES, BREP, OBJ support
6. **Authentication** - User accounts and API keys
7. **Collaboration** - Real-time multi-user editing
8. **Mobile App** - iOS/Android support
9. **Docker** - Containerized deployment
10. **CI/CD** - Automated testing and deployment

---

## 🤝 Contributing

Contributions welcome! Areas for improvement:

- Template library expansion
- New CAD features
- UI/UX enhancements
- Documentation
- Test coverage
- Performance optimization

---

## 📄 License

Open source - use for learning/research.

---

## 🙏 Acknowledgments

- **CadQuery** - Python CAD kernel
- **FreeCAD** - Open-source CAD platform
- **Google Gemini** - LLM API
- **Flask** - Web framework

---

## 📞 Support & Contact

- **Issues**: Report bugs and feature requests
- **Logs**: Check `outputs/logs/` for debugging
- **Health Check**: `http://localhost:5000/api/v1/health`
- **Application**: `http://localhost:5000`

**System Status Indicators:**
- 🟢 Backend: Online
- 🟢 FreeCAD: Ready
- 🟡 Generating...
- 🔴 Error: Check logs

---

## 🚀 Quick Reference

```bash
# Start server (serves both frontend and API)
cd backend
python api/app.py

# Generate model (CLI)
python backend/llm_cli.py -p "cylinder 20mm x 50mm"

# Generate model (API)
curl -X POST http://localhost:5000/api/v1/generate/from-prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "cylinder 20mm x 50mm"}'

# View stats
curl http://localhost:5000/api/v1/cleanup/stats

# Open browser
# Windows: start http://localhost:5000
# Mac: open http://localhost:5000
# Linux: xdg-open http://localhost:5000
```

---

**Happy CAD Generation! 🔧✨**
