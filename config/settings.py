# type: ignore
"""
PRISM Analytics - Simple Configuration
Focus on working functionality over perfect types
"""

import os

from dotenv import load_dotenv

load_dotenv()


class Config:
    """Simple configuration class"""

    # Flask Settings
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT", 5000))

    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", None)

    # API Keys
    SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
    SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
    LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
    LASTFM_SHARED_SECRET = os.getenv("LASTFM_SHARED_SECRET")
    GENIUS_API_KEY = os.getenv("GENIUS_API_KEY")

    # Cache settings
    CACHE_TTL_HOURS = 24

    @classmethod
    def validate_required_config(cls):
        """Simple validation"""
        validation = {}

        apis = {
            "spotify": bool(cls.SPOTIFY_CLIENT_ID and cls.SPOTIFY_CLIENT_SECRET),
            "youtube": bool(cls.YOUTUBE_API_KEY),
            "lastfm": bool(cls.LASTFM_API_KEY and cls.LASTFM_SHARED_SECRET),
        }

        for api, configured in apis.items():
            validation[api] = "configured" if configured else "not configured"

        return validation

    @classmethod
    def get_api_config(cls):
        """Get API config as simple dict"""
        return {
            "SPOTIFY_CLIENT_ID": cls.SPOTIFY_CLIENT_ID,
            "SPOTIFY_CLIENT_SECRET": cls.SPOTIFY_CLIENT_SECRET,
            "YOUTUBE_API_KEY": cls.YOUTUBE_API_KEY,
            "LASTFM_API_KEY": cls.LASTFM_API_KEY,
            "LASTFM_SHARED_SECRET": cls.LASTFM_SHARED_SECRET,
            "GENIUS_API_KEY": cls.GENIUS_API_KEY,
        }


def get_config(env=None):
    """Get configuration"""
    return Config()


if __name__ == "__main__":
    config = Config()
    validation = config.validate_required_config()

    print("🔧 PRISM Analytics Configuration")
    print("=" * 40)

    for service, status in validation.items():
        icon = "✅" if status == "configured" else "⚠️"
        print(f"{icon} {service}: {status}")
