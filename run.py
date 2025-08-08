# run.py

#!/usr/bin/env python3
"""
PRISM Analytics - Enhanced Metadata Intelligence System
Main Application Entry Point - Reconciled Version
Incorporates all features from main.py including enhanced Excel export
"""

import os
import sys
import logging
import re
import json
import io
import csv
import time
import sqlite3
import base64
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

import requests
import uvicorn
from fastapi import FastAPI, HTTPException, Query, Response, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# --- Simplified and Direct Imports ---
# These imports are now direct. If a file is missing, Python will raise a standard ImportError.
from config.settings import Config
from src.services.api_clients import APIClientManager
from src.services.metadata_collector_async import AsyncMetadataCollector

# Excel support
try:
    import xlsxwriter
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    print("⚠️ xlsxwriter not installed. Excel export will be limited.")

# Production configuration
IS_PRODUCTION = os.getenv("RENDER") is not None or os.getenv("DATABASE_URL") is not None

if IS_PRODUCTION:
    # Update database URL for SQLAlchemy compatibility
    db_url = os.getenv("DATABASE_URL")
    if db_url and db_url.startswith("postgresql://"):
        os.environ["DATABASE_URL"] = db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables (handled by config.settings)

# ============= DATABASE MANAGER =============
class DatabaseManager:
    """SQLite database manager for metadata storage - Complete Implementation"""
    
    def __init__(self, db_path: str = "data/prism_metadata.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.create_tables()
    
    def create_tables(self):
        """Initialize all database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Main tracks table with all fields
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
                    musicbrainz_recording_id TEXT,
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
                CREATE TABLE IF NOT EXISTS track_lyrics (
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
                CREATE TABLE IF NOT EXISTS track_credits (
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
    
    def get_session(self):
        """Get a database connection (compatibility method)"""
        return self.get_connection().__enter__()
    
    def close_session(self, session):
        """Close a database connection (compatibility method)"""
        try:
            session.close()
        except:
            pass
    
    def save_track_metadata(self, metadata: dict[str, Any]):
        """Save track metadata to database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            sources_json = json.dumps(metadata.get("sources", []))
            
            cursor.execute("""
                INSERT OR REPLACE INTO tracks (
                    isrc, title, artist, album, duration_ms, release_date,
                    spotify_id, spotify_url, musicbrainz_recording_id, youtube_video_id,
                    youtube_url, youtube_views, tempo, key, mode, energy,
                    danceability, valence, popularity, confidence_score,
                    data_completeness, sources, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
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
                metadata.get("last_updated", datetime.now().isoformat())
            ))
            
            conn.commit()
            logger.info(f"💾 Saved metadata for {metadata.get('isrc')} to database")
    
    def save_lyrics(self, isrc: str, lyrics_data: dict[str, Any]):
        """Save lyrics to database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT OR REPLACE INTO track_lyrics (
                    isrc, lyrics_text, genius_song_id, genius_url,
                    language_code, explicit_content, copyright_info,
                    source_confidence
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                isrc,
                lyrics_data.get("lyrics_text"),
                lyrics_data.get("genius_song_id"),
                lyrics_data.get("genius_url"),
                lyrics_data.get("language_code"),
                lyrics_data.get("explicit_content", False),
                json.dumps(lyrics_data.get("copyright_info", {})),
                lyrics_data.get("confidence", 0)
            ))
            
            conn.commit()
            logger.info(f"💾 Saved lyrics for {isrc} to database")
    
    def save_credits(self, isrc: str, credits_list: list[dict[str, Any]]):
        """Save credits to database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Clear existing credits
            cursor.execute("DELETE FROM track_credits WHERE isrc = ?", (isrc,))
            
            # Insert new credits
            for credit in credits_list:
                cursor.execute("""
                    INSERT INTO track_credits (
                        isrc, person_name, credit_type, role_details,
                        source_api, source_confidence
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    isrc,
                    credit.get("person_name"),
                    credit.get("credit_type"),
                    json.dumps(credit.get("role_details", {})),
                    credit.get("source_api"),
                    credit.get("source_confidence", 0)
                ))
            
            conn.commit()
            logger.info(f"💾 Saved {len(credits_list)} credits for {isrc} to database")
    
    def get_track_by_isrc(self, isrc: str) -> dict[str, Any] | None:
        """Get track metadata from database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tracks WHERE isrc = ?", (isrc,))
            row = cursor.fetchone()
            
            if row:
                track = dict(row)
                if track.get("sources"):
                    track["sources"] = json.loads(track["sources"])
                return track
            return None
    
    def get_analysis_stats(self) -> dict[str, Any]:
        """Get comprehensive analysis statistics"""
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
            cursor.execute("SELECT COUNT(*) as count FROM track_lyrics")
            stats["tracks_with_lyrics"] = cursor.fetchone()["count"]
            
            # Platform coverage
            cursor.execute("SELECT COUNT(*) as count FROM tracks WHERE spotify_id IS NOT NULL")
            stats["spotify_coverage"] = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM tracks WHERE youtube_video_id IS NOT NULL")
            stats["youtube_coverage"] = cursor.fetchone()["count"]
            
            cursor.execute("SELECT COUNT(*) as count FROM tracks WHERE musicbrainz_recording_id IS NOT NULL")
            stats["musicbrainz_coverage"] = cursor.fetchone()["count"]
            
            return stats

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1")
                cursor.fetchone()
                return True
        except Exception as e:
            logger.error(f"Database connection test failed: {e}")
            return False
    
    def get_stats(self) -> dict[str, Any]:
        """Get database statistics - alias for get_analysis_stats"""
        return self.get_analysis_stats()
    
# For compatibility with run.py's model imports
class Track:
    pass

class TrackCredit:
    pass

class TrackLyrics:
    pass

# ============= METADATA CACHE WITH DB FALLBACK FROM main.py =============
class MetadataCache:
    """Enhanced cache with database fallback"""
    
    def __init__(self, db_manager: DatabaseManager, cache_dir: str = "data/cache", ttl_hours: int = 24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_hours = ttl_hours
        self.db = db_manager
        logger.info(f"📁 Cache initialized at {self.cache_dir}")
    
    def _get_cache_path(self, isrc: str) -> Path:
        """Get cache file path for ISRC"""
        return self.cache_dir / f"{isrc}.json"
    
    def get(self, isrc: str) -> dict[str, Any] | None:
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
    
    def set(self, isrc: str, data: dict[str, Any]):
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

# ============= GENIUS API INTEGRATION FROM main.py =============
async def get_genius_lyrics(isrc: str, track_title: str | None = None, artist: str | None = None) -> dict[str, Any]:
    """Get lyrics from Genius API - Complete Implementation"""
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
            timeout=10
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
                f"https://api.genius.com/songs/{song_id}",
                headers=headers,
                timeout=10
            )
            
            if song_response.status_code == 200:
                song_data = song_response.json()["response"]["song"]
                
                # Extract credits
                credits = []
                
                # Primary artist
                if song_data.get("primary_artist"):
                    credits.append({
                        "person_name": song_data["primary_artist"]["name"],
                        "credit_type": "primary_artist",
                        "source_api": "genius",
                        "source_confidence": 0.9
                    })
                
                # Featured artists
                for featured_artist in song_data.get("featured_artists", []):
                    credits.append({
                        "person_name": featured_artist["name"],
                        "credit_type": "featured_artist",
                        "source_api": "genius",
                        "source_confidence": 0.9
                    })
                
                # Producer artists
                for producer in song_data.get("producer_artists", []):
                    credits.append({
                        "person_name": producer["name"],
                        "credit_type": "producer",
                        "source_api": "genius",
                        "source_confidence": 0.85
                    })
                
                # Writer artists
                for writer in song_data.get("writer_artists", []):
                    credits.append({
                        "person_name": writer["name"],
                        "credit_type": "writer",
                        "source_api": "genius",
                        "source_confidence": 0.85
                    })
                
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
                    "confidence": 80
                }
        
        return {"error": "No songs found on Genius"}
        
    except Exception as e:
        return {"error": f"Genius API error: {str(e)}"}

# ============= REQUEST MODELS =============
class ISRCAnalysisRequest(BaseModel):
    isrc: str = Field(..., description="International Standard Recording Code")
    include_lyrics: bool = Field(default=True, description="Include lyrics from Genius")
    include_credits: bool = Field(default=True, description="Include credits information")
    force_refresh: bool = Field(default=False, description="Skip cache and force refresh")

class BulkAnalysisRequest(BaseModel):
    isrcs: list[str] = Field(..., description="List of ISRCs to analyze")
    include_lyrics: bool = Field(default=False, description="Include lyrics (slower)")
    export_format: str = Field(default="csv", description="Export format: csv, excel, json")

class ExportRequest(BaseModel):
    isrcs: list[str] = Field(..., description="ISRCs to export")
    format: str = Field(default="csv", description="Export format")
    include_confidence: bool = Field(default=True, description="Include confidence metrics")

# ============= ENHANCED CONFIDENCE SCORER =============
class EnhancedConfidenceScorer:
    """Advanced confidence scoring with multi-factor analysis - Best of Both Versions"""
    
    @staticmethod
    def calculate_score(metadata: dict[str, Any], lyrics_data: dict[str, Any] | None = None) -> dict[str, Any]:
        """Calculate comprehensive confidence score"""
        
        scores = {
            "data_sources": 0.0,
            "essential_fields": 0.0,
            "audio_features": 0.0,
            "external_ids": 0.0,
            "popularity_metrics": 0.0,
            "lyrics_availability": 0.0,
            "credits_completeness": 0.0,
            "cross_validation": 0.0
        }
        
        weights = {
            "data_sources": 0.25,
            "essential_fields": 0.20,
            "audio_features": 0.15,
            "external_ids": 0.10,
            "popularity_metrics": 0.10,
            "lyrics_availability": 0.10,
            "credits_completeness": 0.05,
            "cross_validation": 0.05
        }
        
        # Calculate individual scores
        sources = metadata.get("sources", [])
        
        # Data Sources Score
        if "Spotify" in sources:
            scores["data_sources"] += 35
        if "MusicBrainz" in sources:
            scores["data_sources"] += 35
        if "YouTube" in sources:
            scores["data_sources"] += 30
        
        # Essential Fields Score
        essential = ["title", "artist", "album", "duration_ms", "release_date"]
        present = sum(1 for field in essential if metadata.get(field))
        scores["essential_fields"] = (present / len(essential)) * 100
        
        # Audio Features Score
        audio = ["tempo", "key", "energy", "danceability", "valence"]
        audio_present = sum(1 for field in audio if metadata.get(field) is not None)
        scores["audio_features"] = (audio_present / len(audio)) * 100
        
        # External IDs Score
        ids = ["spotify_id", "musicbrainz_id", "youtube_video_id"]
        ids_present = sum(1 for field in ids if metadata.get(field))
        scores["external_ids"] = (ids_present / len(ids)) * 100
        
        # Popularity Metrics Score
        if metadata.get("popularity"):
            scores["popularity_metrics"] += 50
        if metadata.get("youtube_views"):
            scores["popularity_metrics"] += 50
        
        # Lyrics Availability Score
        if metadata.get("has_lyrics") or lyrics_data:
            scores["lyrics_availability"] = 100
            if lyrics_data and lyrics_data.get("genius_song_id"):
                scores["lyrics_availability"] = 100
        
        # Credits Completeness Score
        credits = []
        if metadata.get("credits"):
            credits = metadata.get("credits", [])
        elif lyrics_data and lyrics_data.get("credits"):
            credits = lyrics_data.get("credits", [])
        
        if credits:
            scores["credits_completeness"] = min(100, len(credits) * 20)
        
        # Cross-validation Score
        if len(sources) >= 2:
            scores["cross_validation"] = 100 if len(sources) >= 3 else 70
        
        # Calculate weighted total
        total_score = sum(scores[key] * weights[key] for key in scores)
        
        # Apply source multiplier
        if len(sources) == 0:
            total_score *= 0.3
        elif len(sources) == 1:
            total_score *= 0.7
        elif len(sources) == 2:
            total_score *= 0.9
        
        total_score = min(100, total_score)
        
        # Determine quality rating
        if total_score >= 90:
            quality = "Excellent"
        elif total_score >= 75:
            quality = "Good"
        elif total_score >= 60:
            quality = "Fair"
        elif total_score >= 40:
            quality = "Poor"
        else:
            quality = "Insufficient"
        
        # Calculate completeness
        all_fields = list(metadata.keys())
        non_empty = sum(1 for field in all_fields 
                        if metadata.get(field) not in [None, "", 0, [], {}])
        completeness = (non_empty / len(all_fields)) * 100 if all_fields else 0
        
        return {
            "confidence_score": round(total_score, 2),
            "data_completeness": round(completeness, 2),
            "quality_rating": quality,
            "score_breakdown": {k: round(v, 2) for k, v in scores.items()},
            "weights_used": weights
        }

# ============= ENHANCED EXPORT SERVICE WITH EXCEL FROM main.py =============
class ExportService:
    """Enhanced export service with comprehensive Excel support from main.py"""
    
    @staticmethod
    def create_csv(metadata_list: list[dict[str, Any]]) -> str:
        """Create CSV export"""
        output = io.StringIO()
        
        # Add metadata header
        output.write("# PRISM Analytics - Metadata Export\n")
        output.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        output.write(f"# Total Records: {len(metadata_list)}\n")
        output.write("#\n")
        
        if not metadata_list:
            return output.getvalue()
        
        fieldnames = [
            "ISRC", "Title", "Artist", "Album", "Duration_MS", "Release_Date",
            "Spotify_ID", "Spotify_URL", "MusicBrainz_ID", "YouTube_ID", "YouTube_URL",
            "YouTube_Views", "Tempo", "Key", "Energy", "Danceability", "Valence",
            "Popularity", "Confidence_Score", "Quality_Rating", "Sources"
        ]
        
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in metadata_list:
            writer.writerow({
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
                "Tempo": item.get("tempo", ""),
                "Key": item.get("key", ""),
                "Energy": item.get("energy", ""),
                "Danceability": item.get("danceability", ""),
                "Valence": item.get("valence", ""),
                "Popularity": item.get("popularity", ""),
                "Confidence_Score": item.get("confidence_score", 0),
                "Quality_Rating": item.get("quality_rating", ""),
                "Sources": "|".join(item.get("sources", []))
            })
        
        return output.getvalue()
    
    @staticmethod
    def create_excel(metadata_list: list[dict[str, Any]], db_stats: dict[str, Any] | None = None) -> io.BytesIO:
        """Create comprehensive Excel export with PRISM branding - Enhanced from main.py"""
        if not EXCEL_AVAILABLE:
            raise ValueError("Excel export not available. Install xlsxwriter.")
        
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Define PRISM brand colors and formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#1A1A1A',
            'font_color': '#FFFFFF',
            'border': 1,
            'align': 'center',
            'valign': 'vcenter'
        })
        
        title_format = workbook.add_format({
            'bold': True,
            'font_size': 16,
            'font_color': '#1A1A1A',
            'align': 'left'
        })
        
        subtitle_format = workbook.add_format({
            'font_size': 12,
            'font_color': '#666666',
            'align': 'left'
        })
        
        high_confidence = workbook.add_format({
            'font_color': '#28a745',
            'bold': True
        })
        
        medium_confidence = workbook.add_format({
            'font_color': '#ffc107',
            'bold': True
        })
        
        low_confidence = workbook.add_format({
            'font_color': '#E50914',
            'bold': True
        })
        
        # Main metadata sheet
        worksheet = workbook.add_worksheet('Track Metadata')
        
        # Add PRISM branding header
        worksheet.merge_range(0, 0, 0, 21, 'PRISM Analytics - Metadata Export', title_format)
        worksheet.merge_range(1, 0, 1, 21, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', subtitle_format)
        worksheet.merge_range(2, 0, 2, 21, f'Total Records: {len(metadata_list)}', subtitle_format)
        
        # Headers
        headers = [
            'ISRC', 'Title', 'Artist', 'Album', 'Duration (ms)', 'Release Date',
            'Spotify ID', 'Spotify URL', 'MusicBrainz ID', 'YouTube ID', 'YouTube URL',
            'YouTube Views', 'Tempo (BPM)', 'Key', 'Mode', 'Energy', 'Danceability',
            'Valence', 'Popularity', 'Confidence %', 'Quality', 'Sources'
        ]
        
        # Write headers
        for col, header in enumerate(headers):
            worksheet.write(4, col, header, header_format)
        
        # Set column widths
        column_widths = [12, 30, 30, 30, 12, 12, 15, 40, 15, 15, 40, 12, 10, 8, 8, 8, 12, 8, 10, 12, 10, 20]
        for i, width in enumerate(column_widths):
            if i < len(headers):
                worksheet.set_column(i, i, width)
        
        # Write data
        for row_idx, item in enumerate(metadata_list):
            row = row_idx + 5
            
            # Get confidence details
            confidence = item.get("confidence_score", item.get("confidence", 0))
            quality = item.get("quality_rating", "")
            if not quality and item.get("confidence_details"):
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
            worksheet.write(row, 14, str(item.get("mode", "")))
            worksheet.write(row, 15, str(item.get("energy", "")))
            worksheet.write(row, 16, str(item.get("danceability", "")))
            worksheet.write(row, 17, str(item.get("valence", "")))
            worksheet.write(row, 18, str(item.get("popularity", "")))
            
            # Confidence with color coding
            if confidence >= 80:
                worksheet.write(row, 19, confidence, high_confidence)
            elif confidence >= 60:
                worksheet.write(row, 19, confidence, medium_confidence)
            else:
                worksheet.write(row, 19, confidence, low_confidence)
            
            worksheet.write(row, 20, quality)
            
            # Sources
            sources = item.get("sources", [])
            if isinstance(sources, list):
                worksheet.write(row, 21, ", ".join(str(s) for s in sources))
            else:
                worksheet.write(row, 21, str(sources))
        
        # Add comprehensive summary sheet
        summary_sheet = workbook.add_worksheet('Summary')
        
        # Summary branding
        summary_sheet.merge_range(0, 0, 0, 1, 'PRISM Analytics Summary', title_format)
        summary_sheet.merge_range(1, 0, 1, 1, f'Analysis Date: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', subtitle_format)
        
        # Summary headers
        summary_headers = ['Metric', 'Value']
        for col, header in enumerate(summary_headers):
            summary_sheet.write(3, col, header, header_format)
        
        # Calculate statistics
        total_tracks = len(metadata_list)
        avg_confidence = sum(item.get("confidence_score", item.get("confidence", 0)) for item in metadata_list) / max(total_tracks, 1)
        spotify_found = sum(1 for item in metadata_list if item.get("spotify_id"))
        youtube_found = sum(1 for item in metadata_list if item.get("youtube_video_id"))
        musicbrainz_found = sum(1 for item in metadata_list if item.get("musicbrainz_id"))
        genius_found = sum(1 for item in metadata_list if "Genius" in item.get("sources", []))
        
        # Quality distribution
        quality_dist = {
            "Excellent": 0, "Good": 0, "Fair": 0, "Poor": 0, "Insufficient": 0
        }
        
        for item in metadata_list:
            quality = item.get("quality_rating", "")
            if not quality and item.get("confidence_details"):
                quality = item["confidence_details"].get("quality_rating", "Unknown")
            if quality in quality_dist:
                quality_dist[quality] += 1
        
        # Write summary statistics
        stats = [
            ('Export Statistics', ''),
            ('Total Tracks', str(total_tracks)),
            ('Average Confidence', f'{avg_confidence:.1f}%'),
            ('', ''),
            ('Platform Coverage', ''),
            ('Spotify Coverage', f'{spotify_found}/{total_tracks} ({spotify_found/total_tracks*100:.1f}%)' if total_tracks > 0 else '0/0 (0%)'),
            ('YouTube Coverage', f'{youtube_found}/{total_tracks} ({youtube_found/total_tracks*100:.1f}%)' if total_tracks > 0 else '0/0 (0%)'),
            ('MusicBrainz Coverage', f'{musicbrainz_found}/{total_tracks} ({musicbrainz_found/total_tracks*100:.1f}%)' if total_tracks > 0 else '0/0 (0%)'),
            ('Genius Coverage', f'{genius_found}/{total_tracks} ({genius_found/total_tracks*100:.1f}%)' if total_tracks > 0 else '0/0 (0%)'),
            ('', ''),
            ('Quality Distribution', ''),
            ('Excellent', f'{quality_dist["Excellent"]} ({quality_dist["Excellent"]/total_tracks*100:.1f}%)' if total_tracks > 0 else '0 (0%)'),
            ('Good', f'{quality_dist["Good"]} ({quality_dist["Good"]/total_tracks*100:.1f}%)' if total_tracks > 0 else '0 (0%)'),
            ('Fair', f'{quality_dist["Fair"]} ({quality_dist["Fair"]/total_tracks*100:.1f}%)' if total_tracks > 0 else '0 (0%)'),
            ('Poor', f'{quality_dist["Poor"]} ({quality_dist["Poor"]/total_tracks*100:.1f}%)' if total_tracks > 0 else '0 (0%)'),
            ('Insufficient', f'{quality_dist["Insufficient"]} ({quality_dist["Insufficient"]/total_tracks*100:.1f}%)' if total_tracks > 0 else '0 (0%)'),
        ]
        
        # Add database statistics if available
        if db_stats:
            stats.extend([
                ('', ''),
                ('Database Statistics', ''),
                ('Total Tracks in DB', str(db_stats.get('total_tracks', 0))),
                ('Avg DB Confidence', f'{db_stats.get("avg_confidence", 0):.1f}%'),
                ('Tracks with Lyrics', str(db_stats.get('tracks_with_lyrics', 0))),
            ])
        
        for row_idx, (metric, value) in enumerate(stats):
            summary_sheet.write(row_idx + 4, 0, metric)
            summary_sheet.write(row_idx + 4, 1, str(value))
        
        summary_sheet.set_column(0, 0, 25)
        summary_sheet.set_column(1, 1, 35)
        
        workbook.close()
        output.seek(0)
        
        return output

# Helper functions for validation
def validate_isrc(isrc: str) -> bool:
    """Validate ISRC format"""
    pattern = r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$'
    return bool(re.match(pattern, isrc.upper().strip()))

def clean_isrc(isrc: str) -> str:
    """Clean ISRC format"""
    if not isrc:
        return ""
    return re.sub(r'[-\s]', '', isrc.upper().strip())

# ============= APPLICATION FACTORY =============
def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    
    app = FastAPI(
        title="PRISM Analytics Engine",
        description="Metadata Intelligence Component - Reconciled Version",
        version="2.1.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc"
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )
    
    # Initialize services
    config = Config()
    api_config = config.get_api_config()
    
    # Initialize managers
    db_manager = DatabaseManager()
    
    # Initialize cache with database
    cache = MetadataCache(db_manager)
    
    # Initialize core components directly
    api_clients = APIClientManager(api_config)
    metadata_collector = AsyncMetadataCollector(api_clients, db_manager)
    confidence_scorer = EnhancedConfidenceScorer()
    export_service = ExportService()
    
    # Store in app state
    app.state.config = config
    app.state.db_manager = db_manager
    app.state.cache = cache
    app.state.api_clients = api_clients
    app.state.metadata_collector = metadata_collector
    app.state.confidence_scorer = confidence_scorer
    app.state.export_service = export_service
    
    return app

# Create application instance
app = create_app()

# Mount static files
static_dir = Path("static")
if static_dir.exists():
    app.mount("/static", StaticFiles(directory="static"), name="static")

# ============= ROUTES =============

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve main interface with fallback to embedded HTML"""
    template_paths = [Path("templates/index.html"), Path("templates/enhanced_index.html")]
    for template_path in template_paths:
        if template_path.exists():
            return HTMLResponse(content=template_path.read_text())
    return HTMLResponse(content="<h1>PRISM UI not found</h1><p>Place index.html in /templates directory.</p>")

