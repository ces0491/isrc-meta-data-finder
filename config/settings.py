# Updated config/settings.py

import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()


class Config:
    """
    Manages application configuration by loading values from environment variables.
    Provides methods to validate configuration and retrieve API keys.
    """

    def __init__(self):
        """Initializes the configuration object by loading all settings."""
        # Spotify API
        self.SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
        self.SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
        
        # YouTube API
        self.YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
        
        # Genius API
        self.GENIUS_API_KEY = os.getenv("GENIUS_API_KEY")
        
        # Last.fm API
        self.LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
        self.LASTFM_SHARED_SECRET = os.getenv("LASTFM_SHARED_SECRET")
        
        # Discogs API - Updated to use OAuth credentials
        self.DISCOGS_CONSUMER_KEY = os.getenv("DISCOGS_CONSUMER_KEY")
        self.DISCOGS_CONSUMER_SECRET = os.getenv("DISCOGS_CONSUMER_SECRET")
        self.DISCOGS_USER_TOKEN = os.getenv("DISCOGS_USER_TOKEN")  # Optional
        
        # Legacy support for old DISCOGS_API_KEY variable
        if not self.DISCOGS_CONSUMER_KEY and os.getenv("DISCOGS_API_KEY"):
            # If someone still has the old API key, use it as user token
            self.DISCOGS_USER_TOKEN = os.getenv("DISCOGS_API_KEY")

        # Application Settings
        self.SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-for-prism")
        self.HOST = os.getenv("HOST", "127.0.0.1")
        self.PORT = int(os.getenv("PORT", 5000))
        self.CACHE_TTL_HOURS = int(os.getenv("CACHE_TTL_HOURS", 24))

    def validate_required_config(self):
        """
        Validates that essential API keys are configured and returns their status.
        """
        validation_status = {
            "spotify": "✅ configured" if self.SPOTIFY_CLIENT_ID and self.SPOTIFY_CLIENT_SECRET else "⚠️ not configured",
            "youtube": "✅ configured" if self.YOUTUBE_API_KEY else "⚠️ not configured",
            "genius": "✅ configured" if self.GENIUS_API_KEY else "⚠️ not configured",
            "lastfm": "✅ configured" if self.LASTFM_API_KEY and self.LASTFM_SHARED_SECRET else "⚠️ not configured",
            "discogs": "✅ configured (OAuth)" if self.DISCOGS_CONSUMER_KEY and self.DISCOGS_CONSUMER_SECRET 
                      else "⚠️ configured (Token only)" if self.DISCOGS_USER_TOKEN 
                      else "❌ not configured",
        }
        return validation_status

    def get_api_config(self):
        """
        Returns a dictionary of all configured API keys for client managers.
        """
        return {
            # Spotify
            "SPOTIFY_CLIENT_ID": self.SPOTIFY_CLIENT_ID,
            "SPOTIFY_CLIENT_SECRET": self.SPOTIFY_CLIENT_SECRET,
            
            # YouTube
            "YOUTUBE_API_KEY": self.YOUTUBE_API_KEY,
            
            # Genius
            "GENIUS_API_KEY": self.GENIUS_API_KEY,
            
            # Last.fm
            "LASTFM_API_KEY": self.LASTFM_API_KEY,
            "LASTFM_SHARED_SECRET": self.LASTFM_SHARED_SECRET,
            
            # Discogs (OAuth)
            "DISCOGS_CONSUMER_KEY": self.DISCOGS_CONSUMER_KEY,
            "DISCOGS_CONSUMER_SECRET": self.DISCOGS_CONSUMER_SECRET,
            "DISCOGS_USER_TOKEN": self.DISCOGS_USER_TOKEN,
            
            # Legacy support
            "DISCOGS_API_KEY": self.DISCOGS_USER_TOKEN,  # For backward compatibility
        }


# This block allows you to run the file directly to check configuration
if __name__ == "__main__":
    config = Config()
    validation = config.validate_required_config()

    print("🔧 PRISM Analytics Configuration Check")
    print("=" * 40)

    for service, status in validation.items():
        print(f"{service.capitalize()}: {status}")
    
    # Additional Discogs-specific information
    if config.DISCOGS_CONSUMER_KEY:
        print(f"\n📀 Discogs OAuth Details:")
        print(f"  Consumer Key: {config.DISCOGS_CONSUMER_KEY[:8]}..." if config.DISCOGS_CONSUMER_KEY else "  Consumer Key: Not set")
        print(f"  Consumer Secret: {'***' if config.DISCOGS_CONSUMER_SECRET else 'Not set'}")
        print(f"  User Token: {'Set' if config.DISCOGS_USER_TOKEN else 'Not set (optional)'}")
    
    # Check for common issues
    print("\n⚠️ Common Issues to Check:")
    if not config.SPOTIFY_CLIENT_ID or not config.SPOTIFY_CLIENT_SECRET:
        print("  • Spotify: Create an app at https://developer.spotify.com/dashboard")
    if not config.YOUTUBE_API_KEY:
        print("  • YouTube: Enable YouTube Data API v3 in Google Cloud Console")
    if not config.DISCOGS_CONSUMER_KEY or not config.DISCOGS_CONSUMER_SECRET:
        print("  • Discogs: Get Consumer Key/Secret from https://www.discogs.com/settings/developers")
        print("    Your app 'ISRC Lead Analyzer' should show these credentials")