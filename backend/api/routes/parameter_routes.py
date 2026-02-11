from flask import Blueprint, request, jsonify
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from services.parameter_extractor import ParameterExtractor
from services.parameter_updater import ParameterUpdater
from utils.logger import api_logger
from utils.errors import ParameterUpdateError
from core import config


bp = Blueprint('parameters', __name__)
extractor = ParameterExtractor()
updater = ParameterUpdater()


@bp.route('/extract/<filename>', methods=['GET'])
def extract_parameters(filename):
    
    py_file = config.PY_OUTPUT_DIR / filename
    
    if not py_file.exists():
        return jsonify({
            'error': True,
            'message': f'Python file not found: {filename}'
        }), 404
        
    try:
        params_data = extractor.extract_from_python(str(py_file))
        markdown = extractor.generate_markdown(params_data)
        
        api_logger.info(f"Extracted {params_data['total_count']} parameters from {filename}")
        
        return jsonify({
            'success': True,
            'file': filename,
            'parameters': params_data['parameters'],
            'markdown': markdown,
            'total_count': params_data['total_count']
        }), 200
        
    except Exception as e:
        api_logger.error(f"Parameter extraction failed: {str(e)}")
        return jsonify({
            'error': True,
            'message': f'Failed to extract parameters: {str(e)}'
        }), 500


@bp.route('/update/<filename>', methods=['POST'])
def update_parameters(filename):
    
    py_file = config.PY_OUTPUT_DIR / filename
    
    if not py_file.exists():
        return jsonify({
            'error': True,
            'message': f'Python file not found: {filename}'
        }), 404
        
    data = request.get_json()
    parameters = data.get('parameters', {})
    
    if not parameters:
        raise ParameterUpdateError("No parameters provided for update")
        
    try:
        for param_name, value in parameters.items():
            is_valid, error_msg = updater.validate_parameter_value(param_name, value)
            if not is_valid:
                raise ParameterUpdateError(f"Invalid value for {param_name}: {error_msg}")
                
        success = updater.update_python_file(str(py_file), parameters)
        
        if not success:
            raise ParameterUpdateError("Failed to update Python file")
            
        api_logger.info(f"Updated {len(parameters)} parameters in {filename}")
        
        return jsonify({
            'success': True,
            'message': f'Updated {len(parameters)} parameters',
            'file': filename,
            'updated_parameters': list(parameters.keys())
        }), 200
        
    except ParameterUpdateError as e:
        raise e
    except Exception as e:
        api_logger.error(f"Parameter update failed: {str(e)}")
        return jsonify({
            'error': True,
            'message': f'Failed to update parameters: {str(e)}'
        }), 500
