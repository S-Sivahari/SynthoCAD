from flask import Flask, jsonify
from flask_cors import CORS
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).parent.parent))

from api.routes import generation_routes, parameter_routes, template_routes
from utils.logger import api_logger
from utils.errors import SynthoCadError


def create_app():
    app = Flask(__name__)
    CORS(app)
    
    app.register_blueprint(generation_routes.bp, url_prefix='/api/v1/generate')
    app.register_blueprint(parameter_routes.bp, url_prefix='/api/v1/parameters')
    app.register_blueprint(template_routes.bp, url_prefix='/api/v1/templates')
    
    @app.errorhandler(SynthoCadError)
    def handle_synthocad_error(error):
        api_logger.error(f"SynthoCad Error: {error.code.value} - {error.message}")
        return jsonify(error.to_dict()), 400
        
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': True, 'message': 'Endpoint not found'}), 404
        
    @app.errorhandler(500)
    def internal_error(error):
        api_logger.error(f"Internal server error: {str(error)}")
        return jsonify({'error': True, 'message': 'Internal server error'}), 500
        
    @app.route('/api/v1/health', methods=['GET'])
    def health_check():
        return jsonify({'status': 'healthy', 'service': 'SynthoCAD API'}), 200
        
    return app


if __name__ == '__main__':
    app = create_app()
    api_logger.info("Starting SynthoCAD API server...")
    app.run(host='0.0.0.0', port=5000, debug=True)
