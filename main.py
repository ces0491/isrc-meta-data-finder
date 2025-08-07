#!/usr/bin/env python3
"""
PRISM Analytics - Phase 2 Enhanced Version
ISRC Metadata Aggregator with Genius API, Database Storage, and Enhanced Confidence
"""

import asyncio
import base64
import csv
import io
import json
import logging
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import requests
import uvicorn
from fastapi import (
    FastAPI,
    HTTPException,
    Query,
    Response,
)
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from typing import List, Optional, Tuple

# Excel export support
try:
    import xlsxwriter
    from xlsxwriter import Workbook

    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    print("⚠️ xlsxwriter not installed. Excel export will be limited.")


# Load environment variables
def load_environment():
    """Load environment variables with multiple fallback methods"""
    try:
        from dotenv import load_dotenv

        env_paths = [
            ".env",
            Path(".env"),
            Path(__file__).parent / ".env",
            Path.cwd() / ".env",
        ]
        for env_path in env_paths:
            if Path(env_path).exists():
                load_dotenv(env_path, override=True)
                break
    except ImportError:
        pass

    # Manual .env parsing as fallback
    env_file = Path(".env")
    if env_file.exists():
        try:
            with open(env_file) as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        value = value.strip().strip('"').strip("'")
                        os.environ[key.strip()] = value
        except Exception:
            pass


