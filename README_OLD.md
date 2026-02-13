# SynthoCAD - Natural Language to Parametric CAD Pipeline

**Convert natural language descriptions into STEP files via LLM-powered JSON generation.**

## Quick Start

```bash
python backend/llm_cli.py -p "Create a cylinder 10mm radius, 20mm tall"
```

Or interactive mode:
```bash
python backend/llm_cli.py
```

## Architecture

### 7-Step Pipeline

```
1. Prompt Validation          → Checks CAD keywords, length constraints
2. LLM → JSON Generation      → Google Gemini (gemini-2.5-flash) converts to SCL JSON
3. JSON Schema Validation     → Validates against backend/core/scl_schema.json
4. CadQuery Code Generation   → Converts JSON to Python executable
5. STEP File Export           → Subprocess runs Python, outputs .step file
6. Parameter Extraction       → Identifies editable dimensions
7. FreeCAD Integration        → Opens result (optional with --no-freecad)
```

### Directory Structure

```
backend/
├── llm_cli.py                          # Main CLI entry point
├── scl_to_step.py                      # Direct JSON→STEP converter
├── core/
│   ├── main.py                         # SynthoCadPipeline class (orchestrator)
│   ├── scl_schema.json                 # SCL schema (source of truth)
│   └── config.py                       # Path definitions
├── services/
│   ├── gemini_service.py               # Gemini REST API client
│   ├── freecad_instance_generator.py   # FreeCAD launcher
│   ├── parameter_extractor.py          # Extract editable dimensions
│   └── parameter_updater.py            # Update parameters and regenerate
├── validators/
│   ├── prompt_validator.py             # Step 1: Validate user prompt
│   └── json_validator.py               # Step 3: Validate JSON vs schema
├── api/
│   └── app.py                          # Flask REST API (future frontend integration)
└── utils/
    ├── logger.py                       # Logging setup
    └── errors.py                       # Custom error classes

templates/basic/
├── cylinder_10x20.json                 # Concrete dimension example
└── box_50x30x10.json                   # Real-world template

outputs/
├── json/                               # Generated SCL JSON files
├── py/                                 # Generated CadQuery Python code
├── step/                               # Output .step files
└── logs/                               # Pipeline logs
```

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

### 6. Start Frontend

```bash
cd frontend

# Option 1: Python http server
python -m http.server 8000
# Open http://localhost:8000

# Option 2: Node.js serve
npx serve
# Open http://localhost:3000

# Option 3: VS Code Live Server
# Right-click index.html -> "Open with Live Server"
```

---

## 📡 API Endpoints

### Generation
```
POST   /api/v1/generate/from-prompt      # Generate from natural language
POST   /api/v1/generate/from-json        # Generate from JSON
POST   /api/v1/generate/validate-prompt  # Validate prompt
```

### Parameters
```
GET    /api/v1/parameters/extract/<file>       # Extract parameters
POST   /api/v1/parameters/update/<file>        # Update parameters
POST   /api/v1/parameters/regenerate/<file>    # Update & regenerate
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
GET    /api/v1/templates         # List all templates
GET    /api/v1/templates/<name>  # Get specific template
```

### Health
```
GET    /api/v1/health            # API health check
```

---

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
with open('model.json') as f:
    json_data = json.load(f)
result = pipeline.process_from_json(json_data, open_freecad=True)
📝 Output Files

After generation, check:

```
outputs/
├── json/
│   └── Cylinder_10x20.json         # Generated SCL JSON
├── py/
│   └── Cylinder_10x20_generated.py # CadQuery Python code
├── step/
│   └── Cylinder_10x20.step         # Final STEP file
└─Backend offline | API not running | Start with `python backend/api/app.py` |
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

- **Frontend Guide**: [`frontend/README.md`](frontend/README.md)
- **Cleanup & Recovery**: [`backend/CLEANUP_AND_RECOVERY.md`](backend/CLEANUP_AND_RECOVERY.md)
- **API Documentation**: See endpoint descriptions above
- **SCL Schema**: [`backend/core/scl_schema.json`](backend/core/scl_schema.json)

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
- **Frontend**: `http://localhost:8000`

**System Status Indicators:**
- 🟢 Backend: Online
- 🟢 FreeCAD: Ready
- 🟡 Generating...
- 🔴 Error: Check logs

---

## 🚀 Quick Reference

```bash
# Start everything
python backend/api/app.py &
cd frontend && python -m http.server 8000

# Generate model
curl -X POST http://localhost:5000/api/v1/generate/from-prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": "cylinder 20mm x 50mm"}'

# View stats
curl http://localhost:5000/api/v1/cleanup/stats

# Open browser
open http://localhost:8000
```

**Happy CAD Generation! 🔧✨**
# Get storage statistics
curl http://localhost:5000/api/v1/cleanup/stats

# Run cleanup (dry run)
curl -X POST http://localhost:5000/api/v1/cleanup/cleanup \
  -H "Content-Type: application/json" \
  -d '{"max_age_days": 30, "dry_run": true}'
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

---
```

## Output Files

After running, check:
- **JSON:** `outputs/json/Cylinder_10x20.json`
- **Python:** `outputs/py/Cylinder_10x20_generated.py`
- **STEP:** `outputs/step/Cylinder_10x20.step`
- **Logs:** `outputs/logs/pipeline.log`

## Error Handling

| Error | Cause | Fix |
|-------|-------|-----|
| 404 from Gemini | Invalid model name | Check .env GEMINI_MODEL |
| Rate limit (429) | Quota exhausted | Wait 60s or use new API key |
| JSON validation fails | Non-conforming LLM output | Check logs, adjust prompt |
| STEP generation fails | CadQuery errors | Check generated Python code |

## Future Improvements

1. **RAG System** - Vector search over data_set/ for semantic template matching
2. **More Templates** - Expand templates/basic/ with mechanical parts
3. **React Frontend** - 3D viewer + parameter editing UI
4. **MCP/VLM Validation** - Geometric correctness checking
5. **Design Persistence** - Save/load design history

## Requirements

- Python 3.10+
- `cadquery==2.4.0`
- `requests>=2.28.0`
- `python-dotenv>=1.0.0`
- `jsonschema==4.20.0`
- `numpy<2.0` (CadQuery compatibility)
- Google Gemini API key

Install:
```bash
pip install -r backend/requirements.txt
```

## License

Open source - use for learning/research.
