# src/config/settings.py

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
        # API Keys
        self.SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
        self.SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
        self.YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
        self.GENIUS_API_KEY = os.getenv("GENIUS_API_KEY")
        self.LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
        self.LASTFM_SHARED_SECRET = os.getenv("LASTFM_SHARED_SECRET")
        self.DISCOGS_API_KEY = os.getenv("DISCOGS_API_KEY")

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
            "spotify": "configured" if self.SPOTIFY_CLIENT_ID and self.SPOTIFY_CLIENT_SECRET else "⚠️ not configured",
            "youtube": "configured" if self.YOUTUBE_API_KEY else "⚠️ not configured",
            "genius": "configured" if self.GENIUS_API_KEY else "⚠️ not configured",
            "lastfm": "configured" if self.LASTFM_API_KEY and self.LASTFM_SHARED_SECRET else "⚠️ not configured",
            "discogs": "configured" if self.DISCOGS_API_KEY else "⚠️ not configured",
        }
        return validation_status

    def get_api_config(self):
        """
        Returns a dictionary of all configured API keys for client managers.
        """
        return {
            "SPOTIFY_CLIENT_ID": self.SPOTIFY_CLIENT_ID,
            "SPOTIFY_CLIENT_SECRET": self.SPOTIFY_CLIENT_SECRET,
            "YOUTUBE_API_KEY": self.YOUTUBE_API_KEY,
            "GENIUS_API_KEY": self.GENIUS_API_KEY,
            "LASTFM_API_KEY": self.LASTFM_API_KEY,
            "LASTFM_SHARED_SECRET": self.LASTFM_SHARED_SECRET,
            "DISCOGS_API_KEY": self.DISCOGS_API_KEY,
        }


# This block allows you to run the file directly to check configuration
if __name__ == "__main__":
    config = Config()
    validation = config.validate_required_config()

    print("🔧 PRISM Analytics Configuration Check")
    print("=" * 40)

    for service, status in validation.items():
        icon = "✅" if "configured" in status else "⚠️"
        print(f"{icon} {service.capitalize()}: {status}")