load_environment()

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============= DATABASE SETUP =============
class DatabaseManager:
    """SQLite database manager for metadata storage"""

    def __init__(self, db_path="data/prism_metadata.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    def init_database(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Main tracks table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS tracks (
                    isrc TEXT PRIMARY KEY,
                    title TEXT,
                    artist TEXT,
                    album TEXT,
                    duration_ms INTEGER,
                    release_date TEXT,
                    spotify_id TEXT,
                    spotify_url TEXT,
                    musicbrainz_id TEXT,
                    youtube_video_id TEXT,
                    youtube_url TEXT,
                    youtube_views INTEGER,
                    tempo REAL,
                    key INTEGER,
                    mode INTEGER,
                    energy REAL,
                    danceability REAL,
                    valence REAL,
                    popularity INTEGER,
                    confidence_score REAL,
                    data_completeness REAL,
                    sources TEXT,
                    last_updated TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Lyrics table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS lyrics (
                    isrc TEXT PRIMARY KEY,
                    lyrics_text TEXT,
                    genius_song_id INTEGER,
                    genius_url TEXT,
                    language_code TEXT,
                    explicit_content BOOLEAN,
                    copyright_info TEXT,
                    source_confidence REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (isrc) REFERENCES tracks(isrc)
                )
            """)

            # Credits table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS credits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    isrc TEXT,
                    person_name TEXT,
                    credit_type TEXT,
                    role_details TEXT,
                    source_api TEXT,
                    source_confidence REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (isrc) REFERENCES tracks(isrc)
                )
            """)

            # Analysis history table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS analysis_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    isrc TEXT,
                    analysis_type TEXT,
                    status TEXT,
                    confidence_score REAL,
                    processing_time_ms INTEGER,
                    error_message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (isrc) REFERENCES tracks(isrc)
                )
            """)

            conn.commit()
            logger.info("📊 Database initialized successfully")

    @contextmanager
    def get_connection(self):
        """Get database connection context manager"""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def save_track_metadata(self, metadata: dict):
        """Save track metadata to database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Convert sources list to JSON string
            sources_json = json.dumps(metadata.get("sources", []))

            cursor.execute(
                """
                INSERT OR REPLACE INTO tracks (
                    isrc, title, artist, album, duration_ms, release_date,
                    spotify_id, spotify_url, musicbrainz_id, youtube_video_id,
                    youtube_url, youtube_views, tempo, key, mode, energy,
                    danceability, valence, popularity, confidence_score,
                    data_completeness, sources, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    metadata.get("isrc"),
                    metadata.get("title"),
                    metadata.get("artist"),
                    metadata.get("album"),
                    metadata.get("duration_ms"),
                    metadata.get("release_date"),
                    metadata.get("spotify_id"),
                    metadata.get("spotify_url"),
                    metadata.get("musicbrainz_id"),
                    metadata.get("youtube_video_id"),
                    metadata.get("youtube_url"),
                    metadata.get("youtube_views"),
                    metadata.get("tempo"),
                    metadata.get("key"),
                    metadata.get("mode"),
                    metadata.get("energy"),
                    metadata.get("danceability"),
                    metadata.get("valence"),
                    metadata.get("popularity"),
                    metadata.get("confidence"),
                    metadata.get("data_completeness"),
                    sources_json,
                    metadata.get("last_updated"),
                ),
            )

            conn.commit()
            logger.info(f"💾 Saved metadata for {metadata.get('isrc')} to database")

    def save_lyrics(self, isrc: str, lyrics_data: dict):
        """Save lyrics to database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO lyrics (
                    isrc, lyrics_text, genius_song_id, genius_url,
                    language_code, explicit_content, copyright_info,
                    source_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    isrc,
                    lyrics_data.get("lyrics_text"),
                    lyrics_data.get("genius_song_id"),
                    lyrics_data.get("genius_url"),
                    lyrics_data.get("language_code"),
                    lyrics_data.get("explicit_content", False),
                    json.dumps(lyrics_data.get("copyright_info", {})),
                    lyrics_data.get("confidence", 0),
                ),
            )

            conn.commit()
            logger.info(f"💾 Saved lyrics for {isrc} to database")

    def save_credits(self, isrc: str, credits_list: List[dict]):
        """Save credits to database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Clear existing credits
            cursor.execute("DELETE FROM credits WHERE isrc = ?", (isrc,))

            # Insert new credits
            for credit in credits_list:
                cursor.execute(
                    """
                    INSERT INTO credits (
                        isrc, person_name, credit_type, role_details,
                        source_api, source_confidence
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (
                        isrc,
                        credit.get("person_name"),
                        credit.get("credit_type"),
                        json.dumps(credit.get("role_details", {})),
                        credit.get("source_api"),
                        credit.get("source_confidence", 0),
                    ),
                )

            conn.commit()
            logger.info(f"💾 Saved {len(credits_list)} credits for {isrc} to database")

    def get_track_by_isrc(self, isrc: str) -> Optional[dict]:
        """Get track metadata from database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tracks WHERE isrc = ?", (isrc,))
            row = cursor.fetchone()

            if row:
                track = dict(row)
                # Parse sources JSON
                if track.get("sources"):
                    track["sources"] = json.loads(track["sources"])
                return track
            return None

    def get_lyrics_by_isrc(self, isrc: str) -> Optional[dict]:
        """Get lyrics from database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM lyrics WHERE isrc = ?", (isrc,))
            row = cursor.fetchone()

            if row:
                lyrics = dict(row)
                # Parse copyright info JSON
                if lyrics.get("copyright_info"):
                    lyrics["copyright_info"] = json.loads(lyrics["copyright_info"])
                return lyrics
            return None

    def get_analysis_stats(self) -> dict:
        """Get analysis statistics"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            stats = {}

            # Total tracks analyzed
            cursor.execute("SELECT COUNT(*) as count FROM tracks")
            stats["total_tracks"] = cursor.fetchone()["count"]

            # Average confidence score
            cursor.execute("SELECT AVG(confidence_score) as avg FROM tracks")
            stats["avg_confidence"] = cursor.fetchone()["avg"] or 0

            # Tracks with lyrics
            cursor.execute("SELECT COUNT(*) as count FROM lyrics")
            stats["tracks_with_lyrics"] = cursor.fetchone()["count"]

            # Source distribution
            cursor.execute(
                "SELECT COUNT(*) as count FROM tracks WHERE spotify_id IS NOT NULL"
            )
            stats["spotify_coverage"] = cursor.fetchone()["count"]

            cursor.execute(
                "SELECT COUNT(*) as count FROM tracks WHERE youtube_video_id IS NOT NULL"
            )
            stats["youtube_coverage"] = cursor.fetchone()["count"]

            cursor.execute(
                "SELECT COUNT(*) as count FROM tracks WHERE musicbrainz_id IS NOT NULL"
            )
            stats["musicbrainz_coverage"] = cursor.fetchone()["count"]

            return stats


# Initialize database
db = DatabaseManager()


# ============= ENHANCED CACHE WITH DB FALLBACK =============
class MetadataCache:
    """Enhanced cache with database fallback"""

    def __init__(self, cache_dir="data/cache", ttl_hours=24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_hours = ttl_hours
        self.db = db  # Use global database manager
        logger.info(f"📁 Cache initialized at {self.cache_dir}")

    def _get_cache_path(self, isrc: str) -> Path:
        """Get cache file path for ISRC"""
        return self.cache_dir / f"{isrc}.json"

    def get(self, isrc: str) -> Optional[dict]:
        """Get cached data with database fallback"""
        cache_file = self._get_cache_path(isrc)

        # Try file cache first
        if cache_file.exists():
            try:
                age_hours = (time.time() - cache_file.stat().st_mtime) / 3600

                if age_hours < self.ttl_hours:
                    with open(cache_file) as f:
                        data = json.load(f)
                    logger.info(f"✅ Cache hit for {isrc} (age: {age_hours:.1f}h)")
                    return data
            except Exception as e:
                logger.error(f"Cache read error: {e}")

        # Try database fallback
        db_data = self.db.get_track_by_isrc(isrc)
        if db_data:
            logger.info(f"📊 Database hit for {isrc}")
            # Update file cache from database
            self.set(isrc, db_data)
            return db_data

        return None

    def set(self, isrc: str, data: dict):
        """Store data in cache and database"""
        cache_file = self._get_cache_path(isrc)

        try:
            # Save to file cache
            with open(cache_file, "w") as f:
                json.dump(data, f, indent=2)
            logger.info(f"💾 Cached data for {isrc}")

            # Save to database
            self.db.save_track_metadata(data)

        except Exception as e:
            logger.error(f"Cache write error: {e}")


# Initialize cache
cache = MetadataCache()


# ============= GENIUS API INTEGRATION =============
async def get_genius_lyrics(
    isrc: str, track_title: Optional[str] = None, artist: Optional[str] = None
) -> dict:
    """Get lyrics from Genius API"""
    try:
        api_key = os.getenv("GENIUS_API_KEY")

        if not api_key:
            return {"error": "Genius API not configured"}

        if not track_title or not artist:
            return {"error": "Track title and artist required for Genius search"}

        # Search for the song
        headers = {"Authorization": f"Bearer {api_key}"}

        search_params = {"q": f"{artist} {track_title}"}

        search_response = requests.get(
            "https://api.genius.com/search",
            headers=headers,
            params=search_params,
            timeout=10,
        )

        if search_response.status_code != 200:
            return {"error": f"Genius search failed: {search_response.status_code}"}

        search_data = search_response.json()

        if search_data.get("response", {}).get("hits"):
            # Get the most relevant hit
            hit = search_data["response"]["hits"][0]
            result = hit["result"]

            # Get song details
            song_id = result.get("id")
            song_response = requests.get(
                f"https://api.genius.com/songs/{song_id}", headers=headers, timeout=10
            )

            if song_response.status_code == 200:
                song_data = song_response.json()["response"]["song"]

                # Extract credits
                credits = []

                # Primary artist
                if song_data.get("primary_artist"):
                    credits.append(
                        {
                            "person_name": song_data["primary_artist"]["name"],
                            "credit_type": "primary_artist",
                            "source_api": "genius",
                            "source_confidence": 0.9,
                        }
                    )

                # Featured artists
                for featured_artist in song_data.get("featured_artists", []):
                    credits.append(
                        {
                            "person_name": featured_artist["name"],
                            "credit_type": "featured_artist",
                            "source_api": "genius",
                            "source_confidence": 0.9,
                        }
                    )

                # Producer artists
                for producer in song_data.get("producer_artists", []):
                    credits.append(
                        {
                            "person_name": producer["name"],
                            "credit_type": "producer",
                            "source_api": "genius",
                            "source_confidence": 0.85,
                        }
                    )

                # Writer artists
                for writer in song_data.get("writer_artists", []):
                    credits.append(
                        {
                            "person_name": writer["name"],
                            "credit_type": "writer",
                            "source_api": "genius",
                            "source_confidence": 0.85,
                        }
                    )

                return {
                    "genius_song_id": song_id,
                    "genius_url": result.get("url", ""),
                    "title": result.get("title", ""),
                    "artist": result.get("primary_artist", {}).get("name", ""),
                    "lyrics_state": result.get("lyrics_state", "none"),
                    "page_views": result.get("stats", {}).get("pageviews", 0),
                    "credits": credits,
                    "release_date": song_data.get("release_date_for_display", ""),
                    "language": song_data.get("language", "en"),
                    "explicit": song_data.get("explicit", False),
                    "confidence": 80,
                }

        return {"error": "No songs found on Genius"}

    except Exception as e:
        return {"error": f"Genius API error: {str(e)}"}


# ============= ENHANCED CONFIDENCE SCORING =============
class ConfidenceScorer:
    """Enhanced confidence scoring system"""

    @staticmethod
    def calculate_comprehensive_score(
        metadata: dict, lyrics_data: Optional[dict] = None
    ) -> Tuple[float, dict]:
        """Calculate comprehensive confidence score with detailed breakdown"""

        scores = {
            "data_sources": 0.0,
            "essential_fields": 0.0,
            "audio_features": 0.0,
            "external_ids": 0.0,
            "popularity_metrics": 0.0,
            "lyrics_availability": 0.0,
            "credits_completeness": 0.0,
            "cross_validation": 0.0,
        }

        weights = {
            "data_sources": 0.25,
            "essential_fields": 0.20,
            "audio_features": 0.15,
            "external_ids": 0.10,
            "popularity_metrics": 0.10,
            "lyrics_availability": 0.10,
            "credits_completeness": 0.05,
            "cross_validation": 0.05,
        }

        # 1. Data Sources Score (25%)
        sources = metadata.get("sources", [])
        if "Spotify" in sources:
            scores["data_sources"] += 35
        if "MusicBrainz" in sources:
            scores["data_sources"] += 35
        if "YouTube" in sources:
            scores["data_sources"] += 30

        # 2. Essential Fields Score (20%)
        essential_fields = ["title", "artist", "album", "duration_ms", "release_date"]
        fields_present = sum(1 for field in essential_fields if metadata.get(field))
        scores["essential_fields"] = (fields_present / len(essential_fields)) * 100

        # 3. Audio Features Score (15%)
        audio_features = ["tempo", "key", "energy", "danceability", "valence"]
        features_present = sum(
            1 for feature in audio_features if metadata.get(feature) is not None
        )
        scores["audio_features"] = (features_present / len(audio_features)) * 100

        # 4. External IDs Score (10%)
        external_ids = ["spotify_id", "musicbrainz_id", "youtube_video_id"]
        ids_present = sum(1 for id_field in external_ids if metadata.get(id_field))
        scores["external_ids"] = (ids_present / len(external_ids)) * 100

        # 5. Popularity Metrics Score (10%)
        if metadata.get("popularity"):
            scores["popularity_metrics"] += 50
        if metadata.get("youtube_views"):
            scores["popularity_metrics"] += 50

        # 6. Lyrics Availability Score (10%)
        if lyrics_data:
            if lyrics_data.get("genius_song_id"):
                scores["lyrics_availability"] = 100
            elif lyrics_data.get("lyrics_text"):
                scores["lyrics_availability"] = 80

        # 7. Credits Completeness Score (5%)
        if lyrics_data and lyrics_data.get("credits"):
            credits = lyrics_data["credits"]
            credit_types = set(credit["credit_type"] for credit in credits)
            if "writer" in credit_types:
                scores["credits_completeness"] += 40
            if "producer" in credit_types:
                scores["credits_completeness"] += 30
            if "primary_artist" in credit_types:
                scores["credits_completeness"] += 30

        # 8. Cross-validation Score (5%)
        if len(sources) >= 2:
            # Check if title/artist match across sources
            scores["cross_validation"] = 100 if len(sources) >= 3 else 70

        # Calculate weighted total
        total_score = sum(scores[key] * weights[key] for key in scores)

        # Apply confidence multipliers
        if len(sources) == 0:
            total_score *= 0.3
        elif len(sources) == 1:
            total_score *= 0.7
        elif len(sources) == 2:
            total_score *= 0.9

        # Cap at 100
        total_score = min(100, total_score)

        # Calculate data completeness
        all_fields = list(metadata.keys())
        non_empty_fields = sum(
            1 for field in all_fields if metadata.get(field) not in [None, "", 0, []]
        )
        data_completeness = (
            (non_empty_fields / len(all_fields)) * 100 if all_fields else 0
        )

        return total_score, {
            "confidence_score": round(total_score, 2),
            "data_completeness": round(data_completeness, 2),
            "score_breakdown": scores,
            "weights_used": weights,
            "quality_rating": ConfidenceScorer.get_quality_rating(total_score),
        }

    @staticmethod
    def get_quality_rating(score: float) -> str:
        """Get quality rating based on confidence score"""
        if score >= 90:
            return "Excellent"
        elif score >= 75:
            return "Good"
        elif score >= 60:
            return "Fair"
        elif score >= 40:
            return "Poor"
        else:
            return "Insufficient"


# Initialize confidence scorer
scorer = ConfidenceScorer()


# ============= REQUEST MODELS =============
class ISRCRequest(BaseModel):
    isrc: str


class EnhancedISRCRequest(BaseModel):
    isrc: str
    include_lyrics: bool = True
    include_credits: bool = True
    force_refresh: bool = False


class BulkISRCRequest(BaseModel):
    isrcs: List[str]
    export_format: str = "csv"
    include_lyrics: bool = False


# ============= ENHANCED METADATA COLLECTION =============
async def collect_enhanced_metadata(
    isrc: str, include_lyrics: bool = True, force_refresh: bool = False
) -> dict:
    """Collect enhanced metadata from all sources including Genius"""

    # Check cache first (unless force refresh)
    if not force_refresh:
        cached_data = cache.get(isrc)
        if cached_data:
            # Check if we need to add lyrics
            if include_lyrics and not cached_data.get("has_lyrics"):
                # Fetch lyrics if not in cache
                lyrics_data = await get_genius_lyrics(
                    isrc, cached_data.get("title"), cached_data.get("artist")
                )
                if "error" not in lyrics_data:
                    cached_data["lyrics_data"] = lyrics_data
                    cached_data["has_lyrics"] = True
                    cache.set(isrc, cached_data)
            return cached_data

    # Start timing
    start_time = time.time()

    result = {
        "isrc": isrc,
        "title": "",
        "artist": "",
        "album": "",
        "duration_ms": "",
        "release_date": "",
        "spotify_id": "",
        "spotify_url": "",
        "musicbrainz_id": "",
        "youtube_video_id": "",
        "youtube_url": "",
        "youtube_views": "",
        "tempo": "",
        "key": "",
        "mode": "",
        "energy": "",
        "danceability": "",
        "valence": "",
        "popularity": "",
        "confidence": 0,
        "data_completeness": 0,
        "sources": [],
        "has_lyrics": False,
        "processing_time_ms": 0,
        "last_updated": datetime.now().isoformat(),
    }

    # Collect from all sources (existing code)
    logger.info(f"🎵 Checking Spotify for ISRC: {isrc}")
    spotify_data = await get_spotify_metadata(isrc)

    if "error" not in spotify_data:
        result.update(spotify_data)
        result["sources"].append("Spotify")
        logger.info(f"✅ Found on Spotify: {result['title']} by {result['artist']}")

    logger.info(f"🎼 Checking MusicBrainz for ISRC: {isrc}")
    mb_data = await get_musicbrainz_metadata(isrc)

    if "error" not in mb_data:
        for key in ["title", "artist", "album", "release_date"]:
            if not result[key] and mb_data.get(key):
                result[key] = mb_data[key]
        result["musicbrainz_id"] = mb_data.get("musicbrainz_id", "")
        result["sources"].append("MusicBrainz")
        logger.info(f"✅ Found on MusicBrainz: {mb_data.get('title', 'Unknown')}")

    if result["title"] or result["artist"]:
        logger.info(f"📺 Checking YouTube for ISRC: {isrc}")
        youtube_data = await get_youtube_metadata(
            isrc, result.get("title") or None, result.get("artist") or None
        )

        if "error" not in youtube_data:
            result.update({k: v for k, v in youtube_data.items() if k != "confidence"})
            result["sources"].append("YouTube")
            logger.info(
                f"✅ Found on YouTube: {youtube_data.get('youtube_title', 'Unknown')}"
            )

    # NEW: Collect from Genius if we have title and artist
    lyrics_data = None
    if include_lyrics and result["title"] and result["artist"]:
        logger.info(f"📝 Checking Genius for lyrics: {isrc}")
        lyrics_data = await get_genius_lyrics(isrc, result["title"], result["artist"])

        if "error" not in lyrics_data:
            result["sources"].append("Genius")
            result["has_lyrics"] = True
            result["lyrics_data"] = lyrics_data
            logger.info(f"✅ Found on Genius: {lyrics_data.get('title', 'Unknown')}")

            # Save lyrics to database
            db.save_lyrics(isrc, lyrics_data)

            # Save credits if available
            if lyrics_data.get("credits"):
                db.save_credits(isrc, lyrics_data["credits"])

    # Calculate enhanced confidence score
    confidence, confidence_details = scorer.calculate_comprehensive_score(
        result, lyrics_data
    )
    result["confidence"] = confidence
    result["data_completeness"] = confidence_details["data_completeness"]
    result["confidence_details"] = confidence_details

    # Calculate processing time
    result["processing_time_ms"] = int((time.time() - start_time) * 1000)

    # Log analysis to history
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO analysis_history (
                isrc, analysis_type, status, confidence_score, 
                processing_time_ms
            ) VALUES (?, ?, ?, ?, ?)
        """,
            (
                isrc,
                "comprehensive" if include_lyrics else "basic",
                "success" if result["sources"] else "no_data",
                confidence,
                result["processing_time_ms"],
            ),
        )
        conn.commit()

    # Cache the result if we found data
    if result["sources"]:
        cache.set(isrc, result)

    return result


