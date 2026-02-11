from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent
BACKEND_DIR = BASE_DIR / "backend"
OUTPUT_DIR = BASE_DIR / "outputs"
TEMPLATES_DIR = BASE_DIR / "templates"
FREECAD_DIR = BASE_DIR / "freecad"

PY_OUTPUT_DIR = OUTPUT_DIR / "py"
STEP_OUTPUT_DIR = OUTPUT_DIR / "step"
JSON_OUTPUT_DIR = OUTPUT_DIR / "json"
LOGS_DIR = OUTPUT_DIR / "logs"

SCHEMA_PATH = BACKEND_DIR / "core" / "scl_schema.json"

for dir_path in [PY_OUTPUT_DIR, STEP_OUTPUT_DIR, JSON_OUTPUT_DIR, LOGS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

PROMPT_MIN_LENGTH = 10
PROMPT_MAX_LENGTH = 5000

EXECUTION_TIMEOUT = 60

SUPPORTED_TEMPLATES = ["cylinder", "box", "tube", "l_bracket", "flange", "shaft"]
