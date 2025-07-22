#!/usr/bin/env python3
"""
PRISM Analytics - ISRC Metadata Analyzer
Main entry point for the application
"""
import os
from src.api.routes import create_app
from config.settings import Config

def main():
    """Main application entry point"""
    app = create_app()
    
    # Get configuration
    config = Config()
    host = config.HOST
    port = config.PORT
    debug = config.DEBUG
    
    print("🎵 PRISM Analytics - ISRC Metadata Analyzer")
    print("Transforming Music Data into Actionable Insights")
    print(f"Running on http://{host}:{port}")
    
    app.run(host=host, port=port, debug=debug)

if __name__ == "__main__":
    main()