# Keep existing helper functions from Phase 1
async def get_spotify_metadata(isrc: str) -> dict:
    """Get metadata from Spotify API"""
    try:
        client_id = os.getenv("SPOTIFY_CLIENT_ID")
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")

        if not client_id or not client_secret:
            return {"error": "Spotify credentials not configured"}

        # Get access token
        auth_string = f"{client_id}:{client_secret}"
        auth_bytes = auth_string.encode("utf-8")
        auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")

        token_headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded",
        }

        token_data = {"grant_type": "client_credentials"}

        token_response = requests.post(
            "https://accounts.spotify.com/api/token",
            headers=token_headers,
            data=token_data,
            timeout=10,
        )

        if token_response.status_code != 200:
            return {"error": f"Spotify auth failed: {token_response.status_code}"}

        token_info = token_response.json()
        access_token = token_info["access_token"]

        # Search for ISRC
        search_headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        search_params = {"q": f"isrc:{isrc}", "type": "track", "limit": 1}

        search_response = requests.get(
            "https://api.spotify.com/v1/search",
            headers=search_headers,
            params=search_params,
            timeout=10,
        )

        if search_response.status_code != 200:
            return {"error": f"Spotify search failed: {search_response.status_code}"}

        search_data = search_response.json()

        if search_data.get("tracks", {}).get("items"):
            track = search_data["tracks"]["items"][0]

            # Get audio features if track ID available
            audio_features = {}
            if track.get("id"):
                features_response = requests.get(
                    f"https://api.spotify.com/v1/audio-features/{track['id']}",
                    headers=search_headers,
                    timeout=10,
                )
                if features_response.status_code == 200:
                    audio_features = features_response.json()

            return {
                "title": track.get("name", ""),
                "artist": ", ".join([a["name"] for a in track.get("artists", [])]),
                "album": track.get("album", {}).get("name", ""),
                "duration_ms": track.get("duration_ms", ""),
                "release_date": track.get("album", {}).get("release_date", ""),
                "spotify_id": track.get("id", ""),
                "spotify_url": track.get("external_urls", {}).get("spotify", ""),
                "popularity": track.get("popularity", ""),
                "tempo": audio_features.get("tempo", ""),
                "key": audio_features.get("key", ""),
                "mode": audio_features.get("mode", ""),
                "energy": audio_features.get("energy", ""),
                "danceability": audio_features.get("danceability", ""),
                "valence": audio_features.get("valence", ""),
            }
        else:
            return {"error": "No tracks found for this ISRC"}

    except Exception as e:
        return {"error": f"Spotify API error: {str(e)}"}


