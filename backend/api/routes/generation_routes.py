from flask import Blueprint, request, jsonify
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from validators.prompt_validator import PromptValidator
from utils.logger import api_logger
from utils.errors import PromptValidationError, JSONValidationError, CodeGenerationError


bp = Blueprint('generation', __name__)
prompt_validator = PromptValidator()


@bp.route('/validate-prompt', methods=['POST'])
def validate_prompt():
    
    data = request.get_json()
    prompt = data.get('prompt', '')
    
    is_valid, error_message, metadata = prompt_validator.validate(prompt)
    
    if not is_valid:
        suggestions = prompt_validator.suggest_templates(prompt)
        return jsonify({
            'valid': False,
            'error': error_message or 'Validation failed',
            'suggestions': suggestions,
            'metadata': metadata or {}
        }), 400
        
    api_logger.info(f"Prompt validated successfully. Keywords: {(metadata or {}).get('cad_keywords_found', [])}")
    
    return jsonify({
        'valid': True,
        'message': 'Prompt is valid',
        'metadata': metadata or {}
    }), 200


@bp.route('/from-prompt', methods=['POST'])
def generate_from_prompt():
    
    data = request.get_json()
    prompt = data.get('prompt', '')
    
    is_valid, error_message, metadata = prompt_validator.validate(prompt)
    
    if not is_valid:
        raise PromptValidationError(error_message, {'suggestions': prompt_validator.suggest_templates(prompt)})
        
    api_logger.info(f"Starting generation from prompt: {prompt[:50]}...")
    
    return jsonify({
        'status': 'processing',
        'message': 'LLM processing will be implemented here',
        'prompt': prompt
    }), 202


@bp.route('/from-json', methods=['POST'])
def generate_from_json():
    
    data = request.get_json()
    scl_json = data.get('json', {})
    
    if not scl_json:
        raise JSONValidationError("JSON data is required")
        
    api_logger.info("Starting generation from JSON...")
    
    return jsonify({
        'status': 'processing',
        'message': 'JSON processing pipeline will be implemented here'
    }), 202
