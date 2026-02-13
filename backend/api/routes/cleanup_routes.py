from flask import Blueprint, request, jsonify
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent.parent))

from services.file_cleanup_service import FileCleanupService
from services.error_recovery_service import ErrorRecoveryService
from utils.logger import api_logger
from core import config


bp = Blueprint('cleanup', __name__)

# Initialize cleanup service
cleanup_service = FileCleanupService(
    output_dirs={
        'json': config.JSON_OUTPUT_DIR,
        'py': config.PY_OUTPUT_DIR,
        'step': config.STEP_OUTPUT_DIR
    },
    max_age_days=config.CLEANUP_MAX_AGE_DAYS,
    max_files_per_type=config.CLEANUP_MAX_FILES_PER_TYPE,
    logger=api_logger
)

# Initialize error recovery service for statistics
error_recovery_service = ErrorRecoveryService(logger=api_logger)


@bp.route('/stats', methods=['GET'])
def get_storage_stats():
    """
    Get storage statistics for all output directories.
    
    Returns:
    {
        "by_type": {...},
        "total_files": 150,
        "total_size_mb": 45.2,
        "timestamp": "2026-02-13T..."
    }
    """
    try:
        stats = cleanup_service.get_storage_stats()
        return jsonify(stats), 200
        
    except Exception as e:
        api_logger.error(f"Failed to get storage stats: {str(e)}")
        return jsonify({
            'error': True,
            'message': f'Failed to get storage stats: {str(e)}'
        }), 500


@bp.route('/cleanup', methods=['POST'])
def cleanup_files():
    """
    Clean up old files based on age and count limits.
    
    Request Body:
    {
        "max_age_days": 30 (optional),
        "max_files_per_type": 100 (optional),
        "dry_run": false (optional)
    }
    
    Returns:
    {
        "results_by_type": {...},
        "total_deleted_files": 25,
        "total_deleted_size_mb": 12.5,
        "dry_run": false
    }
    """
    try:
        data = request.get_json() or {}
        max_age_days = data.get('max_age_days', None)
        max_files_per_type = data.get('max_files_per_type', None)
        dry_run = data.get('dry_run', False)
        
        api_logger.info(f"Starting cleanup (dry_run={dry_run})")
        
        result = cleanup_service.cleanup_all(
            max_age_days=max_age_days,
            max_files_per_type=max_files_per_type,
            dry_run=dry_run
        )
        
        if not dry_run:
            api_logger.info(
                f"Cleanup complete: {result['total_deleted_files']} files, "
                f"{result['total_deleted_size_mb']} MB"
            )
        
        return jsonify(result), 200
        
    except Exception as e:
        api_logger.error(f"Cleanup failed: {str(e)}")
        return jsonify({
            'error': True,
            'message': f'Cleanup failed: {str(e)}'
        }), 500


@bp.route('/cleanup/by-age', methods=['POST'])
def cleanup_by_age():
    """
    Clean up files older than specified age.
    
    Request Body:
    {
        "max_age_days": 30,
        "file_type": "step" (optional: json, py, step, or "all"),
        "dry_run": false (optional)
    }
    """
    try:
        data = request.get_json() or {}
        max_age_days = data.get('max_age_days')
        file_type = data.get('file_type', 'all')
        dry_run = data.get('dry_run', False)
        
        if max_age_days is None:
            return jsonify({
                'error': True,
                'message': 'max_age_days is required'
            }), 400
            
        if file_type == 'all':
            result = cleanup_service.cleanup_all(
                max_age_days=max_age_days,
                dry_run=dry_run
            )
        else:
            if file_type not in cleanup_service.output_dirs:
                return jsonify({
                    'error': True,
                    'message': f'Invalid file_type. Must be one of: {list(cleanup_service.output_dirs.keys())}'
                }), 400
                
            directory = cleanup_service.output_dirs[file_type]
            result = cleanup_service.cleanup_by_age(
                directory,
                max_age_days=max_age_days,
                dry_run=dry_run
            )
            
        return jsonify(result), 200
        
    except Exception as e:
        api_logger.error(f"Cleanup by age failed: {str(e)}")
        return jsonify({
            'error': True,
            'message': f'Cleanup by age failed: {str(e)}'
        }), 500