async def get_youtube_metadata(
    isrc: str, track_title: Optional[str] = None, artist: Optional[str] = None
) -> dict:
    """Get metadata from YouTube API"""
    try:
        api_key = os.getenv("YOUTUBE_API_KEY")

        if not api_key:
            return {"error": "YouTube API not configured"}

        # Build search query
        if track_title and artist:
            search_query = f'"{artist}" "{track_title}" "{isrc}"'
        else:
            search_query = f'"{isrc}"'

        # Search for videos
        search_params = {
            "part": "snippet",
            "q": search_query,
            "type": "video",
            "videoCategoryId": "10",  # Music category
            "maxResults": 5,
            "key": api_key,
        }

        search_response = requests.get(
            "https://www.googleapis.com/youtube/v3/search",
            params=search_params,
            timeout=10,
        )

        if search_response.status_code != 200:
            return {"error": f"YouTube search failed: {search_response.status_code}"}

        search_data = search_response.json()

        if search_data.get("items"):
            # Find best match
            best_match = None
            for item in search_data["items"]:
                snippet = item.get("snippet", {})

                # Check if ISRC is in description
                description = snippet.get("description", "").upper()
                if isrc in description:
                    best_match = item
                    break

                # Otherwise take first result
                if not best_match:
                    best_match = item

            if best_match:
                snippet = best_match["snippet"]
                video_id = best_match["id"]["videoId"]

                # Get video statistics
                stats_params = {
                    "part": "statistics,contentDetails",
                    "id": video_id,
                    "key": api_key,
                }

                stats_response = requests.get(
                    "https://www.googleapis.com/youtube/v3/videos",
                    params=stats_params,
                    timeout=10,
                )

                stats_data = {}
                if stats_response.status_code == 200:
                    stats_result = stats_response.json()
                    if stats_result.get("items"):
                        stats_data = stats_result["items"][0].get("statistics", {})

                return {
                    "youtube_video_id": video_id,
                    "youtube_url": f"https://www.youtube.com/watch?v={video_id}",
                    "youtube_title": snippet.get("title", ""),
                    "youtube_channel": snippet.get("channelTitle", ""),
                    "youtube_channel_id": snippet.get("channelId", ""),
                    "youtube_published": snippet.get("publishedAt", ""),
                    "youtube_views": stats_data.get("viewCount", ""),
                    "youtube_likes": stats_data.get("likeCount", ""),
                    "youtube_comments": stats_data.get("commentCount", ""),
                }

        return {"error": "No YouTube videos found for this ISRC"}

    except Exception as e:
        return {"error": f"YouTube API error: {str(e)}"}


async def get_musicbrainz_metadata(isrc: str) -> dict:
    """Get metadata from MusicBrainz API"""
    try:
        headers = {"User-Agent": "PRISM-Analytics/2.0"}
        params = {
            "query": f"isrc:{isrc}",
            "fmt": "json",
            "inc": "artist-credits+releases",
        }

        response = requests.get(
            "https://musicbrainz.org/ws/2/recording/",
            headers=headers,
            params=params,
            timeout=15,
        )

        if response.status_code != 200:
            return {"error": f"MusicBrainz error: {response.status_code}"}

        data = response.json()

        if data.get("recordings"):
            recording = data["recordings"][0]
            artist_credits = recording.get("artist-credit", [])
            artist_name = ", ".join(
                [credit.get("name", "") for credit in artist_credits]
            )

            # Get first release info
            releases = recording.get("releases", [])
            album_name = ""
            release_date = ""
            if releases:
                album_name = releases[0].get("title", "")
                release_date = releases[0].get("date", "")

            return {
                "title": recording.get("title", ""),
                "artist": artist_name,
                "album": album_name,
                "release_date": release_date,
                "musicbrainz_id": recording.get("id", ""),
                "length": recording.get("length", ""),
            }
        else:
            return {"error": "No recordings found for this ISRC"}

    except Exception as e:
        return {"error": f"MusicBrainz API error: {str(e)}"}


# Keep existing helper functions from Phase 1
def validate_isrc(isrc: str) -> bool:
    """Validate ISRC format"""
    pattern = r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$"
    return bool(re.match(pattern, isrc.upper().strip()))


def clean_isrc(isrc: str) -> str:
    """Clean ISRC format"""
    if not isrc:
        return ""
    return re.sub(r"[-\s]", "", isrc.upper().strip())


