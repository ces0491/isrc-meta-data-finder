"""
PRISM Analytics - ISRC Metadata Analyzer
Application configuration settings
"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration class"""
    
    # Flask Settings
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    DEBUG = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    HOST = os.getenv('HOST', '127.0.0.1')
    PORT = int(os.getenv('PORT', 5000))
    
    # API Keys
    SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
    SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET') 
    YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
    GENIUS_API_KEY = os.getenv('GENIUS_API_KEY')