@app.get("/api/health")
async def health_check():
    """Comprehensive health check endpoint"""
    db_stats = app.state.db_manager.get_analysis_stats()
    api_status = await app.state.api_clients.validate_clients_async()
    
    return {
        "status": "healthy",
        "service": "PRISM Analytics Engine",
        "version": "2.1.0",
        "timestamp": datetime.now().isoformat(),
        "database": db_stats,
        "apis": api_status,
        "features": {
            "excel_export": EXCEL_AVAILABLE,
            "enhanced_confidence": True,
            "database_storage": True,
            "cache_with_fallback": True,
            "genius_integration": bool(os.getenv("GENIUS_API_KEY"))
        }
    }

@app.get("/api/stats")
async def get_statistics():
    """Get comprehensive database statistics"""
    return app.state.db_manager.get_analysis_stats()

@app.post("/api/analyze-enhanced")
async def analyze_enhanced(request: ISRCAnalysisRequest):
    """Enhanced ISRC analysis with confidence scoring"""
    isrc = clean_isrc(request.isrc)
    if not validate_isrc(isrc):
        raise HTTPException(status_code=400, detail="Invalid ISRC format")
    
    if not request.force_refresh:
        cached_data = app.state.cache.get(isrc)
        if cached_data:
            return cached_data
    
    try:
        result = await app.state.metadata_collector.analyze_isrc_async(
            isrc,
            comprehensive=request.include_lyrics
        )
        
        lyrics_data = None
        if request.include_lyrics and result.get("title") and result.get("artist"):
            lyrics_data = await get_genius_lyrics(isrc, result["title"], result["artist"])
            if "error" not in lyrics_data:
                result["has_lyrics"] = True
                result["lyrics_data"] = lyrics_data
                if "Genius" not in result.get("sources", []):
                    result["sources"].append("Genius")
                
                app.state.db_manager.save_lyrics(isrc, lyrics_data)
                if lyrics_data.get("credits"):
                    app.state.db_manager.save_credits(isrc, lyrics_data["credits"])
        
        confidence_data = app.state.confidence_scorer.calculate_score(result, lyrics_data)
        result.update({
            "confidence": confidence_data["confidence_score"],
            "confidence_score": confidence_data["confidence_score"],
            "data_completeness": confidence_data["data_completeness"],
            "quality_rating": confidence_data["quality_rating"],
            "confidence_details": confidence_data
        })
        
        app.state.cache.set(isrc, result)
        return result
        
    except Exception as e:
        logger.error(f"Analysis failed for {isrc}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bulk-csv")