def extract_isrcs_from_text(text: str) -> List[str]:
    """Extract ISRCs from text"""
    pattern = r"\b[A-Z]{2}[-\s]?[A-Z0-9]{3}[-\s]?[0-9]{7}\b"
    matches = re.findall(pattern, text.upper())

    isrcs = []
    for match in matches:
        cleaned = clean_isrc(match)
        if validate_isrc(cleaned):
            isrcs.append(cleaned)

    return list(set(isrcs))


def create_csv_export(metadata_list: List[dict]) -> str:
    """Create enhanced CSV from metadata list"""
    output = io.StringIO()

    if not metadata_list:
        return "No data to export"

    # Add header comment
    output.write("# PRISM Analytics - ISRC Metadata Export\n")
    output.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    output.write(f"# Total Records: {len(metadata_list)}\n")
    output.write("#\n")

    # CSV headers
    fieldnames = [
        "ISRC",
        "Title",
        "Artist",
        "Album",
        "Duration_MS",
        "Release_Date",
        "Spotify_ID",
        "Spotify_URL",
        "MusicBrainz_ID",
        "YouTube_ID",
        "YouTube_URL",
        "YouTube_Views",
        "Tempo_BPM",
        "Key",
        "Energy",
        "Danceability",
        "Valence",
        "Popularity",
        "Confidence",
        "Quality_Rating",
        "Sources",
        "Last_Updated",
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for item in metadata_list:
        sources = item.get("sources", [])
        if isinstance(sources, list):
            sources_str = "|".join(str(s) for s in sources) if sources else "None"
        else:
            sources_str = str(sources)

        # Get quality rating
        quality = "Unknown"
        if item.get("confidence_details"):
            quality = item["confidence_details"].get("quality_rating", "Unknown")

        writer.writerow(
            {
                "ISRC": item.get("isrc", ""),
                "Title": item.get("title", ""),
                "Artist": item.get("artist", ""),
                "Album": item.get("album", ""),
                "Duration_MS": item.get("duration_ms", ""),
                "Release_Date": item.get("release_date", ""),
                "Spotify_ID": item.get("spotify_id", ""),
                "Spotify_URL": item.get("spotify_url", ""),
                "MusicBrainz_ID": item.get("musicbrainz_id", ""),
                "YouTube_ID": item.get("youtube_video_id", ""),
                "YouTube_URL": item.get("youtube_url", ""),
                "YouTube_Views": item.get("youtube_views", ""),
                "Tempo_BPM": item.get("tempo", ""),
                "Key": item.get("key", ""),
                "Energy": item.get("energy", ""),
                "Danceability": item.get("danceability", ""),
                "Valence": item.get("valence", ""),
                "Popularity": item.get("popularity", ""),
                "Confidence": item.get("confidence", 0),
                "Quality_Rating": quality,
                "Sources": sources_str,
                "Last_Updated": item.get("last_updated", ""),
            }
        )

    return output.getvalue()


def create_excel_export(metadata_list: List[dict]) -> io.BytesIO:
    """Create Excel export with PRISM branding"""
    if not EXCEL_AVAILABLE:
        raise HTTPException(
            status_code=500, detail="Excel export not available. Install xlsxwriter."
        )

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True})

    # Define formats
    header_format = workbook.add_format(
        {
            "bold": True,
            "bg_color": "#1A1A1A",
            "font_color": "#FFFFFF",
            "border": 1,
            "align": "center",
            "valign": "vcenter",
        }
    )

    title_format = workbook.add_format(
        {"bold": True, "font_size": 16, "font_color": "#1A1A1A", "align": "left"}
    )

    subtitle_format = workbook.add_format(
        {"font_size": 12, "font_color": "#666666", "align": "left"}
    )

    confidence_high = workbook.add_format({"font_color": "#28a745", "bold": True})
    confidence_medium = workbook.add_format({"font_color": "#ffc107", "bold": True})
    confidence_low = workbook.add_format({"font_color": "#E50914", "bold": True})

    # Main metadata sheet
    worksheet = workbook.add_worksheet("Track Metadata")

    # Add PRISM branding header
    worksheet.merge_range(
        0, 0, 0, 20, "PRISM Analytics - Metadata Export", title_format
    )
    worksheet.merge_range(
        1,
        0,
        1,
        20,
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        subtitle_format,
    )
    worksheet.merge_range(
        2, 0, 2, 20, f"Total Records: {len(metadata_list)}", subtitle_format
    )

    # Headers
    headers = [
        "ISRC",
        "Title",
        "Artist",
        "Album",
        "Duration (ms)",
        "Release Date",
        "Spotify ID",
        "Spotify URL",
        "MusicBrainz ID",
        "YouTube ID",
        "YouTube URL",
        "YouTube Views",
        "Tempo (BPM)",
        "Key",
        "Energy",
        "Danceability",
        "Valence",
        "Popularity",
        "Confidence %",
        "Quality",
        "Sources",
        "Last Updated",
    ]

    # Write headers
    for col, header in enumerate(headers):
        worksheet.write(4, col, header, header_format)

    # Set column widths
    column_widths = [
        12,
        30,
        30,
        30,
        12,
        12,
        15,
        40,
        15,
        15,
        40,
        12,
        10,
        8,
        8,
        12,
        8,
        10,
        12,
        10,
        20,
        20,
    ]
    for i, width in enumerate(column_widths):
        if i < len(headers):
            worksheet.set_column(i, i, width)

    # Write data
    for row_idx, item in enumerate(metadata_list):
        row = row_idx + 5

        # Get quality rating
        quality = "Unknown"
        if item.get("confidence_details"):
            quality = item["confidence_details"].get("quality_rating", "Unknown")

        # Write basic data
        worksheet.write(row, 0, str(item.get("isrc", "")))
        worksheet.write(row, 1, str(item.get("title", "")))
        worksheet.write(row, 2, str(item.get("artist", "")))
        worksheet.write(row, 3, str(item.get("album", "")))
        worksheet.write(row, 4, str(item.get("duration_ms", "")))
        worksheet.write(row, 5, str(item.get("release_date", "")))
        worksheet.write(row, 6, str(item.get("spotify_id", "")))

        # Spotify URL as hyperlink
        spotify_url = item.get("spotify_url", "")
        if spotify_url:
            worksheet.write_url(row, 7, spotify_url, string="Open in Spotify")
        else:
            worksheet.write(row, 7, "")

        worksheet.write(row, 8, item.get("musicbrainz_id", ""))
        worksheet.write(row, 9, item.get("youtube_video_id", ""))

        # YouTube URL as hyperlink
        youtube_url = item.get("youtube_url", "")
        if youtube_url:
            worksheet.write_url(row, 10, youtube_url, string="Watch on YouTube")
        else:
            worksheet.write(row, 10, "")

        worksheet.write(row, 11, str(item.get("youtube_views", "")))
        worksheet.write(row, 12, str(item.get("tempo", "")))
        worksheet.write(row, 13, str(item.get("key", "")))
        worksheet.write(row, 14, str(item.get("energy", "")))
        worksheet.write(row, 15, str(item.get("danceability", "")))
        worksheet.write(row, 16, str(item.get("valence", "")))
        worksheet.write(row, 17, str(item.get("popularity", "")))

        # Confidence with color coding
        confidence = item.get("confidence", 0)
        if confidence >= 80:
            worksheet.write(row, 18, confidence, confidence_high)
        elif confidence >= 60:
            worksheet.write(row, 18, confidence, confidence_medium)
        else:
            worksheet.write(row, 18, confidence, confidence_low)

        worksheet.write(row, 19, quality)

        # Sources
        sources = item.get("sources", [])
        if isinstance(sources, list):
            worksheet.write(row, 20, ", ".join(str(s) for s in sources))
        else:
            worksheet.write(row, 20, str(sources))

        worksheet.write(row, 21, str(item.get("last_updated", "")))

    # Add summary sheet
    summary_sheet = workbook.add_worksheet("Summary")

    # Summary statistics
    summary_sheet.merge_range(0, 0, 0, 1, "PRISM Analytics Summary", title_format)

    stats_headers = ["Metric", "Value"]
    for col, header in enumerate(stats_headers):
        summary_sheet.write(2, col, header, header_format)

    # Get database statistics
    db_stats = db.get_analysis_stats()

    # Calculate statistics
    total_tracks = len(metadata_list)
    avg_confidence = sum(item.get("confidence", 0) for item in metadata_list) / max(
        total_tracks, 1
    )
    spotify_found = sum(1 for item in metadata_list if item.get("spotify_id"))
    youtube_found = sum(1 for item in metadata_list if item.get("youtube_video_id"))
    musicbrainz_found = sum(1 for item in metadata_list if item.get("musicbrainz_id"))
    genius_found = sum(
        1 for item in metadata_list if "Genius" in item.get("sources", [])
    )

    stats = [
        ("Total Tracks in Export", str(total_tracks)),
        ("Average Confidence", f"{avg_confidence:.1f}%"),
        (
            "Spotify Coverage",
            f"{spotify_found}/{total_tracks} ({spotify_found / total_tracks * 100:.1f}%)"
            if total_tracks > 0
            else "0/0 (0%)",
        ),
        (
            "YouTube Coverage",
            f"{youtube_found}/{total_tracks} ({youtube_found / total_tracks * 100:.1f}%)"
            if total_tracks > 0
            else "0/0 (0%)",
        ),
        (
            "MusicBrainz Coverage",
            f"{musicbrainz_found}/{total_tracks} ({musicbrainz_found / total_tracks * 100:.1f}%)"
            if total_tracks > 0
            else "0/0 (0%)",
        ),
        (
            "Genius Coverage",
            f"{genius_found}/{total_tracks} ({genius_found / total_tracks * 100:.1f}%)"
            if total_tracks > 0
            else "0/0 (0%)",
        ),
        ("", ""),  # Blank row
        ("Database Statistics", ""),
        ("Total Tracks in DB", str(db_stats.get("total_tracks", 0))),
        ("Avg DB Confidence", f"{db_stats.get('avg_confidence', 0):.1f}%"),
        ("Tracks with Lyrics", str(db_stats.get("tracks_with_lyrics", 0))),
    ]

    for row_idx, (metric, value) in enumerate(stats):
        summary_sheet.write(row_idx + 3, 0, metric)
        summary_sheet.write(row_idx + 3, 1, str(value))

    summary_sheet.set_column(0, 0, 25)
    summary_sheet.set_column(1, 1, 35)

    workbook.close()
    output.seek(0)

    return output


