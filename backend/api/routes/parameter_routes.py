from flask import Blueprint, request, jsonify, send_file
import sys
import re
import json
from pathlib import Path
from typing import Dict, List, Any

sys.path.append(str(Path(__file__).parent.parent.parent))

from services.parameter_extractor import ParameterExtractor
from services.ai_parameter_extractor import AIParameterExtractor
from services.intelligent_parameter_extractor import IntelligentParameterExtractor
from services.parameter_updater import ParameterUpdater
from core.main import SynthoCadPipeline
from utils.logger import api_logger
from utils.errors import ParameterUpdateError
from core import config
from step_editor import step_analyzer, edit_pipeline

bp = Blueprint('parameters', __name__)
extractor = ParameterExtractor()  # Legacy regex-based
ai_extractor = AIParameterExtractor()  # AI-powered (most accurate)
intelligent_extractor = IntelligentParameterExtractor()  # Rule-based JSON parser
updater = ParameterUpdater()
pipeline = SynthoCadPipeline()  # For regeneration


@bp.route('/extract/<filename>', methods=['GET'])
def extract_parameters(filename):
    """
    Extract parameters using AI-powered extraction (most accurate)
    Query params:
    - method: 'ai' (default), 'intelligent', 'legacy'
    """
    
    method = request.args.get('method', 'ai')
    
    # Find corresponding files
    base_name = filename.replace('_generated.py', '')
    json_file = config.JSON_OUTPUT_DIR / f"{base_name}.json"
    py_file = config.PY_OUTPUT_DIR / filename
    
    if not json_file.exists():
        return jsonify({
            'error': True,
            'message': f'JSON file not found: {base_name}.json'
        }), 404
    
    try:
        # Choose extraction method
        if method == 'ai':
            # AI-powered extraction (most accurate)
            params_data = ai_extractor.extract_with_fallback(
                str(json_file), 
                str(py_file) if py_file.exists() else None
            )
            markdown = ai_extractor.generate_markdown(params_data)
        
        elif method == 'intelligent':
            # Rule-based JSON parsing
            params_data = intelligent_extractor.extract_from_json(str(json_file))
            markdown = "# Parameters\n\n" + json.dumps(params_data['parameters'], indent=2)
        
        else:
            # Legacy regex-based (fallback)
            if not py_file.exists():
                return jsonify({
                    'error': True,
                    'message': f'Python file not found: {filename}'
                }), 404
            params_data = extractor.extract_from_python(str(py_file))
            markdown = extractor.generate_markdown(params_data)
        
        api_logger.info(
            f"Extracted {params_data.get('total_count', 0)} parameters from {base_name} "
            f"using {params_data.get('extraction_method', method)} method"
        )
        
        return jsonify({
            'success': True,
            'file': filename,
            'parameters': params_data.get('parameters', []),
            'markdown': markdown,
            'total_count': params_data.get('total_count', 0),
            'shape_type': params_data.get('shape_type', 'Unknown'),
            'design_intent': params_data.get('design_intent', ''),
            'extraction_method': params_data.get('extraction_method', method),
            'units': params_data.get('units', 'mm')
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


@bp.route('/regenerate/<filename>', methods=['POST'])
def regenerate_step(filename):
    """
    Regenerate STEP file after parameter updates.
    
    Request Body:
    {
        "parameters": {"radius": 15.0, "height": 30.0}
    }
    """
    py_file = config.PY_OUTPUT_DIR / filename
    
    if not py_file.exists():
        return jsonify({
            'error': True,
            'message': f'Python file not found: {filename}'
        }), 404
        
    data = request.get_json()
    parameters = data.get('parameters', {})
    
    if not parameters:
        return jsonify({
            'error': True,
            'message': 'No parameters provided for update'
        }), 400
        
    try:
        # Validate and update parameters
        for param_name, value in parameters.items():
            is_valid, error_msg = updater.validate_parameter_value(param_name, value)
            if not is_valid:
                raise ParameterUpdateError(f"Invalid value for {param_name}: {error_msg}")
                
        updater.update_python_file(str(py_file), parameters)
        
        # Extract output name from filename (remove _generated.py suffix)
        output_name = filename.replace('_generated.py', '').replace('.py', '')
        
        # Regenerate STEP file
        api_logger.info(f"Regenerating {output_name} with updated parameters")
        step_file = pipeline.regenerate_from_updated_python(
            str(py_file), 
            output_name
        )
        
        api_logger.info(f"Successfully regenerated: {step_file}")

        # Check for GLB
        glb_file = config.GLB_OUTPUT_DIR / f"{output_name}.glb"
        
        return jsonify({
            'success': True,
            'status': 'success',
            'message': f'Regenerated with {len(parameters)} updated parameters',
            'py_file': str(py_file),
            'step_file': step_file,
            'glb_url': f'/outputs/glb/{output_name}.glb' if glb_file.exists() else None,
            'updated_parameters': list(parameters.keys())
        }), 200
        
    except ParameterUpdateError as e:
        api_logger.error(f"Parameter update error: {e.message}")
        return jsonify({
            'error': True,
            'message': e.message
        }), 400
    except Exception as e:
        api_logger.error(f"Regeneration failed: {str(e)}")
        return jsonify({
            'error': True,
            'message': f'Failed to regenerate: {str(e)}'
        }), 500


@bp.route('/view/json/<filename>', methods=['GET'])
def view_json_file(filename):
    """View JSON file contents"""
    
    base_name = filename.replace('.json', '')
    json_file = config.JSON_OUTPUT_DIR / f"{base_name}.json"
    
    if not json_file.exists():
        return jsonify({
            'error': True,
            'message': f'JSON file not found: {filename}'
        }), 404
    
    try:
        with open(json_file, 'r') as f:
            json_data = json.load(f)
        
        return jsonify({
            'success': True,
            'filename': filename,
            'content': json_data,
            'content_str': json.dumps(json_data, indent=2),
            'file_path': str(json_file)
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': True,
            'message': f'Failed to read JSON file: {str(e)}'
        }), 500


@bp.route('/view/python/<filename>', methods=['GET'])
def view_python_file(filename):
    """View generated Python file contents"""
    
    py_file = config.PY_OUTPUT_DIR / filename
    
    if not py_file.exists():
        return jsonify({
            'error': True,
            'message': f'Python file not found: {filename}'
        }), 404
    
    try:
        with open(py_file, 'r') as f:
            code = f.read()
        
        return jsonify({
            'success': True,
            'filename': filename,
            'content': code,
            'file_path': str(py_file),
            'language': 'python'
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': True,
            'message': f'Failed to read Python file: {str(e)}'
        }), 500


@bp.route('/view/step/<filename>', methods=['GET'])
def view_step_file(filename):
    """View or download STEP file"""
    
    base_name = filename.replace('.step', '')
    step_file = config.STEP_OUTPUT_DIR / f"{base_name}.step"
    
    if not step_file.exists():
        return jsonify({
            'error': True,
            'message': f'STEP file not found: {filename}'
        }), 404
    
    # Check if user wants to download or just view metadata
    download = request.args.get('download', 'false').lower() == 'true'
    
    if download:
        return send_file(
            step_file,
            as_attachment=True,
            download_name=filename,
            mimetype='application/step'
        )
    
    try:
        # Read file info
        file_size = step_file.stat().st_size
        
        with open(step_file, 'r') as f:
            content = f.read()
        
        # Extract basic STEP metadata
        lines = content.split('\n')
        header_lines = [l for l in lines if l.startswith('FILE_')]
        
        return jsonify({
            'success': True,
            'filename': filename,
            'file_path': str(step_file),
            'file_size_bytes': file_size,
            'file_size_kb': round(file_size / 1024, 2),
            'content_preview': content[:500] + '...' if len(content) > 500 else content,
            'header': header_lines,
            'download_url': f'/api/v1/parameters/view/step/{filename}?download=true'
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': True,
            'message': f'Failed to read STEP file: {str(e)}'
        }), 500


@bp.route('/list-files', methods=['GET'])
def list_generated_files():
    """List all generated files (JSON, Python, STEP)"""
    
    try:
        json_files = [f.name for f in config.JSON_OUTPUT_DIR.glob('*.json')]
        py_files = [f.name for f in config.PY_OUTPUT_DIR.glob('*.py')]
        step_files = [f.name for f in config.STEP_OUTPUT_DIR.glob('*.step')]
        
        # Group by base name
        all_bases = set()
        for jf in json_files:
            all_bases.add(jf.replace('.json', ''))
        
        files_grouped = []
        for base in sorted(all_bases):
            json_exists = f"{base}.json" in json_files
            py_exists = f"{base}_generated.py" in py_files
            step_exists = f"{base}.step" in step_files
            
            files_grouped.append({
                'base_name': base,
                'json_file': f"{base}.json" if json_exists else None,
                'py_file': f"{base}_generated.py" if py_exists else None,
                'step_file': f"{base}.step" if step_exists else None,
                'complete': json_exists and py_exists and step_exists
            })
        
        return jsonify({
            'success': True,
            'files': files_grouped,
            'total': len(files_grouped),
            'json_count': len(json_files),
            'py_count': len(py_files),
            'step_count': len(step_files)
        }), 200
        
    except Exception as e:
        return jsonify({
            'error': True,
            'message': f'Failed to list files: {str(e)}'
        }), 500
@bp.route('/ocp/<filename>', methods=['GET'])
def extract_ocp_parameters(filename):
    """
    Extract exact geometric parameters using OCP/CadQuery.
    """
    base_name = filename.replace('_generated.py', '').replace('.py', '').replace('.step', '')
    step_file = config.STEP_OUTPUT_DIR / f"{base_name}.step"
    
    if not step_file.exists():
        # Try to find it in the uploads dir if not in outputs
        step_file = config.DATA_DIR / 'uploads' / f"{base_name}.step"
        if not step_file.exists():
            return jsonify({
                'error': True,
                'message': f'STEP file not found for {base_name}'
            }), 404
            
    try:
        features = step_analyzer.analyze(str(step_file))
        return jsonify({
            'success': True,
            'filename': step_file.name,
            'features': features
        }), 200
    except Exception as e:
        api_logger.error(f"OCP extraction failed: {str(e)}")
        return jsonify({
            'error': True,
            'message': f'Failed to extract OCP parameters: {str(e)}'
        }), 500


@bp.route('/regenerate-ocp/<filename>', methods=['POST'])
def regenerate_ocp(filename):
    """
    Regenerate model based on OCP face edits using intermediate design representation.
    
    Flow: OCP Features → Intermediate Design → LLM → SCL JSON → STEP
    
    Request body: { 
        "updates": [{id: "f0", type: "cylinder", radius: 15, location: [X,Y,Z]}, ...], 
        "original_features": {...} 
    }
    """
    base_name = filename.replace('_generated.py', '').replace('.py', '').replace('.step', '')
    step_file = config.STEP_OUTPUT_DIR / f"{base_name}.step"
    
    if not step_file.exists():
        step_file = config.DATA_DIR / 'uploads' / f"{base_name}.step"
        if not step_file.exists():
            return jsonify({'error': True, 'message': 'Original STEP file not found'}), 404

    data = request.get_json()
    updates = data.get('updates', [])
    original_features = data.get('original_features', {})
    
    if not updates:
        return jsonify({'error': True, 'message': 'No updates provided'}), 400

    try:
        # Step 1: Apply updates to original features
        api_logger.info(f"[Regen-OCP] Applying {len(updates)} updates to geometry...")
        updated_features = _apply_updates_to_features(original_features, updates)
        
        # Step 2: Convert updated features to intermediate design representation
        from step_editor.geometric_interpreter import GeometricInterpreter, create_intermediate_prompt
        
        interpreter = GeometricInterpreter()
        intermediate_design = interpreter.interpret(updated_features)
        
        api_logger.info(f"[Regen-OCP] Interpreted as: {intermediate_design.get('design_type')}")
        api_logger.info(f"[Regen-OCP] Design description:\n{interpreter.to_description(intermediate_design)}")
        
        # Step 3: Build LLM prompt using intermediate representation
        system_prompt = create_intermediate_prompt()
        
        intermediate_json_str = json.dumps(intermediate_design, indent=2)
        user_request = f"""{intermediate_json_str}

Additional Context:
- Original model: {base_name}
- User modifications: {len(updates)} geometric changes applied
- Target: Generate parametric SCL JSON that matches this design exactly

Remember:
- Use sketch_scale that matches real dimensions
- Position features accurately using moveTo
- Maintain proper operation types (NewBody, Cut, Join)
- Output ONLY valid SCL JSON"""

        full_llm_prompt = f"{system_prompt}\n\n{user_request}"
        
        # Step 4: Call LLM to generate SCL JSON
        from services.gemini_service import call_gemini
        from services.ollama_service import call_ollama
        
        api_logger.info(f"[Regen-OCP] Calling LLM with intermediate design (prompt: {len(full_llm_prompt)} chars)")
        
        if config.LLM_PROVIDER == "ollama":
            raw_response = call_ollama(full_llm_prompt, max_tokens=4096, temperature=0.1)
        else:
            raw_response = call_gemini(full_llm_prompt, max_tokens=8192, temperature=0.1)

        # Step 5: Parse and validate JSON response
        api_logger.info(f"[Regen-OCP] Parsing LLM response ({len(raw_response)} chars)...")
        
        raw_response = raw_response.strip()
        
        # Remove markdown code blocks if present
        if raw_response.startswith("```"):
            lines = raw_response.split("\n")
            lines = lines[1:]
            for i, line in enumerate(lines):
                if line.strip().startswith("```"):
                    lines = lines[:i]
                    break
            raw_response = "\n".join(lines).strip()
        
        # Extract JSON using regex as fallback
        if not raw_response.startswith("{"):
            match = re.search(r"\{[\s\S]*\}", raw_response)
            if match:
                raw_response = match.group()
            else:
                raise ValueError("No valid JSON object found in LLM response")
        
        # Parse the JSON
        try:
            scl_json = json.loads(raw_response)
        except json.JSONDecodeError as e:
            api_logger.error(f"[Regen-OCP] JSON parsing failed: {e}")
            api_logger.error(f"[Regen-OCP] Response preview: {raw_response[:500]}...")
            raise ValueError(f"LLM returned invalid JSON: {str(e)}")
        
        # Validate structure
        if not isinstance(scl_json, dict):
            raise ValueError("LLM response is not a JSON object")
        
        if "parts" not in scl_json:
            raise ValueError("LLM response missing 'parts' key")
        
        if "part_1" not in scl_json.get("parts", {}):
            raise ValueError("LLM response missing 'part_1' in parts")
        
        # Set defaults if missing
        if "units" not in scl_json:
            scl_json["units"] = "mm"
            api_logger.info("[Regen-OCP] Added default units: mm")
        
        if "final_name" not in scl_json:
            scl_json["final_name"] = f"{base_name}_edited"
            api_logger.info(f"[Regen-OCP] Added default final_name: {scl_json['final_name']}")
        
        # Step 6: Generate new STEP from SCL JSON
        api_logger.info("[Regen-OCP] Generating STEP file from SCL JSON...")
        pipeline = SynthoCadPipeline()
        result = pipeline.process_from_json(scl_json)
        
        result['base_name'] = base_name
        result['intermediate_design'] = intermediate_design  # Include for debugging
        
        api_logger.info(f"[Regen-OCP] SUCCESS: {result.get('step_file', 'unknown')}")
        
        return jsonify(result), 200

    except ValueError as e:
        api_logger.error(f"[Regen-OCP] Validation error: {str(e)}")
        return jsonify({'error': True, 'message': f"Invalid response from LLM: {str(e)}"}), 400
    except json.JSONDecodeError as e:
        api_logger.error(f"[Regen-OCP] JSON decode error: {str(e)}")
        return jsonify({'error': True, 'message': f"Failed to parse LLM response: {str(e)}"}), 500
    except Exception as e:
        api_logger.error(f"[Regen-OCP] Regeneration failed: {str(e)}", exc_info=True)
        return jsonify({'error': True, 'message': f"Model regeneration failed: {str(e)}"}), 500


def _apply_updates_to_features(original_features: Dict, updates: List[Dict]) -> Dict:
    """
    Apply user modifications to the original OCP features.
    
    This creates a modified feature set that reflects the user's requested changes.
    """
    import copy
    updated = copy.deepcopy(original_features)
    
    for update in updates:
        face_id = update.get('id')
        face_type = update.get('type')
        
        # Find and update the corresponding feature
        if face_type == 'cylinder':
            for cyl in updated.get('cylinders', []):
                if cyl.get('id') == face_id:
                    if 'radius_mm' in update:
                        cyl['radius_mm'] = update['radius_mm']
                    if 'location' in update:
                        cyl['location'] = update['location']
                    break
        
        elif face_type == 'plane':
            for plane in updated.get('planes', []):
                if plane.get('id') == face_id:
                    if 'dims' in update:
                        plane['dims'] = update['dims']
                    if 'location' in update:
                        plane['location'] = update['location']
                    break
    
    return updated


# ── Panel History API ─────────────────────────────────────────────────────────

PANEL_HISTORY_FILE = Path(__file__).parent.parent.parent / 'data' / 'panel_history.json'
_VALID_PANELS = {'viewer3d', 'preview', 'json', 'python', 'step', 'parameters'}


def _load_panel_history() -> Dict:
    """Load the panel history JSON from disk, returning an empty dict on error."""
    if PANEL_HISTORY_FILE.exists():
        try:
            with open(PANEL_HISTORY_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {p: [] for p in _VALID_PANELS}


def _save_panel_history(data: Dict) -> None:
    """Persist the panel history dict to disk."""
    PANEL_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PANEL_HISTORY_FILE, 'w') as f:
        json.dump(data, f, indent=2)


@bp.route('/history/<panel_id>', methods=['GET'])
def get_panel_history(panel_id):
    """Return the history entries for a specific panel."""
    history = _load_panel_history()
    entries = history.get(panel_id, [])
    return jsonify({'success': True, 'panel_id': panel_id, 'entries': entries}), 200


@bp.route('/history/<panel_id>', methods=['POST'])
def add_panel_history_entry(panel_id):
    """Append a new entry to a panel's history."""
    from datetime import datetime, timezone
    data = request.get_json(silent=True) or {}
    entry = {
        'name': data.get('name', 'unnamed'),
        'source': data.get('source', 'unknown'),
        'url': data.get('url') or None,
        'timestamp': datetime.now(timezone.utc).isoformat(),
    }
    history = _load_panel_history()
    if panel_id not in history:
        history[panel_id] = []
    history[panel_id].insert(0, entry)   # newest first
    _save_panel_history(history)
    return jsonify({'success': True, 'entry': entry}), 200


@bp.route('/history/<panel_id>', methods=['DELETE'])
def clear_panel_history(panel_id):
    """Clear all history entries for a specific panel."""
    history = _load_panel_history()
    history[panel_id] = []
    _save_panel_history(history)
    return jsonify({'success': True, 'panel_id': panel_id}), 200
