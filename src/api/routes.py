"""
PRISM Analytics - ISRC Metadata Analyzer
Flask API routes
"""
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import logging

def create_app():
    """Create and configure the Flask application"""
    app = Flask(__name__, 
                template_folder='../../templates',
                static_folder='../../static')
    
    # Enable CORS
    CORS(app)
    
    # Configure logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    @app.route('/')
    def index():
        """Main application page"""
        return render_template('index.html')

    @app.route('/api/analyze-isrc-enhanced', methods=['POST'])
    def analyze_isrc_enhanced():
        """Comprehensive ISRC analysis endpoint"""
        try:
            data = request.get_json()
            isrc = data.get('isrc', '').strip().upper()
            
            # Basic validation
            if not isrc or len(isrc) != 12:
                return jsonify({'error': 'Invalid ISRC format'}), 400
            
            # Mock response for now
            return jsonify({
                'isrc': isrc,
                'metadata': {
                    'title': 'Sample Track',
                    'artist': 'Sample Artist', 
                    'album': 'Sample Album'
                },
                'confidence_score': 85.5,
                'status': 'success'
            })
                
        except Exception as e:
            logger.error(f"Error in ISRC analysis: {str(e)}")
            return jsonify({'error': str(e)}), 500

    @app.route('/api/health')
    def health_check():
        """Health check endpoint"""
        return jsonify({
            'status': 'healthy',
            'service': 'PRISM Analytics - ISRC Metadata Analyzer',
            'version': '1.0.0'
        })

    return app