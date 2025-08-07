#!/usr/bin/env python3
"""
PRISM Analytics - Complete Setup and Testing Script
This script will help you set up and test your metadata aggregation microservice
"""

import os
import sys
import subprocess
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

# ANSI color codes for better output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    """Print a formatted header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 60}{Colors.ENDC}\n")

def print_success(text: str):
    """Print success message"""
    print(f"{Colors.GREEN}✅ {text}{Colors.ENDC}")

def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.WARNING}⚠️  {text}{Colors.ENDC}")

def print_error(text: str):
    """Print error message"""
    print(f"{Colors.FAIL}❌ {text}{Colors.ENDC}")

def print_info(text: str):
    """Print info message"""
    print(f"{Colors.CYAN}ℹ️  {text}{Colors.ENDC}")

def check_python_version():
    """Check if Python version is 3.8+"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print_error(f"Python 3.8+ required. You have {sys.version}")
        return False
    print_success(f"Python version: {sys.version}")
    return True

def check_dependencies() -> Tuple[List[str], List[str]]:
    """Check which dependencies are installed"""
    required_packages = [
        'fastapi',
        'uvicorn',
        'requests',
        'pandas',
        'sqlalchemy',
        'pydantic',
        'aiohttp',
        'python-dotenv',
        'xlsxwriter',
        'beautifulsoup4',
        'spotipy',
        'musicbrainzngs'
    ]
    
    installed = []
    missing = []
    
    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
            installed.append(package)
        except ImportError:
            missing.append(package)
    
    return installed, missing

def install_dependencies(missing_packages: List[str]):
    """Install missing dependencies"""
    if not missing_packages:
        return True
    
    print_info(f"Installing {len(missing_packages)} missing packages...")
    
    try:
        # Install packages
        cmd = [sys.executable, '-m', 'pip', 'install'] + missing_packages
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print_success("All dependencies installed successfully")
            return True
        else:
            print_error(f"Installation failed: {result.stderr}")
            return False
    except Exception as e:
        print_error(f"Failed to install packages: {e}")
        return False

def setup_environment():
    """Set up .env file with API keys"""
    env_path = Path('.env')
    env_example_path = Path('.env.example')
    
    if env_path.exists():
        print_success(".env file already exists")
        return True
    
    if env_example_path.exists():
        print_info("Creating .env from .env.example")
        env_path.write_text(env_example_path.read_text())
        print_warning("Please edit .env and add your API keys")
        
        # Open .env in default editor
        if sys.platform == 'win32':
            os.startfile(str(env_path))
        elif sys.platform == 'darwin':
            subprocess.run(['open', str(env_path)])
        else:
            subprocess.run(['xdg-open', str(env_path)])
        
        print_info("Press Enter after adding your API keys...")
        input()
        return True
    else:
        # Create .env from scratch
        print_info("Creating new .env file")
        
        env_content = """# PRISM Analytics - Environment Configuration

# Spotify API (Required for audio features)
# Get from: https://developer.spotify.com/dashboard
SPOTIFY_CLIENT_ID=your_spotify_client_id_here
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret_here

# YouTube Data API (Optional but recommended)
# Get from: https://console.cloud.google.com/
YOUTUBE_API_KEY=your_youtube_api_key_here

# Genius API (Optional for lyrics)
# Get from: https://genius.com/api-clients
GENIUS_API_KEY=your_genius_api_key_here

# Last.fm API (Optional)
LASTFM_API_KEY=your_lastfm_api_key_here
LASTFM_SHARED_SECRET=your_lastfm_secret_here

# Application Settings
SECRET_KEY=change_this_to_a_random_secret_key
FLASK_ENV=development
FLASK_DEBUG=true
HOST=127.0.0.1
PORT=5000

# Database (Optional - defaults to SQLite)
# DATABASE_URL=postgresql://user:password@localhost/prism_analytics
"""
        
        env_path.write_text(env_content)
        print_success("Created .env file")
        print_warning("Please edit .env and add your API keys")
        return True

def check_api_configuration():
    """Check which APIs are configured"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print_warning("python-dotenv not installed, using system environment")
    
    apis = {
        'Spotify': bool(os.getenv('SPOTIFY_CLIENT_ID') and os.getenv('SPOTIFY_CLIENT_SECRET')),
        'YouTube': bool(os.getenv('YOUTUBE_API_KEY')),
        'Genius': bool(os.getenv('GENIUS_API_KEY')),
        'Last.fm': bool(os.getenv('LASTFM_API_KEY'))
    }
    
    print("\nAPI Configuration Status:")
    for api, configured in apis.items():
        if configured:
            print_success(f"{api} API configured")
        else:
            print_warning(f"{api} API not configured")
    
    if not apis['Spotify']:
        print_error("Spotify API is required for basic functionality")
        return False
    
    return True

def create_directory_structure():
    """Create required directories"""
    directories = [
        'data',
        'data/cache',
        'data/exports',
        'logs',
        'static',
        'static/css',
        'static/js',
        'static/assets',
        'templates',
        'src',
        'src/api',
        'src/models',
        'src/services',
        'config'
    ]
    
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
    
    print_success("Directory structure created")
    
    # Create __init__.py files
    init_paths = [
        'src/__init__.py',
        'src/api/__init__.py',
        'src/models/__init__.py',
        'src/services/__init__.py',
        'config/__init__.py'
    ]
    
    for init_path in init_paths:
        Path(init_path).touch(exist_ok=True)
    
    return True

def initialize_database():
    """Initialize the database"""
    try:
        from src.models.database import DatabaseManager
        
        db = DatabaseManager()
        db.create_tables()
        print_success("Database initialized successfully")
        return True
    except Exception as e:
        print_error(f"Failed to initialize database: {e}")
        return False

