# SynthoCAD Backend Structure

## Directory Organization

```
backend/
├── api/
│   ├── routes/
│   │   ├── generation_routes.py    # Prompt & JSON generation endpoints
│   │   ├── parameter_routes.py     # Parameter extraction/update endpoints
│   │   └── template_routes.py      # Template listing/loading endpoints
│   ├── middleware/                 # Future: auth, rate limiting
│   └── app.py                      # Flask app initialization
│
├── core/
│   ├── cadquery_generator.py       # JSON → CadQuery Python converter
│   ├── scl_schema.json            # SCL JSON schema
│   └── config.py                   # Configuration paths
│
├── services/
│   ├── parameter_extractor.py      # Extract parameters from Python files
│   └── parameter_updater.py        # Update Python files with new values
│
├── validators/
│   ├── json_validator.py           # Validate JSON against schema
│   └── prompt_validator.py         # Validate user prompts
│
├── utils/
│   ├── errors.py                   # Custom error classes
│   └── logger.py                   # Logging configuration
│
└── requirements.txt                # Python dependencies
```

## Workflow

1. **User Input Validation**
   - `prompt_validator.py` checks prompt quality
   - Returns errors or suggests templates if invalid

2. **JSON Generation** (LLM integration - future)
   - Converts prompt to SCL JSON
   - Validates with `json_validator.py`
   - If errors, retry with LLM

3. **Code Generation**
   - `cadquery_generator.py` converts JSON → Python
   - Saves to `outputs/py/`

4. **Execution**
   - Executes Python file
   - Generates STEP file in `outputs/step/`

5. **Parameter Management**
   - `parameter_extractor.py` extracts editable values
   - Frontend displays as markdown
   - User changes values
   - `parameter_updater.py` updates Python file
   - Re-execute to generate new STEP

6. **FreeCAD Integration**
   - `freecad_connector.py` opens/reloads STEP files
   - Macros for automation

## API Endpoints

### Generation
- `POST /api/v1/generate/validate-prompt` - Validate user prompt
- `POST /api/v1/generate/from-prompt` - Generate from prompt (LLM)
- `POST /api/v1/generate/from-json` - Generate from JSON

### Parameters
- `GET /api/v1/parameters/extract/<filename>` - Extract parameters
- `POST /api/v1/parameters/update/<filename>` - Update parameters

### Templates
- `GET /api/v1/templates/list` - List all templates
- `GET /api/v1/templates/<category>/<id>` - Get specific template

### Health
- `GET /api/v1/health` - API health check