async def bulk_csv_export(isrcs: str = Query(..., description="Comma-separated ISRCs")):
    """Bulk CSV export"""
    isrc_list = [clean_isrc(isrc) for isrc in isrcs.split(",") if isrc.strip()]
    if not isrc_list:
        raise HTTPException(status_code=400, detail="No valid ISRCs provided")
    
    metadata_list = []
    for isrc in isrc_list:
        if not validate_isrc(isrc): continue
        try:
            cached_data = app.state.cache.get(isrc)
            if cached_data:
                metadata_list.append(cached_data)
            else:
                result = await app.state.metadata_collector.analyze_isrc_async(isrc, comprehensive=False)
                confidence_data = app.state.confidence_scorer.calculate_score(result)
                result.update({
                    "confidence_score": confidence_data["confidence_score"],
                    "quality_rating": confidence_data["quality_rating"]
                })
                metadata_list.append(result)
                app.state.cache.set(isrc, result)
        except Exception as e:
            logger.error(f"Failed to analyze {isrc}: {e}")
    
    csv_content = app.state.export_service.create_csv(metadata_list)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=prism_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

@app.get("/api/bulk-excel")
async def bulk_excel_export(isrcs: str = Query(..., description="Comma-separated ISRCs")):
    """Bulk Excel export with comprehensive summary"""
    if not EXCEL_AVAILABLE:
        raise HTTPException(status_code=500, detail="Excel export not available. Install xlsxwriter.")
    
    isrc_list = [clean_isrc(isrc) for isrc in isrcs.split(",") if isrc.strip()]
    if not isrc_list:
        raise HTTPException(status_code=400, detail="No valid ISRCs provided")
    
    metadata_list = []
    for isrc in isrc_list:
        if not validate_isrc(isrc): continue
        try:
            cached_data = app.state.cache.get(isrc)
            if cached_data:
                metadata_list.append(cached_data)
            else:
                result = await app.state.metadata_collector.analyze_isrc_async(isrc, comprehensive=False)
                confidence_data = app.state.confidence_scorer.calculate_score(result)
                result.update({
                    "confidence_score": confidence_data["confidence_score"],
                    "quality_rating": confidence_data["quality_rating"],
                    "confidence_details": confidence_data
                })
                metadata_list.append(result)
                app.state.cache.set(isrc, result)
        except Exception as e:
            logger.error(f"Failed to analyze {isrc}: {e}")
    
    db_stats = app.state.db_manager.get_analysis_stats()
    excel_file = app.state.export_service.create_excel(metadata_list, db_stats)
    
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=prism_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"}
    )