def test_spotify_connection():
    """Test Spotify API connection"""
    print_info("Testing Spotify API connection...")
    
    try:
        from src.services.api_clients import SpotifyClient
        
        client_id = os.getenv('SPOTIFY_CLIENT_ID')
        client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        
        if not client_id or not client_secret:
            print_error("Spotify credentials not found")
            return False
        
        client = SpotifyClient(client_id, client_secret)
        
        # Try to get an access token
        token = client._get_access_token()
        
        if token:
            print_success("Spotify API connection successful")
            
            # Try a test search
            result = client.search_by_isrc("USRC17607839")  # Test ISRC
            if result:
                print_success("Test ISRC search successful")
            else:
                print_warning("Test ISRC not found (this is normal)")
            
            return True
        else:
            print_error("Failed to get Spotify access token")
            return False
            
    except Exception as e:
        print_error(f"Spotify test failed: {e}")
        return False

def test_musicbrainz_connection():
    """Test MusicBrainz API connection"""
    print_info("Testing MusicBrainz API connection...")
    
    try:
        from src.services.api_clients import MusicBrainzClient
        
        client = MusicBrainzClient()
        
        # Try a test search
        result = client.search_recording_by_isrc("USRC17607839")
        
        if result is not None:
            print_success("MusicBrainz API connection successful")
            return True
        else:
            print_warning("MusicBrainz test returned no results")
            return True  # This is still okay
            
    except Exception as e:
        print_error(f"MusicBrainz test failed: {e}")
        return False

def run_sample_analysis():
    """Run a sample ISRC analysis"""
    print_header("Sample Analysis")
    
    test_isrcs = [
        "USRC17607839",  # Example ISRC
        "GBUM71505080",  # Another example
        "USCA21602485"   # Third example
    ]
    
    print_info(f"Testing with ISRCs: {', '.join(test_isrcs)}")
    
    try:
        import asyncio
        from src.services.api_clients import APIClientManager
        from src.services.metadata_collector_async import AsyncMetadataCollector
        from src.models.database import DatabaseManager
        from config.settings import Config
        
        # Initialize components
        config = Config()
        api_config = config.get_api_config()
        
        db_manager = DatabaseManager()
        api_clients = APIClientManager(api_config)
        collector = AsyncMetadataCollector(api_clients, db_manager)
        
        # Run analysis
        async def analyze():
            for isrc in test_isrcs:
                print(f"\nAnalyzing {isrc}...")
                try:
                    result = await collector.analyze_isrc_async(isrc, comprehensive=False)
                    
                    if result:
                        print_success(f"Found: {result.get('title', 'Unknown')} by {result.get('artist', 'Unknown')}")
                        print(f"  Sources: {', '.join(result.get('sources', []))}")
                        print(f"  Confidence: {result.get('confidence_score', 0):.1f}%")
                    else:
                        print_warning(f"No data found for {isrc}")
                        
                except Exception as e:
                    print_error(f"Analysis failed: {e}")
        
        # Run the async function
        asyncio.run(analyze())
        
        return True
        
    except Exception as e:
        print_error(f"Sample analysis failed: {e}")
        return False

def start_server():
    """Start the FastAPI server"""
    print_header("Starting PRISM Analytics Server")
    
    print_info("Server starting at: http://localhost:5000")
    print_info("API Documentation: http://localhost:5000/api/docs")
    print_info("Press Ctrl+C to stop the server")
    
    try:
        # Check which main file exists
        if Path("run.py").exists():
            subprocess.run([sys.executable, "run.py"])
        elif Path("main.py").exists():
            subprocess.run([sys.executable, "main.py"])
        else:
            print_error("No main application file found (run.py or main.py)")
            return False
            
    except KeyboardInterrupt:
        print_info("\nServer stopped")
        return True
    except Exception as e:
        print_error(f"Failed to start server: {e}")
        return False

def main():
    """Main setup and testing flow"""
    print_header("PRISM Analytics Setup & Testing")
    
    # 1. Check Python version
    if not check_python_version():
        return 1
    
    # 2. Check and install dependencies
    installed, missing = check_dependencies()
    
    if installed:
        print_success(f"{len(installed)} packages already installed")
    
    if missing:
        print_warning(f"{len(missing)} packages missing: {', '.join(missing)}")
        
        response = input("Install missing packages? (y/n): ").lower()
        if response == 'y':
            if not install_dependencies(missing):
                return 1
        else:
            print_error("Cannot continue without required packages")
            return 1
    
    # 3. Create directory structure
    create_directory_structure()
    
    # 4. Set up environment
    setup_environment()
    
    # 5. Check API configuration
    if not check_api_configuration():
        print_error("Please configure required APIs in .env file")
        return 1
    
    # 6. Initialize database
    if not initialize_database():
        print_warning("Database initialization failed, but continuing...")
    
    # 7. Test API connections
    print_header("Testing API Connections")
    
    spotify_ok = test_spotify_connection()
    musicbrainz_ok = test_musicbrainz_connection()
    
    if not spotify_ok:
        print_error("Spotify API is required for basic functionality")
        return 1
    
    # 8. Run sample analysis
    response = input("\nRun sample analysis? (y/n): ").lower()
    if response == 'y':
        run_sample_analysis()
    
    # 9. Start server
    print_header("Setup Complete!")
    print_success("All systems ready")
    
    response = input("\nStart the server now? (y/n): ").lower()
    if response == 'y':
        start_server()
    else:
        print_info("To start the server later, run: python run.py")
    
    return 0

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print_info("\nSetup cancelled by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        sys.exit(1)