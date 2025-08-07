#!/usr/bin/env python3
"""Quick diagnostic to check if everything is set up correctly"""

import sys
import os

print("🔍 PRISM Analytics - Setup Diagnostic")
print("=" * 50)

# Check Python version
print(f"✓ Python version: {sys.version}")

# Check imports
missing_packages = []

try:
    import fastapi
    print("✓ FastAPI installed")
except ImportError:
    print("✗ FastAPI not installed")
    missing_packages.append("fastapi")

try:
    import uvicorn
    print("✓ Uvicorn installed")
except ImportError:
    print("✗ Uvicorn not installed")
    missing_packages.append("uvicorn")

try:
    import aiohttp
    print("✓ aiohttp installed")
except ImportError:
    print("✗ aiohttp not installed")
    missing_packages.append("aiohttp")

try:
    import sqlalchemy
    print("✓ SQLAlchemy installed")
except ImportError:
    print("✗ SQLAlchemy not installed")
    missing_packages.append("sqlalchemy")

try:
    import requests
    print("✓ requests installed")
except ImportError:
    print("✗ requests not installed")
    missing_packages.append("requests")

try:
    import spotipy
    print("✓ spotipy installed")
except ImportError:
    print("✗ spotipy not installed")
    missing_packages.append("spotipy")

try:
    import musicbrainzngs
    print("✓ musicbrainzngs installed")
except ImportError:
    print("✗ musicbrainzngs not installed")
    missing_packages.append("musicbrainzngs")

try:
    import pandas
    print("✓ pandas installed")
except ImportError:
    print("✗ pandas not installed")
    missing_packages.append("pandas")

try:
    from dotenv import load_dotenv
    print("✓ python-dotenv installed")
except ImportError:
    print("✗ python-dotenv not installed")
    missing_packages.append("python-dotenv")

if missing_packages:
    print(f"\n⚠️  Install missing packages with:")
    print(f"   pip install {' '.join(missing_packages)}")

print("\n" + "-" * 50)

# Check .env file
if os.path.exists('.env'):
    print("✓ .env file exists")
    from dotenv import load_dotenv
    load_dotenv()
    
    # Check API keys
    spotify_id = os.getenv('SPOTIFY_CLIENT_ID')
    spotify_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    spotify_configured = bool(spotify_id and spotify_secret)
    
    if spotify_configured:
        print(f"  Spotify: ✓ Configured (ID: {spotify_id[:10]}...)")
    else:
        print(f"  Spotify: ✗ Not configured")
    
    youtube_key = os.getenv('YOUTUBE_API_KEY')
    youtube_configured = bool(youtube_key)
    
    if youtube_configured:
        print(f"  YouTube: ✓ Configured (Key: {youtube_key[:10]}...)")
    else:
        print(f"  YouTube: ✗ Not configured")
    
    genius_key = os.getenv('GENIUS_API_KEY')
    if genius_key:
        print(f"  Genius: ✓ Configured (Key: {genius_key[:10]}...)")
    else:
        print(f"  Genius: ✗ Not configured")
else:
    print("✗ .env file missing")
    if os.path.exists('.env.example'):
        print("  ℹ️  Copy .env.example to .env:")
        print("     copy .env.example .env")
    else:
        print("  ℹ️  Create a .env file with your API keys")

print("\n" + "-" * 50)

# Check directories
dirs_to_check = ['static', 'templates', 'src', 'config', 'data']
for dir_name in dirs_to_check:
    if os.path.exists(dir_name):
        print(f"✓ {dir_name}/ directory exists")
    else:
        print(f"✗ {dir_name}/ directory missing")

print("\n" + "-" * 50)

# Check database
try:
    from src.models.database import DatabaseManager
    
    # Create data directory if it doesn't exist
    os.makedirs('data', exist_ok=True)
    
    db = DatabaseManager()
    db.create_tables()
    print("✓ Database ready")
except Exception as e:
    print(f"✗ Database issue: {e}")
    print("  ℹ️  Will be created on first run")

print("\n" + "-" * 50)

# Check if we can import main modules
try:
    from config.settings import Config
    config = Config()
    print("✓ Configuration module working")
except Exception as e:
    print(f"✗ Configuration issue: {e}")

try:
    from src.services.api_clients import APIClientManager
    print("✓ API clients module working")
except Exception as e:
    print(f"✗ API clients issue: {e}")

print("\n" + "=" * 50)

if not missing_packages:
    print("✅ All dependencies installed!")
    print("\nTo start the server, run:")
    print("   python main.py")
    print("\nOr:")
    print("   python run.py dev")
else:
    print("⚠️  Fix missing dependencies first")

print("\nOnce running, access at:")
print("   Web Interface: http://localhost:5000")
print("   API Docs: http://localhost:5000/docs")