# ============= FASTAPI APP =============
app = FastAPI(
    title="PRISM Analytics - ISRC Metadata Aggregator",
    description="Phase 2: Enhanced with Genius API, Database Storage, and Advanced Confidence Scoring",
    version="2.0.0",
)

# Mount static files
static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def root():
    """Enhanced main application interface with improved UI"""
    html_file = Path("templates/enhanced_index.html")
    if html_file.exists():
        return HTMLResponse(content=html_file.read_text())

    # Fallback to embedded HTML
    html_content = """<!DOCTYPE html>
<html>
<head>
    <title>PRISM Analytics - Phase 2</title>
    <style>
        :root {
            --prism-black: #1A1A1A;
            --precise-red: #E50914;
            --charcoal-gray: #333333;
            --pure-white: #FFFFFF;
            --light-gray: #F8F9FA;
            --medium-gray: #666666;
            --success-green: #28a745;
            --warning-yellow: #ffc107;
            --danger-red: #dc3545;
        }
        
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .header {
            text-align: center;
            margin-bottom: 40px;
            color: var(--pure-white);
        }
        
        .header h1 {
            font-size: 3rem;
            font-weight: 300;
            letter-spacing: 8px;
            margin-bottom: 10px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }
        
        .header p {
            font-size: 1.2rem;
            opacity: 0.9;
        }
        
        .dashboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .card {
            background: var(--pure-white);
            border-radius: 12px;
            padding: 25px;
            box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        
        .card:hover {
            transform: translateY(-5px);
            box-shadow: 0 15px 40px rgba(0,0,0,0.15);
        }
        
        .card h3 {
            color: var(--prism-black);
            margin-bottom: 20px;
            font-size: 1.3rem;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .status-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 10px;
        }
        
        .status-badge {
            padding: 10px;
            border-radius: 8px;
            text-align: center;
            font-size: 0.9rem;
            font-weight: 500;
            transition: all 0.2s ease;
        }
        
        .status-badge.active {
            background: #e6ffe6;
            color: var(--success-green);
            border: 1px solid var(--success-green);
        }
        
        .status-badge.partial {
            background: #fff3cd;
            color: var(--warning-yellow);
            border: 1px solid var(--warning-yellow);
        }
        
        .status-badge.inactive {
            background: #f8f9fa;
            color: var(--medium-gray);
            border: 1px solid var(--medium-gray);
        }
        
        .form-group {
            margin-bottom: 20px;
        }
        
        .form-label {
            display: block;
            margin-bottom: 8px;
            color: var(--prism-black);
            font-weight: 500;
        }
        
        .form-input, .form-select, .form-textarea {
            width: 100%;
            padding: 12px;
            border: 2px solid #e0e0e0;
            border-radius: 8px;
            font-size: 14px;
            transition: all 0.3s ease;
        }
        
        .form-input:focus, .form-select:focus, .form-textarea:focus {
            outline: none;
            border-color: var(--precise-red);
            box-shadow: 0 0 0 3px rgba(229, 9, 20, 0.1);
        }
        
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        
        .btn-primary {
            background: var(--precise-red);
            color: white;
        }
        
        .btn-primary:hover {
            background: #c50812;
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(229, 9, 20, 0.3);
        }
        
        .btn-secondary {
            background: var(--charcoal-gray);
            color: white;
        }
        
        .btn-secondary:hover {
            background: var(--prism-black);
        }
        
        .btn-full {
            width: 100%;
            justify-content: center;
        }
        
        .results {
            margin-top: 30px;
            display: none;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
        }
        
        .spinner {
            display: inline-block;
            width: 50px;
            height: 50px;
            border: 4px solid #f3f3f3;
            border-top: 4px solid var(--precise-red);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }
        
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        
        .confidence-badge {
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
        }
        
        .confidence-excellent {
            background: #d4edda;
            color: #155724;
        }
        
        .confidence-good {
            background: #fff3cd;
            color: #856404;
        }
        
        .confidence-fair {
            background: #ffeaa7;
            color: #fdcb6e;
        }
        
        .confidence-poor {
            background: #f8d7da;
            color: #721c24;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin-top: 20px;
        }
        
        .stat-item {
            background: var(--light-gray);
            padding: 15px;
            border-radius: 8px;
            text-align: center;
        }
        
        .stat-value {
            font-size: 2rem;
            font-weight: bold;
            color: var(--prism-black);
        }
        
        .stat-label {
            color: var(--medium-gray);
            font-size: 0.9rem;
            margin-top: 5px;
        }
        
        .checkbox-group {
            display: flex;
            gap: 20px;
            flex-wrap: wrap;
        }
        
        .checkbox-label {
            display: flex;
            align-items: center;
            gap: 8px;
            cursor: pointer;
        }
        
        .checkbox-label input[type="checkbox"] {
            width: 18px;
            height: 18px;
            cursor: pointer;
        }
        
        .export-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin-top: 15px;
        }
        
        .message {
            padding: 15px;
            border-radius: 8px;
            margin: 15px 0;
            display: none;
        }
        
        .message.success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        
        .message.error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        
        .message.info {
            background: #d1ecf1;
            color: #0c5460;
            border: 1px solid #bee5eb;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>P R I S M</h1>
            <p>Analytics Engine - Phase 2</p>
            <p style="margin-top: 10px; font-size: 0.9rem; opacity: 0.8;">
                Enhanced with Genius API, Database Storage & Advanced Confidence Scoring
            </p>
        </div>
        
        <div class="dashboard">
            <div class="card">
                <h3>📊 API Status</h3>
                <div class="status-grid">
                    <div class="status-badge active">✓ Spotify</div>
                    <div class="status-badge active">✓ YouTube</div>
                    <div class="status-badge active">✓ MusicBrainz</div>
                    <div class="status-badge active">✓ Genius</div>
                    <div class="status-badge inactive">Last.fm</div>
                    <div class="status-badge inactive">Discogs</div>
                </div>
            </div>
            
            <div class="card">
                <h3>💾 Database Statistics</h3>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value" id="total-tracks">0</div>
                        <div class="stat-label">Total Tracks</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="avg-confidence">0%</div>
                        <div class="stat-label">Avg Confidence</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="tracks-lyrics">0</div>
                        <div class="stat-label">With Lyrics</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="dashboard">
            <div class="card">
                <h3>🎵 Single ISRC Analysis</h3>
                <div class="form-group">
                    <label class="form-label">International Standard Recording Code (ISRC)</label>
                    <input type="text" id="single-isrc" class="form-input" 
                           placeholder="e.g., USRC17607839" />
                </div>
                <div class="form-group">
                    <div class="checkbox-group">
                        <label class="checkbox-label">
                            <input type="checkbox" id="include-lyrics" checked>
                            <span>Include Lyrics & Credits</span>
                        </label>
                        <label class="checkbox-label">
                            <input type="checkbox" id="force-refresh">
                            <span>Force Refresh (Skip Cache)</span>
                        </label>
                    </div>
                </div>
                <button class="btn btn-primary btn-full" onclick="analyzeEnhanced()">
                    🔍 Analyze with Enhanced Confidence
                </button>
            </div>
            
            <div class="card">
                <h3>📊 Bulk Export</h3>
                <div class="form-group">
                    <label class="form-label">Multiple ISRCs</label>
                    <textarea id="bulk-isrcs" class="form-textarea" rows="4" 
                              placeholder="Enter ISRCs separated by commas or new lines"></textarea>
                </div>
                <div class="form-group">
                    <label class="form-label">Export Format</label>
                    <select id="export-format" class="form-select">
                        <option value="csv">CSV - Spreadsheet</option>
                        <option value="excel">Excel - With Summary</option>
                        <option value="json">JSON - API Integration</option>
                    </select>
                </div>
                <button class="btn btn-secondary btn-full" onclick="analyzeBulkExport()">
                    📥 Generate Export
                </button>
            </div>
        </div>
        
        <div id="message" class="message"></div>
        <div id="results" class="results"></div>
    </div>
    
    <script>
        // Load database stats on page load
        window.addEventListener('DOMContentLoaded', loadDatabaseStats);
        
        async function loadDatabaseStats() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                
                document.getElementById('total-tracks').textContent = stats.total_tracks || '0';
                document.getElementById('avg-confidence').textContent = Math.round(stats.avg_confidence || 0) + '%';
                document.getElementById('tracks-lyrics').textContent = stats.tracks_with_lyrics || '0';
            } catch (error) {
                console.error('Failed to load stats:', error);
            }
        }
        
        async function analyzeEnhanced() {
            const isrc = document.getElementById('single-isrc').value.trim();
            const includeLyrics = document.getElementById('include-lyrics').checked;
            const forceRefresh = document.getElementById('force-refresh').checked;
            
            if (!isrc) {
                showMessage('Please enter an ISRC', 'error');
                return;
            }
            
            showMessage('Analyzing with enhanced confidence scoring...', 'info');
            showLoading();
            
            try {
                const response = await fetch('/api/analyze-enhanced', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        isrc: isrc,
                        include_lyrics: includeLyrics,
                        include_credits: includeLyrics,
                        force_refresh: forceRefresh
                    })
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    showEnhancedResult(data);
                    showMessage('Analysis complete!', 'success');
                    loadDatabaseStats(); // Refresh stats
                } else {
                    showMessage(data.detail || 'Analysis failed', 'error');
                }
            } catch (error) {
                showMessage('Network error: ' + error.message, 'error');
            } finally {
                hideLoading();
            }
        }
        
        async function analyzeBulkExport() {
            const isrcs = document.getElementById('bulk-isrcs').value.trim();
            const format = document.getElementById('export-format').value;
            
            if (!isrcs) {
                showMessage('Please enter ISRCs', 'error');
                return;
            }
            
            showMessage('Processing bulk export...', 'info');
            showLoading();
            
            try {
                const endpoint = format === 'excel' ? '/api/bulk-excel' : '/api/bulk-csv';
                const response = await fetch(endpoint + '?' + new URLSearchParams({ isrcs: isrcs }));
                
                if (response.ok) {
                    const blob = await response.blob();
                    const extension = format === 'excel' ? 'xlsx' : format;
                    downloadFile(blob, `prism_metadata_enhanced_${new Date().toISOString().slice(0,10)}.${extension}`);
                    showMessage('Export completed successfully!', 'success');
                } else {
                    const error = await response.json();
                    showMessage(error.detail || 'Export failed', 'error');
                }
            } catch (error) {
                showMessage('Network error: ' + error.message, 'error');
            } finally {
                hideLoading();
            }
        }
        
        function showEnhancedResult(data) {
            const results = document.getElementById('results');
            
            const confidence = data.confidence || 0;
            const quality = data.confidence_details?.quality_rating || 'Unknown';
            const qualityClass = quality.toLowerCase().replace(' ', '-');
            
            let scoreBreakdown = '';
            if (data.confidence_details?.score_breakdown) {
                const breakdown = data.confidence_details.score_breakdown;
                scoreBreakdown = `
                    <div class="stat-item">
                        <h4>Confidence Breakdown</h4>
                        <div style="font-size: 0.9rem; text-align: left;">
                            Data Sources: ${breakdown.data_sources.toFixed(0)}%<br>
                            Essential Fields: ${breakdown.essential_fields.toFixed(0)}%<br>
                            Audio Features: ${breakdown.audio_features.toFixed(0)}%<br>
                            External IDs: ${breakdown.external_ids.toFixed(0)}%<br>
                            Popularity: ${breakdown.popularity_metrics.toFixed(0)}%<br>
                            Lyrics: ${breakdown.lyrics_availability.toFixed(0)}%<br>
                            Credits: ${breakdown.credits_completeness.toFixed(0)}%<br>
                            Cross-validation: ${breakdown.cross_validation.toFixed(0)}%
                        </div>
                    </div>
                `;
            }
            
            results.innerHTML = `
                <div class="card">
                    <h3>📈 Enhanced Analysis Results</h3>
                    <div style="margin: 20px 0;">
                        <p><strong>ISRC:</strong> ${data.isrc}</p>
                        <p><strong>Title:</strong> ${data.title || 'Unknown'}</p>
                        <p><strong>Artist:</strong> ${data.artist || 'Unknown'}</p>
                        <p><strong>Album:</strong> ${data.album || 'Unknown'}</p>
                        <p><strong>Confidence Score:</strong> 
                            <span style="font-size: 1.5rem; font-weight: bold; color: ${getConfidenceColor(confidence)}">
                                ${confidence.toFixed(1)}%
                            </span>
                            <span class="confidence-badge confidence-${qualityClass}">${quality}</span>
                        </p>
                        <p><strong>Data Completeness:</strong> ${(data.data_completeness || 0).toFixed(1)}%</p>
                        <p><strong>Sources:</strong> ${(data.sources || []).join(', ') || 'None'}</p>
                        <p><strong>Processing Time:</strong> ${data.processing_time_ms || 0}ms</p>
                    </div>
                    
                    <div class="stats-grid">
                        ${scoreBreakdown}
                    </div>
                    
                    <div class="export-grid">
                        ${data.spotify_url ? `<a href="${data.spotify_url}" target="_blank" class="btn btn-secondary">🎵 Spotify</a>` : ''}
                        ${data.youtube_url ? `<a href="${data.youtube_url}" target="_blank" class="btn btn-secondary">📺 YouTube</a>` : ''}
                        ${data.lyrics_data?.genius_url ? `<a href="${data.lyrics_data.genius_url}" target="_blank" class="btn btn-secondary">📝 Genius</a>` : ''}
                    </div>
                </div>
            `;
            
            results.style.display = 'block';
        }
        
        function getConfidenceColor(confidence) {
            if (confidence >= 80) return '#28a745';
            if (confidence >= 60) return '#ffc107';
            return '#dc3545';
        }
        
        function showMessage(text, type) {
            const message = document.getElementById('message');
            message.textContent = text;
            message.className = 'message ' + type;
            message.style.display = 'block';
            
            if (type === 'success') {
                setTimeout(() => {
                    message.style.display = 'none';
                }, 5000);
            }
        }
        
        function showLoading() {
            const results = document.getElementById('results');
            results.innerHTML = '<div class="loading"><div class="spinner"></div><p>Processing...</p></div>';
            results.style.display = 'block';
        }
        
        function hideLoading() {
            // Loading is replaced by results
        }
        
        function downloadFile(blob, filename) {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            document.body.removeChild(a);
        }
    </script>
</body>
</html>"""
    return HTMLResponse(content=html_content)


