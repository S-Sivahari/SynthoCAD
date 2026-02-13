from flask import Blueprint, request, jsonify
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from validators.prompt_validator import PromptValidator
from core.main import SynthoCadPipeline
from utils.logger import api_logger
from utils.errors import PromptValidationError, JSONValidationError, CodeGenerationError, SynthoCadError


bp = Blueprint('generation', __name__)
prompt_validator = PromptValidator()
pipeline = SynthoCadPipeline()  # Initialize pipeline once


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
    """
    Generate CAD model from natural language prompt.
    
    Request Body:
    {
        "prompt": "Create a cylinder with 20mm diameter and 50mm height",
        "open_freecad": true  (optional, default: true)
    }
    
    Returns:
    {
        "status": "success",
        "json_file": "/path/to/output.json",
        "py_file": "/path/to/output_generated.py",
        "step_file": "/path/to/output.step",
        "parameters": {...},
        "freecad_opened": true
    }
    """
    try:
        data = request.get_json()
        prompt = data.get('prompt', '')
        open_freecad = data.get('open_freecad', True)
        
        if not prompt:
            return jsonify({
                'status': 'error',
                'error': 'Prompt is required'
            }), 400
            
        api_logger.info(f"Starting generation from prompt: {prompt[:100]}...")
        
        # Process through the full pipeline
        result = pipeline.process_from_prompt(prompt, open_freecad=open_freecad)
        
        if result['status'] == 'success':
            api_logger.info(f"Successfully generated: {result['step_file']}")
            return jsonify(result), 200
        else:
            api_logger.error(f"Generation failed: {result.get('error', {})}")
            return jsonify(result), 400
            
    except SynthoCadError as e:
        api_logger.error(f"SynthoCad Error: {e.message}")
        return jsonify({
            'status': 'error',
            'error': e.to_dict()
        }), 400
    except Exception as e:
        api_logger.error(f"Unexpected error: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': {
                'code': 'UNKNOWN_ERROR',
                'message': str(e)
            }
        }), 500


@bp.route('/from-json', methods=['POST'])
def generate_from_json():
    """
    Generate CAD model from SCL JSON.
    
    Request Body:
    {
        "json": {...SCL JSON...},
        "output_name": "my_part" (optional),
        "open_freecad": true (optional, default: true)
    }
    
    Returns:
    {
        "status": "success",
        "json_file": "/path/to/output.json",
        "py_file": "/path/to/output_generated.py",
        "step_file": "/path/to/output.step",
        "parameters": {...},
        "freecad_opened": true
    }
    """
    try:
        data = request.get_json()
        scl_json = data.get('json', {})
        output_name = data.get('output_name', None)
        open_freecad = data.get('open_freecad', True)
        
        if not scl_json:
            return jsonify({
                'status': 'error',
                'error': 'JSON data is required'
            }), 400
            
        api_logger.info(f"Starting generation from JSON. Output: {output_name or 'auto'}")
        
        # Process through the pipeline
        result = pipeline.process_from_json(scl_json, output_name=output_name, open_freecad=open_freecad)
        
        if result['status'] == 'success':
            api_logger.info(f"Successfully generated: {result['step_file']}")
            return jsonify(result), 200
        else:
            api_logger.error(f"Generation failed: {result.get('error', {})}")
            return jsonify(result), 400
            
    except SynthoCadError as e:
        api_logger.error(f"SynthoCad Error: {e.message}")
        return jsonify({
            'status': 'error',
            'error': e.to_dict()
        }), 400
    except Exception as e:
        api_logger.error(f"Unexpected error: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': {
                'code': 'UNKNOWN_ERROR',
                'message': str(e)
            }
        }), 500
