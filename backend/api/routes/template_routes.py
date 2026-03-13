from flask import Blueprint, request, jsonify
import sys
from pathlib import Path
import json

sys.path.append(str(Path(__file__).parent.parent.parent))

from utils.logger import api_logger
from core import config


bp = Blueprint('templates', __name__)


@bp.route('/', methods=['GET'], strict_slashes=False)
@bp.route('/list', methods=['GET'])
def list_templates():
    
    templates = []
    seen_ids = set()

    # Auto-discover every sub-folder under the templates directory
    if config.TEMPLATES_DIR.exists():
        for json_file in sorted(config.TEMPLATES_DIR.rglob("*.json")):
            file_id = json_file.stem
            # Use relative path as unique id to avoid collisions across categories
            try:
                rel = json_file.relative_to(config.TEMPLATES_DIR)
            except ValueError:
                continue
            unique_id = str(rel).replace("\\", "/")
            if unique_id in seen_ids:
                continue
            seen_ids.add(unique_id)
            category = json_file.parent.name

            try:
                with open(json_file, 'r') as f:
                    template_data = json.load(f)

                templates.append({
                    'id': unique_id,
                    'name': template_data.get('final_name', file_id),
                    'category': template_data.get('_template_category', category),
                    'description': template_data.get('_engineering_note',
                                    template_data.get('_description',
                                    template_data.get('description', ''))),
                    'file': json_file.name,
                    'editable_parameters': template_data.get('_editable_parameters', [])
                })
            except Exception as e:
                api_logger.warning(f"Failed to load template {json_file}: {e}")

    # Collect distinct category names
    categories = sorted({t['category'] for t in templates if t['category']})
                    
    return jsonify({
        'success': True,
        'templates': templates,
        'count': len(templates),
        'categories': categories
    }), 200


@bp.route('/<path:template_id>', methods=['GET'])
def get_template(template_id):
    """Fetch a single template by its relative path id (e.g. 'basic/cylinder' or
    'power_transmission/2_bolt_flange_bearing') or by bare stem name."""

    # Try as a relative path first (with or without .json extension)
    candidate = config.TEMPLATES_DIR / template_id
    if not candidate.suffix:
        candidate = candidate.with_suffix('.json')

    if not candidate.exists():
        # Fall back: search for a file whose stem matches the last path segment
        stem = Path(template_id).stem
        matches = list(config.TEMPLATES_DIR.rglob(f"{stem}.json"))
        if matches:
            candidate = matches[0]
        else:
            return jsonify({
                'error': True,
                'message': f'Template not found: {template_id}'
            }), 404
        
    try:
        with open(candidate, 'r') as f:
            template_data = json.load(f)

        try:
            rel_id = str(candidate.relative_to(config.TEMPLATES_DIR)).replace("\\", "/")
        except ValueError:
            rel_id = candidate.stem

        api_logger.info(f"Loaded template: {rel_id}")
        
        return jsonify({
            'success': True,
            'template': template_data,
            'id': rel_id,
            'category': template_data.get('_template_category', candidate.parent.name)
        }), 200
        
    except Exception as e:
        api_logger.error(f"Failed to load template {template_id}: {e}")
        return jsonify({
            'error': True,
            'message': f'Failed to load template: {str(e)}'
        }), 500