@app.post("/api/analyze-enhanced")
async def analyze_enhanced(request: EnhancedISRCRequest):
    """Enhanced single ISRC analysis with Genius and confidence scoring"""
    cleaned_isrc = clean_isrc(request.isrc)

    if not validate_isrc(cleaned_isrc):
        raise HTTPException(status_code=400, detail="Invalid ISRC format")

    metadata = await collect_enhanced_metadata(
        cleaned_isrc,
        include_lyrics=request.include_lyrics,
        force_refresh=request.force_refresh,
    )

    return metadata


@app.get("/api/stats")
async def get_stats():
    """Get database statistics"""
    return db.get_analysis_stats()


@app.get("/api/bulk-csv")
async def bulk_csv(isrcs: str = Query(..., description="ISRCs to process")):
    """Process multiple ISRCs and return CSV"""
    isrc_text = isrcs.replace("\n", ",").replace("\r", ",")
    isrc_list = []

    for isrc in isrc_text.split(","):
        cleaned = clean_isrc(isrc)
        if validate_isrc(cleaned):
            isrc_list.append(cleaned)

    if not isrc_list:
        raise HTTPException(status_code=400, detail="No valid ISRCs found")

    logger.info(f"Processing {len(isrc_list)} ISRCs for CSV export")

    metadata_list = []
    for i, isrc in enumerate(isrc_list):
        logger.info(f"Processing ISRC {i + 1}/{len(isrc_list)}: {isrc}")
        metadata = await collect_enhanced_metadata(isrc, include_lyrics=False)
        metadata_list.append(metadata)

        if i < len(isrc_list) - 1:
            await asyncio.sleep(0.5)

    csv_content = create_csv_export(metadata_list)

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=prism_metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        },
    )


