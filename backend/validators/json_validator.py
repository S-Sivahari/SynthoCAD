import json
from pathlib import Path
from typing import Union, Dict, Any
from jsonschema import validate, ValidationError


def validate_json(json_input: Union[str, Dict[str, Any]]) -> bool:
    schema_path = Path(__file__).parent.parent / "core" / "scl_schema.json"
    
    with open(schema_path, 'r') as f:
        schema = json.load(f)    
    if isinstance(json_input, str):
        try:
            json_data = json.loads(json_input)
        except json.JSONDecodeError:
            return False
    else:
        json_data = json_input
    try:
        validate(instance=json_data, schema=schema)
        return True
    except ValidationError:
        return False