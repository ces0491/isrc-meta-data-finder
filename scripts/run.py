#!/usr/bin/env python3
"""
PRISM Analytics - Simple Application Runner
"""
import os
import sys
import uvicorn
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

def main():
    """Run the application"""
    print("🎵 PRISM Analytics - ISRC to CSV Tool")
    print("=" * 50)
    
    # Check for .env file
    if not os.path.exists('.env'):
        print("⚠️  Warning: .env file not found")
        print("   Copy .env.example to .env and add your API keys")
        print("")
    
    # Load environment variables if .env exists
    if os.path.exists('.env'):
        try:
            from dotenv import load_dotenv
            load_dotenv()
            print("✅ Environment variables loaded from .env")
        except ImportError:
            print("⚠️  python-dotenv not installed, using system environment")
    
    # Check critical configuration
    spotify_configured = bool(
        os.getenv('SPOTIFY_CLIENT_ID') and 
        os.getenv('SPOTIFY_CLIENT_SECRET')
    )
    
    if spotify_configured:
        print("✅ Spotify API configured")
    else:
        print("⚠️  Spotify API not configured (limited functionality)")
    
    print("=" * 50)
    print("🚀 Starting server on http://localhost:5000")
    print("📚 API Documentation: http://localhost:5000/docs")
    print("=" * 50)
    
    # Import and run the main app
    try:
        from main import app
        
        # Run with uvicorn
        uvicorn.run(
            app,
            host="127.0.0.1",
            port=5000,
            log_level="info",
            reload=True  # Enable auto-reload for development
        )
    except ImportError as e:
        print(f"❌ Failed to import main app: {e}")
        print("   Make sure main.py exists in the current directory")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"\n❌ Server error: {e}")
        sys.exit(1)