@app.post("/api/bulk-analyze")
async def bulk_analyze(request: BulkAnalysisRequest):
    """Bulk analysis with progress tracking"""
    results, errors = await app.state.metadata_collector.bulk_analyze_async(
        request.isrcs,
        comprehensive=request.include_lyrics
    )
    
    for result in results:
        confidence_data = app.state.confidence_scorer.calculate_score(result)
        result.update({
            "confidence_score": confidence_data["confidence_score"],
            "quality_rating": confidence_data["quality_rating"],
            "confidence_details": confidence_data
        })
        app.state.cache.set(result["isrc"], result)
    
    return {
        "success": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
        "timestamp": datetime.now().isoformat()
    }

# ============= MAIN ENTRY POINT =============
if __name__ == "__main__":
    print("=" * 60)
    print("🎵 ISRC Metadata Finder")
    print("=" * 60)
    
    config = Config()
    validation = config.validate_required_config()
    
    # Determine environment
    environment = "PRODUCTION" if IS_PRODUCTION else "DEVELOPMENT"
    env_icon = "🚀" if IS_PRODUCTION else "💻"
    
    print(f"\n{env_icon} Environment: {environment}")
    
    # Database info
    if IS_PRODUCTION:
        db_type = "PostgreSQL" if "postgresql" in os.getenv("DATABASE_URL", "") else "Unknown"
        print(f"📊 Database: {db_type} (Production)")
    else:
        print(f"📊 Database: SQLite (Development)")
    
    print("\n📋 Configuration Status:")
    for service, status in validation.items():
        icon = "✅" if "configured" in status else "⚠️"
        print(f"  {icon} {service.capitalize()}: {status}")
    
    # Determine host and port based on environment
    if IS_PRODUCTION:
        # Production settings for Render
        host = "0.0.0.0"
        port = int(os.getenv("PORT", 10000))
        reload = False
        
        # Render provides the public URL
        render_service_name = os.getenv("RENDER_SERVICE_NAME", "your-service")
        public_url = f"https://{render_service_name}.onrender.com"
        
        print("\n🌐 Server Information (Production):")
        print(f"  Internal: http://{host}:{port}")
        print(f"  Public URL: {public_url}")
        print(f"  API Documentation: {public_url}/api/docs")
        print(f"  Health Check: {public_url}/api/health")
    else:
        # Development settings
        host = config.HOST
        port = config.PORT
        reload = True
        
        print("\n🌐 Server Information (Development):")
        print(f"  Web Interface: http://{host}:{port}")
        print(f"  API Documentation: http://{host}:{port}/api/docs")
        print(f"  Health Check: http://{host}:{port}/api/health")
    
    print("\n✨ Enhanced Features:")
    print(f"  • Comprehensive Excel Export: {'✅' if EXCEL_AVAILABLE else '❌ Install xlsxwriter'}")
    print(f"  • Database Storage with Cache Fallback: ✅")
    print(f"  • Genius API Integration: {'✅' if os.getenv('GENIUS_API_KEY') else '⚠️ Set GENIUS_API_KEY'}")
    print(f"  • Enhanced Confidence Scoring: ✅")
    print(f"  • Async Processing: ✅")
    print(f"  • Multi-Source Aggregation: ✅")
    
    # Additional production features
    if IS_PRODUCTION:
        print("\n🔒 Production Features:")
        print(f"  • Auto-scaling: {'✅' if os.getenv('RENDER') else '❌'}")
        print(f"  • SSL/HTTPS: ✅")
        print(f"  • Persistent Storage: {'✅' if 'postgresql' in os.getenv('DATABASE_URL', '') else '❌'}")
        print(f"  • Health Monitoring: ✅")
        
        # Check memory limits for free tier warning
        if os.getenv("RENDER_PLAN", "free") == "free":
            print("\n⚠️  Free Tier Limitations:")
            print("  • 512MB RAM limit")
            print("  • 750 hours/month")
            print("  • Service spins down after 15 min inactivity")
            print("  • Database expires after 90 days")
    
    # API Statistics
    try:
        # Quick check if database is accessible
        db = app.state.db_manager
        if db.test_connection():
            stats = db.get_stats()
            if stats and not stats.get("error"):
                print("\n📊 Database Statistics:")
                print(f"  • Total Tracks: {stats.get('total_tracks', 0)}")
                print(f"  • Average Confidence: {stats.get('avg_confidence', 0):.1f}%")
                print(f"  • Tracks with Lyrics: {stats.get('tracks_with_lyrics', 0)}")
                print(f"  • Spotify Coverage: {stats.get('spotify_coverage', 0)}")
                print(f"  • YouTube Coverage: {stats.get('youtube_coverage', 0)}")
    except Exception as e:
        logger.debug(f"Could not load database stats: {e}")
    
    print("\n🚀 Starting server...")
    print("=" * 60)
    
    # Configure uvicorn based on environment
    if IS_PRODUCTION:
        print(f"Running on port {port} (production mode)")
        print("Note: Render will handle SSL termination and provide HTTPS")
        
        uvicorn.run(
            "run:app",
            host=host,
            port=port,
            reload=False,  # No reload in production
            log_level="info",
            access_log=True,  # Enable access logs in production
            workers=1  # Single worker for free tier, increase for paid plans
        )
    else:
        print(f"Running on http://{host}:{port} (development mode with auto-reload)")
        
        uvicorn.run(
            "run:app",
            host=host,
            port=port,
            reload=True,  # Auto-reload in development
            log_level="info",
            reload_dirs=["src", "templates", "static"],  # Watch these directories
            reload_includes=["*.py", "*.html", "*.css", "*.js"]  # Watch these file types
        )