@bp.route('/cleanup/by-count', methods=['POST'])
def cleanup_by_count():
    """
    Clean up oldest files to keep only max_files most recent.
    
    Request Body:
    {
        "max_files": 50,
        "file_type": "step" (optional: json, py, step, or "all"),
        "dry_run": false (optional)
    }
    """
    try:
        data = request.get_json() or {}
        max_files = data.get('max_files')
        file_type = data.get('file_type', 'all')
        dry_run = data.get('dry_run', False)
        
        if max_files is None:
            return jsonify({
                'error': True,
                'message': 'max_files is required'
            }), 400
            
        if file_type == 'all':
            result = cleanup_service.cleanup_all(
                max_files_per_type=max_files,
                dry_run=dry_run
            )
        else:
            if file_type not in cleanup_service.output_dirs:
                return jsonify({
                    'error': True,
                    'message': f'Invalid file_type. Must be one of: {list(cleanup_service.output_dirs.keys())}'
                }), 400
                
            directory = cleanup_service.output_dirs[file_type]
            result = cleanup_service.cleanup_by_count(
                directory,
                max_files=max_files,
                dry_run=dry_run
            )
            
        return jsonify(result), 200
        
    except Exception as e:
        api_logger.error(f"Cleanup by count failed: {str(e)}")
        return jsonify({
            'error': True,
            'message': f'Cleanup by count failed: {str(e)}'
        }), 500


@bp.route('/cleanup/<base_name>', methods=['DELETE'])
def cleanup_model(base_name):
    """
    Delete all files (json, py, step) for a specific model.
    
    Path Parameters:
        base_name: Base name of the model (without extension)
        
    Query Parameters:
        dry_run: true/false (default: false)
        
    Example:
        DELETE /api/v1/cleanup/my_cylinder?dry_run=true
    """
    try:
        dry_run = request.args.get('dry_run', 'false').lower() == 'true'
        
        api_logger.info(f"Deleting model: {base_name} (dry_run={dry_run})")
        
        result = cleanup_service.cleanup_matching_set(
            base_name=base_name,
            dry_run=dry_run
        )
        
        if result['deleted_count'] == 0:
            return jsonify({
                'error': False,
                'message': f'No files found for model: {base_name}',
                'deleted_count': 0
            }), 404
            
        if not dry_run:
            api_logger.info(f"Deleted {result['deleted_count']} files for model: {base_name}")
            
        return jsonify(result), 200
        
    except Exception as e:
        api_logger.error(f"Failed to delete model {base_name}: {str(e)}")
        return jsonify({
            'error': True,
            'message': f'Failed to delete model: {str(e)}'
        }), 500


@bp.route('/retry-stats', methods=['GET'])
def get_retry_statistics():
    """
    Get statistics about retry operations.
    
    Query Parameters:
        operation: Filter by operation name (optional)
        limit: Limit number of history records (optional)
        
    Returns:
    {
        "statistics": {...},
        "history": [...],
        "config": {...}
    }
    """
    try:
        operation_name = request.args.get('operation', None)
        limit = request.args.get('limit', type=int, default=50)
        
        stats = error_recovery_service.get_retry_statistics(operation_name=operation_name)
        history = error_recovery_service.get_retry_history(limit=limit, operation_name=operation_name)
        
        return jsonify({
            'statistics': stats,
            'history': history,
            'config': {
                'retry_enabled': config.RETRY_ENABLED if hasattr(config, 'RETRY_ENABLED') else True,
                'max_attempts': config.RETRY_MAX_ATTEMPTS if hasattr(config, 'RETRY_MAX_ATTEMPTS') else 3,
                'initial_delay': config.RETRY_INITIAL_DELAY if hasattr(config, 'RETRY_INITIAL_DELAY') else 1.0,
                'max_delay': config.RETRY_MAX_DELAY if hasattr(config, 'RETRY_MAX_DELAY') else 60.0
            }
        }), 200
        
    except Exception as e:
        api_logger.error(f"Failed to get retry statistics: {str(e)}")
        return jsonify({
            'error': True,
            'message': f'Failed to get retry statistics: {str(e)}'
        }), 500