@app.get("/api/bulk-excel")
async def bulk_excel(isrcs: str = Query(..., description="ISRCs to process")):
    """Process multiple ISRCs and return Excel file with summary"""
    if not EXCEL_AVAILABLE:
        raise HTTPException(
            status_code=500, detail="Excel export not available. Install xlsxwriter."
        )

    isrc_text = isrcs.replace("\n", ",").replace("\r", ",")
    isrc_list = []

    for isrc in isrc_text.split(","):
        cleaned = clean_isrc(isrc)
        if validate_isrc(cleaned):
            isrc_list.append(cleaned)

    if not isrc_list:
        raise HTTPException(status_code=400, detail="No valid ISRCs found")

    logger.info(f"Processing {len(isrc_list)} ISRCs for Excel export")

    metadata_list = []
    for i, isrc in enumerate(isrc_list):
        logger.info(f"Processing ISRC {i + 1}/{len(isrc_list)}: {isrc}")
        metadata = await collect_enhanced_metadata(isrc, include_lyrics=False)
        metadata_list.append(metadata)

        if i < len(isrc_list) - 1:
            await asyncio.sleep(0.5)

    excel_file = create_excel_export(metadata_list)

    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=prism_metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        },
    )


@app.get("/api/health")
async def health_check():
    """Enhanced health check endpoint"""
    db_stats = db.get_analysis_stats()

    return {
        "status": "healthy",
        "service": "PRISM Analytics - Phase 2",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "apis_configured": {
            "spotify": bool(
                os.getenv("SPOTIFY_CLIENT_ID") and os.getenv("SPOTIFY_CLIENT_SECRET")
            ),
            "youtube": bool(os.getenv("YOUTUBE_API_KEY")),
            "genius": bool(os.getenv("GENIUS_API_KEY")),
            "musicbrainz": True,
        },
        "features": {
            "database_storage": True,
            "enhanced_confidence": True,
            "lyrics_support": bool(os.getenv("GENIUS_API_KEY")),
            "excel_export": EXCEL_AVAILABLE,
            "caching": True,
        },
        "database": {
            "total_tracks": db_stats.get("total_tracks", 0),
            "tracks_with_lyrics": db_stats.get("tracks_with_lyrics", 0),
            "avg_confidence": db_stats.get("avg_confidence", 0),
        },
    }


if __name__ == "__main__":
    print("🎵 PRISM Analytics - Phase 2 Enhanced")
    print("✨ Features: Genius API, Database Storage, Enhanced Confidence")
    print("🚀 Starting server...")

    uvicorn.run(app, host="127.0.0.1", port=5000, log_level="info")
