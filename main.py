#!/usr/bin/env python3
"""
PRISM Analytics - Phase 1 Enhanced Version
ISRC Metadata Aggregator with YouTube, Caching, and Excel Export
"""

import asyncio
import csv
import io
import json
import logging
import os
import re
import sys
import time
import traceback
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response, File, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import requests
import base64

# Excel export support
try:
    import xlsxwriter
    from xlsxwriter import Workbook
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    Workbook = None  # Type placeholder
    print("⚠️ xlsxwriter not installed. Excel export will be limited.")

# Load environment variables
def load_environment():
    """Load environment variables with multiple fallback methods"""
    try:
        from dotenv import load_dotenv
        env_paths = ['.env', Path('.env'), Path(__file__).parent / '.env', Path.cwd() / '.env']
        for env_path in env_paths:
            if Path(env_path).exists():
                load_dotenv(env_path, override=True)
                break
    except ImportError:
        pass
    
    # Manual .env parsing as fallback
    env_file = Path('.env')
    if env_file.exists():
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        value = value.strip().strip('"').strip("'")
                        os.environ[key.strip()] = value
        except Exception:
            pass

load_environment()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ============= CACHE IMPLEMENTATION =============
class MetadataCache:
    """Simple file-based cache for API responses"""
    
    def __init__(self, cache_dir="data/cache", ttl_hours=24):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_hours = ttl_hours
        logger.info(f"📁 Cache initialized at {self.cache_dir}")
    
    def _get_cache_path(self, isrc: str) -> Path:
        """Get cache file path for ISRC"""
        return self.cache_dir / f"{isrc}.json"
    
    def get(self, isrc: str) -> Optional[dict]:
        """Get cached data if fresh"""
        cache_file = self._get_cache_path(isrc)
        
        if cache_file.exists():
            try:
                # Check age
                age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
                
                if age_hours < self.ttl_hours:
                    with open(cache_file, 'r') as f:
                        data = json.load(f)
                    logger.info(f"✅ Cache hit for {isrc} (age: {age_hours:.1f}h)")
                    return data
                else:
                    logger.info(f"⏰ Cache expired for {isrc} (age: {age_hours:.1f}h)")
            except Exception as e:
                logger.error(f"Cache read error: {e}")
        
        return None
    
    def set(self, isrc: str, data: dict):
        """Store data in cache"""
        cache_file = self._get_cache_path(isrc)
        
        try:
            with open(cache_file, 'w') as f:
                json.dump(data, f, indent=2)
            logger.info(f"💾 Cached data for {isrc}")
        except Exception as e:
            logger.error(f"Cache write error: {e}")
    
    def clear(self, isrc: Optional[str] = None):
        """Clear cache for specific ISRC or all"""
        if isrc:
            cache_file = self._get_cache_path(isrc)
            if cache_file.exists():
                cache_file.unlink()
                logger.info(f"🗑️ Cleared cache for {isrc}")
        else:
            for cache_file in self.cache_dir.glob("*.json"):
                cache_file.unlink()
            logger.info("🗑️ Cleared all cache")

# Initialize cache
cache = MetadataCache()

# ============= REQUEST MODELS =============
class ISRCRequest(BaseModel):
    isrc: str

class BulkISRCRequest(BaseModel):
    isrcs: List[str]
    export_format: str = "csv"  # csv, json, excel

# ============= VALIDATION =============
def validate_isrc(isrc: str) -> bool:
    """Validate ISRC format"""
    pattern = r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$'
    return bool(re.match(pattern, isrc.upper().strip()))

def clean_isrc(isrc: str) -> str:
    """Clean ISRC format"""
    if not isrc:
        return ""
    return re.sub(r'[-\s]', '', isrc.upper().strip())

def extract_isrcs_from_text(text: str) -> List[str]:
    """Extract ISRCs from text"""
    pattern = r'\b[A-Z]{2}[-\s]?[A-Z0-9]{3}[-\s]?[0-9]{7}\b'
    matches = re.findall(pattern, text.upper())
    
    isrcs = []
    for match in matches:
        cleaned = clean_isrc(match)
        if validate_isrc(cleaned):
            isrcs.append(cleaned)
    
    return list(set(isrcs))

# ============= SPOTIFY API =============
async def get_spotify_metadata(isrc: str) -> dict:
    """Get metadata from Spotify API"""
    try:
        client_id = os.getenv('SPOTIFY_CLIENT_ID')
        client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
        
        if not client_id or not client_secret:
            return {'error': 'Spotify credentials not configured'}
        
        # Get access token
        auth_string = f"{client_id}:{client_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        token_headers = {
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        token_data = {'grant_type': 'client_credentials'}
        
        token_response = requests.post(
            'https://accounts.spotify.com/api/token', 
            headers=token_headers, 
            data=token_data,
            timeout=10
        )
        
        if token_response.status_code != 200:
            return {'error': f'Spotify auth failed: {token_response.status_code}'}
        
        token_info = token_response.json()
        access_token = token_info['access_token']
        
        # Search for ISRC
        search_headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        search_params = {
            'q': f'isrc:{isrc}',
            'type': 'track',
            'limit': 1
        }
        
        search_response = requests.get(
            'https://api.spotify.com/v1/search',
            headers=search_headers,
            params=search_params,
            timeout=10
        )
        
        if search_response.status_code != 200:
            return {'error': f'Spotify search failed: {search_response.status_code}'}
        
        search_data = search_response.json()
        
        if search_data.get('tracks', {}).get('items'):
            track = search_data['tracks']['items'][0]
            
            # Get audio features if track ID available
            audio_features = {}
            if track.get('id'):
                features_response = requests.get(
                    f'https://api.spotify.com/v1/audio-features/{track["id"]}',
                    headers=search_headers,
                    timeout=10
                )
                if features_response.status_code == 200:
                    audio_features = features_response.json()
            
            return {
                'title': track.get('name', ''),
                'artist': ', '.join([a['name'] for a in track.get('artists', [])]),
                'album': track.get('album', {}).get('name', ''),
                'duration_ms': track.get('duration_ms', ''),
                'release_date': track.get('album', {}).get('release_date', ''),
                'spotify_id': track.get('id', ''),
                'spotify_url': track.get('external_urls', {}).get('spotify', ''),
                'popularity': track.get('popularity', ''),
                'tempo': audio_features.get('tempo', ''),
                'key': audio_features.get('key', ''),
                'mode': audio_features.get('mode', ''),
                'energy': audio_features.get('energy', ''),
                'danceability': audio_features.get('danceability', ''),
                'valence': audio_features.get('valence', ''),
                'confidence': 85
            }
        else:
            return {'error': 'No tracks found for this ISRC'}
            
    except Exception as e:
        return {'error': f'Spotify API error: {str(e)}'}

# ============= YOUTUBE API =============
async def get_youtube_metadata(isrc: str, track_title: Optional[str] = None, artist: Optional[str] = None) -> dict:
    """Get metadata from YouTube API"""
    try:
        api_key = os.getenv('YOUTUBE_API_KEY')
        
        if not api_key:
            return {'error': 'YouTube API not configured'}
        
        # Build search query
        if track_title and artist:
            search_query = f'"{artist}" "{track_title}" "{isrc}"'
        else:
            search_query = f'"{isrc}"'
        
        # Search for videos
        search_params = {
            'part': 'snippet',
            'q': search_query,
            'type': 'video',
            'videoCategoryId': '10',  # Music category
            'maxResults': 5,
            'key': api_key
        }
        
        search_response = requests.get(
            'https://www.googleapis.com/youtube/v3/search',
            params=search_params,
            timeout=10
        )
        
        if search_response.status_code != 200:
            return {'error': f'YouTube search failed: {search_response.status_code}'}
        
        search_data = search_response.json()
        
        if search_data.get('items'):
            # Find best match (prefer official channels)
            best_match = None
            for item in search_data['items']:
                snippet = item.get('snippet', {})
                
                # Check if ISRC is in description
                description = snippet.get('description', '').upper()
                if isrc in description:
                    best_match = item
                    break
                
                # Otherwise take first result
                if not best_match:
                    best_match = item
            
            if best_match:
                snippet = best_match['snippet']
                video_id = best_match['id']['videoId']
                
                # Get video statistics
                stats_params = {
                    'part': 'statistics,contentDetails',
                    'id': video_id,
                    'key': api_key
                }
                
                stats_response = requests.get(
                    'https://www.googleapis.com/youtube/v3/videos',
                    params=stats_params,
                    timeout=10
                )
                
                stats_data = {}
                if stats_response.status_code == 200:
                    stats_result = stats_response.json()
                    if stats_result.get('items'):
                        stats_data = stats_result['items'][0].get('statistics', {})
                
                return {
                    'youtube_video_id': video_id,
                    'youtube_url': f'https://www.youtube.com/watch?v={video_id}',
                    'youtube_title': snippet.get('title', ''),
                    'youtube_channel': snippet.get('channelTitle', ''),
                    'youtube_channel_id': snippet.get('channelId', ''),
                    'youtube_published': snippet.get('publishedAt', ''),
                    'youtube_views': stats_data.get('viewCount', ''),
                    'youtube_likes': stats_data.get('likeCount', ''),
                    'youtube_comments': stats_data.get('commentCount', ''),
                    'confidence': 70
                }
        
        return {'error': 'No YouTube videos found for this ISRC'}
        
    except Exception as e:
        return {'error': f'YouTube API error: {str(e)}'}

# ============= MUSICBRAINZ API =============
async def get_musicbrainz_metadata(isrc: str) -> dict:
    """Get metadata from MusicBrainz API"""
    try:
        headers = {'User-Agent': 'PRISM-Analytics/1.0'}
        params = {
            'query': f'isrc:{isrc}',
            'fmt': 'json',
            'inc': 'artist-credits+releases'
        }
        
        response = requests.get(
            'https://musicbrainz.org/ws/2/recording/',
            headers=headers,
            params=params,
            timeout=15
        )
        
        if response.status_code != 200:
            return {'error': f'MusicBrainz error: {response.status_code}'}
        
        data = response.json()
        
        if data.get('recordings'):
            recording = data['recordings'][0]
            artist_credits = recording.get('artist-credit', [])
            artist_name = ', '.join([credit.get('name', '') for credit in artist_credits])
            
            # Get first release info
            releases = recording.get('releases', [])
            album_name = ''
            release_date = ''
            if releases:
                album_name = releases[0].get('title', '')
                release_date = releases[0].get('date', '')
            
            return {
                'title': recording.get('title', ''),
                'artist': artist_name,
                'album': album_name,
                'release_date': release_date,
                'musicbrainz_id': recording.get('id', ''),
                'length': recording.get('length', ''),
                'confidence': 75
            }
        else:
            return {'error': 'No recordings found for this ISRC'}
            
    except Exception as e:
        return {'error': f'MusicBrainz API error: {str(e)}'}

# ============= CONFIDENCE SCORING =============
def calculate_confidence_score(metadata: dict) -> float:
    """Calculate confidence score based on data completeness"""
    scores = {
        'spotify_data': 30 if metadata.get('spotify_id') else 0,
        'musicbrainz_data': 25 if metadata.get('musicbrainz_id') else 0,
        'youtube_data': 20 if metadata.get('youtube_video_id') else 0,
        'title_present': 10 if metadata.get('title') else 0,
        'artist_present': 10 if metadata.get('artist') else 0,
        'album_present': 5 if metadata.get('album') else 0,
    }
    
    confidence = sum(scores.values())
    
    # Bonus for multiple sources agreeing
    sources_found = sum([
        1 if metadata.get('spotify_id') else 0,
        1 if metadata.get('musicbrainz_id') else 0,
        1 if metadata.get('youtube_video_id') else 0
    ])
    
    if sources_found >= 2:
        confidence = min(100, confidence + 10)
    
    return confidence

# ============= MAIN COLLECTION FUNCTION =============
async def collect_metadata(isrc: str, use_cache: bool = True) -> dict:
    """Collect metadata from all available sources"""
    
    # Check cache first
    if use_cache:
        cached_data = cache.get(isrc)
        if cached_data:
            return cached_data
    
    result = {
        'isrc': isrc,
        'title': '',
        'artist': '',
        'album': '',
        'duration_ms': '',
        'release_date': '',
        'spotify_id': '',
        'spotify_url': '',
        'musicbrainz_id': '',
        'youtube_video_id': '',
        'youtube_url': '',
        'youtube_views': '',
        'tempo': '',
        'key': '',
        'energy': '',
        'danceability': '',
        'valence': '',
        'popularity': '',
        'confidence': 0,
        'sources': [],
        'last_updated': datetime.now().isoformat()
    }
    
    # Try Spotify first
    logger.info(f"🎵 Checking Spotify for ISRC: {isrc}")
    spotify_data = await get_spotify_metadata(isrc)
    
    if 'error' not in spotify_data:
        result.update(spotify_data)
        result['sources'].append('Spotify')
        logger.info(f"✅ Found on Spotify: {result['title']} by {result['artist']}")
    
    # Try MusicBrainz
    logger.info(f"🎼 Checking MusicBrainz for ISRC: {isrc}")
    mb_data = await get_musicbrainz_metadata(isrc)
    
    if 'error' not in mb_data:
        # Update empty fields from MusicBrainz
        for key in ['title', 'artist', 'album', 'release_date']:
            if not result[key] and mb_data.get(key):
                result[key] = mb_data[key]
        result['musicbrainz_id'] = mb_data.get('musicbrainz_id', '')
        result['sources'].append('MusicBrainz')
        logger.info(f"✅ Found on MusicBrainz: {mb_data.get('title', 'Unknown')}")
    
    # Try YouTube if we have title/artist
    if result['title'] or result['artist']:
        logger.info(f"📺 Checking YouTube for ISRC: {isrc}")
        youtube_data = await get_youtube_metadata(
            isrc, 
            result.get('title') or None, 
            result.get('artist') or None
        )
        
        if 'error' not in youtube_data:
            result.update({k: v for k, v in youtube_data.items() if k != 'confidence'})
            result['sources'].append('YouTube')
            logger.info(f"✅ Found on YouTube: {youtube_data.get('youtube_title', 'Unknown')}")
    
    # Calculate final confidence score
    result['confidence'] = calculate_confidence_score(result)
    
    # Determine overall status
    if not result['sources']:
        logger.warning(f"❌ No metadata found for ISRC: {isrc}")
        result['title'] = 'NOT FOUND'
        result['artist'] = 'NOT FOUND'
        result['sources'] = []  # Keep as empty list
    
    # Cache the result
    if use_cache and result['sources']:  # Only cache if we found data
        cache.set(isrc, result)
    
    return result

# ============= EXCEL EXPORT =============
def create_excel_export(metadata_list: List[dict]) -> io.BytesIO:
    """Create Excel export with PRISM branding
    
    Note: Using numeric cell references instead of A1 notation for better type checking compatibility
    """
    if not EXCEL_AVAILABLE:
        raise HTTPException(status_code=500, detail="Excel export not available. Install xlsxwriter.")
    
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    
    # Define formats
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
    
    confidence_high = workbook.add_format({'font_color': '#28a745', 'bold': True})
    confidence_medium = workbook.add_format({'font_color': '#ffc107', 'bold': True})
    confidence_low = workbook.add_format({'font_color': '#E50914', 'bold': True})
    
    # Main metadata sheet
    worksheet = workbook.add_worksheet('Track Metadata')
    
    # Add PRISM branding header (using numeric format for better type checking)
    worksheet.merge_range(0, 0, 0, 17, 'PRISM Analytics - Metadata Export', title_format)
    worksheet.merge_range(1, 0, 1, 17, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', subtitle_format)
    worksheet.merge_range(2, 0, 2, 17, f'Total Records: {len(metadata_list)}', subtitle_format)
    
    # Headers
    headers = [
        'ISRC', 'Title', 'Artist', 'Album', 'Duration (ms)', 
        'Release Date', 'Spotify ID', 'Spotify URL', 'MusicBrainz ID',
        'YouTube ID', 'YouTube URL', 'YouTube Views',
        'Tempo (BPM)', 'Key', 'Energy', 'Danceability', 'Valence',
        'Popularity', 'Confidence %', 'Sources', 'Last Updated'
    ]
    
    # Write headers
    for col, header in enumerate(headers):
        worksheet.write(4, col, header, header_format)
    
    # Set column widths (columns 0-20)
    column_widths = [12, 30, 30, 30, 12, 12, 15, 40, 15, 15, 40, 12, 10, 8, 8, 12, 8, 10, 12, 20, 20]
    for i, width in enumerate(column_widths):
        if i < len(headers):  # Only set width for columns that have headers
            worksheet.set_column(i, i, width)
    
    # Write data
    for row_idx, item in enumerate(metadata_list):
        row = row_idx + 5  # Start after headers
        
        # Write basic data
        worksheet.write(row, 0, str(item.get('isrc', '')))
        worksheet.write(row, 1, str(item.get('title', '')))
        worksheet.write(row, 2, str(item.get('artist', '')))
        worksheet.write(row, 3, str(item.get('album', '')))
        worksheet.write(row, 4, str(item.get('duration_ms', '')))
        worksheet.write(row, 5, str(item.get('release_date', '')))
        worksheet.write(row, 6, str(item.get('spotify_id', '')))
        
        # Spotify URL as hyperlink
        spotify_url = item.get('spotify_url', '')
        if spotify_url:
            worksheet.write_url(row, 7, spotify_url, string='Open in Spotify')
        else:
            worksheet.write(row, 7, '')
        
        worksheet.write(row, 8, item.get('musicbrainz_id', ''))
        worksheet.write(row, 9, item.get('youtube_video_id', ''))
        
        # YouTube URL as hyperlink
        youtube_url = item.get('youtube_url', '')
        if youtube_url:
            worksheet.write_url(row, 10, youtube_url, string='Watch on YouTube')
        else:
            worksheet.write(row, 10, '')
        
        worksheet.write(row, 11, str(item.get('youtube_views', '')))
        worksheet.write(row, 12, str(item.get('tempo', '')))
        worksheet.write(row, 13, str(item.get('key', '')))
        worksheet.write(row, 14, str(item.get('energy', '')))
        worksheet.write(row, 15, str(item.get('danceability', '')))
        worksheet.write(row, 16, str(item.get('valence', '')))
        worksheet.write(row, 17, str(item.get('popularity', '')))
        
        # Confidence with color coding
        confidence = item.get('confidence', 0)
        if confidence >= 80:
            worksheet.write(row, 18, confidence, confidence_high)
        elif confidence >= 60:
            worksheet.write(row, 18, confidence, confidence_medium)
        else:
            worksheet.write(row, 18, confidence, confidence_low)
        
        # Sources
        sources = item.get('sources', [])
        if isinstance(sources, list):
            worksheet.write(row, 19, ', '.join(str(s) for s in sources))
        else:
            worksheet.write(row, 19, str(sources))
        
        worksheet.write(row, 20, str(item.get('last_updated', '')))
    
    # Add summary sheet
    summary_sheet = workbook.add_worksheet('Summary')
    
    # Summary statistics (using numeric format)
    summary_sheet.merge_range(0, 0, 0, 1, 'PRISM Analytics Summary', title_format)
    
    stats_headers = ['Metric', 'Value']
    for col, header in enumerate(stats_headers):
        summary_sheet.write(2, col, header, header_format)
    
    # Calculate statistics
    total_tracks = len(metadata_list)
    avg_confidence = sum(item.get('confidence', 0) for item in metadata_list) / max(total_tracks, 1)
    spotify_found = sum(1 for item in metadata_list if item.get('spotify_id'))
    youtube_found = sum(1 for item in metadata_list if item.get('youtube_video_id'))
    musicbrainz_found = sum(1 for item in metadata_list if item.get('musicbrainz_id'))
    
    stats = [
        ('Total Tracks', str(total_tracks)),
        ('Average Confidence', f'{avg_confidence:.1f}%'),
        ('Spotify Coverage', f'{spotify_found}/{total_tracks} ({spotify_found/total_tracks*100:.1f}%)' if total_tracks > 0 else '0/0 (0%)'),
        ('YouTube Coverage', f'{youtube_found}/{total_tracks} ({youtube_found/total_tracks*100:.1f}%)' if total_tracks > 0 else '0/0 (0%)'),
        ('MusicBrainz Coverage', f'{musicbrainz_found}/{total_tracks} ({musicbrainz_found/total_tracks*100:.1f}%)' if total_tracks > 0 else '0/0 (0%)'),
    ]
    
    for row_idx, (metric, value) in enumerate(stats):
        summary_sheet.write(row_idx + 3, 0, metric)
        summary_sheet.write(row_idx + 3, 1, str(value))
    
    summary_sheet.set_column(0, 0, 20)
    summary_sheet.set_column(1, 1, 30)
    
    workbook.close()
    output.seek(0)
    
    return output

# ============= CSV EXPORT (ENHANCED) =============
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
        'ISRC', 'Title', 'Artist', 'Album', 'Duration_MS', 
        'Release_Date', 'Spotify_ID', 'Spotify_URL', 'MusicBrainz_ID',
        'YouTube_ID', 'YouTube_URL', 'YouTube_Views',
        'Tempo_BPM', 'Key', 'Energy', 'Danceability', 'Valence',
        'Popularity', 'Confidence', 'Sources', 'Last_Updated'
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for item in metadata_list:
        sources = item.get('sources', [])
        if isinstance(sources, list):
            sources_str = '|'.join(str(s) for s in sources) if sources else 'None'
        else:
            sources_str = str(sources)
        
        writer.writerow({
            'ISRC': item.get('isrc', ''),
            'Title': item.get('title', ''),
            'Artist': item.get('artist', ''),
            'Album': item.get('album', ''),
            'Duration_MS': item.get('duration_ms', ''),
            'Release_Date': item.get('release_date', ''),
            'Spotify_ID': item.get('spotify_id', ''),
            'Spotify_URL': item.get('spotify_url', ''),
            'MusicBrainz_ID': item.get('musicbrainz_id', ''),
            'YouTube_ID': item.get('youtube_video_id', ''),
            'YouTube_URL': item.get('youtube_url', ''),
            'YouTube_Views': item.get('youtube_views', ''),
            'Tempo_BPM': item.get('tempo', ''),
            'Key': item.get('key', ''),
            'Energy': item.get('energy', ''),
            'Danceability': item.get('danceability', ''),
            'Valence': item.get('valence', ''),
            'Popularity': item.get('popularity', ''),
            'Confidence': item.get('confidence', 0),
            'Sources': sources_str,
            'Last_Updated': item.get('last_updated', '')
        })
    
    return output.getvalue()

# ============= FASTAPI APP =============
app = FastAPI(
    title="PRISM Analytics - ISRC Metadata Aggregator",
    description="Transform ISRC codes into comprehensive metadata exports",
    version="1.1.0"
)

@app.get("/", response_class=HTMLResponse)
async def root():
    """Enhanced main application interface"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>PRISM Analytics - ISRC Metadata Tool</title>
        <style>
            body { 
                font-family: 'Segoe UI', system-ui, sans-serif; 
                max-width: 1200px; 
                margin: 0 auto; 
                padding: 20px;
                background: #f8f9fa;
            }
            .header {
                text-align: center;
                margin-bottom: 30px;
                padding: 20px;
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .logo { 
                font-size: 2rem; 
                font-weight: 300;
                letter-spacing: 4px;
                color: #1A1A1A;
                margin-bottom: 10px;
            }
            .tagline {
                color: #666;
                font-size: 1.1rem;
            }
            .status-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                gap: 15px;
                margin-bottom: 30px;
            }
            .status-card {
                background: white;
                padding: 15px;
                border-radius: 8px;
                text-align: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .status-card.active { border-left: 4px solid #28a745; }
            .status-card.inactive { border-left: 4px solid #ffc107; }
            .form-section {
                background: white;
                padding: 25px;
                margin-bottom: 20px;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .form-group { margin-bottom: 20px; }
            .form-group h3 { 
                margin: 0 0 15px 0; 
                color: #1A1A1A;
                font-weight: 500;
            }
            input, textarea, button, select { 
                width: 100%; 
                padding: 12px; 
                margin: 5px 0;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-family: inherit;
            }
            button { 
                background: #E50914; 
                color: white; 
                border: none; 
                cursor: pointer;
                font-weight: 500;
                transition: background 0.2s;
            }
            button:hover { background: #c50812; }
            .results { 
                margin-top: 20px; 
                padding: 20px; 
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            .success { 
                background: #e6ffe6; 
                border-left: 4px solid #28a745; 
                padding: 15px;
                margin: 10px 0;
            }
            .error { 
                background: #ffe6e6; 
                border-left: 4px solid #E50914; 
                padding: 15px;
                margin: 10px 0;
            }
            .loading { 
                color: #666; 
                text-align: center;
                padding: 20px;
            }
            .track-info {
                background: #f8f9fa;
                padding: 15px;
                border-radius: 4px;
                margin: 10px 0;
            }
            .confidence-high { color: #28a745; font-weight: bold; }
            .confidence-medium { color: #ffc107; font-weight: bold; }
            .confidence-low { color: #E50914; font-weight: bold; }
            .export-options {
                display: flex;
                gap: 10px;
                margin-top: 15px;
            }
            .export-btn {
                flex: 1;
                padding: 10px;
                background: #333;
                color: white;
                border: none;
                border-radius: 4px;
                cursor: pointer;
            }
            .export-btn:hover { background: #1A1A1A; }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">P R I S M</div>
            <div class="tagline">Analytics Engine</div>
            <p>Transform Music Data into Actionable Insights</p>
        </div>

        <div class="status-grid">
            <div class="status-card active">
                <strong>Spotify</strong><br>
                <span style="color: #28a745;">✓ Connected</span>
            </div>
            <div class="status-card active">
                <strong>YouTube</strong><br>
                <span style="color: #28a745;">✓ Connected</span>
            </div>
            <div class="status-card active">
                <strong>MusicBrainz</strong><br>
                <span style="color: #28a745;">✓ Available</span>
            </div>
            <div class="status-card inactive">
                <strong>Genius</strong><br>
                <span style="color: #ffc107;">Coming Soon</span>
            </div>
            <div class="status-card inactive">
                <strong>Last.fm</strong><br>
                <span style="color: #ffc107;">Coming Soon</span>
            </div>
            <div class="status-card inactive">
                <strong>Discogs</strong><br>
                <span style="color: #ffc107;">Coming Soon</span>
            </div>
        </div>

        <div class="form-section">
            <div class="form-group">
                <h3>🎵 Single ISRC Analysis</h3>
                <input type="text" id="single-isrc" placeholder="Enter ISRC (e.g., USRC17607839)" />
                <button onclick="analyzeSingle()">Analyze Single ISRC</button>
            </div>
        </div>

        <div class="form-section">
            <div class="form-group">
                <h3>📊 Bulk ISRC Export</h3>
                <textarea id="bulk-isrcs" rows="4" placeholder="Enter multiple ISRCs separated by commas or new lines&#10;Example:&#10;USRC17607839&#10;GBUM71505078&#10;USUM71703861"></textarea>
                <label for="export-format">Export Format:</label>
                <select id="export-format">
                    <option value="csv">CSV - Spreadsheet Compatible</option>
                    <option value="excel">Excel - With Formatting & Charts</option>
                    <option value="json">JSON - API Integration</option>
                </select>
                <button onclick="analyzeBulkExport()">Generate Export</button>
            </div>
        </div>

        <div class="form-section">
            <div class="form-group">
                <h3>📄 File Upload</h3>
                <input type="file" id="file-upload" accept=".txt,.csv" />
                <button onclick="analyzeFileExport()">Upload File & Generate Export</button>
                <small style="color: #666; display: block; margin-top: 5px;">
                    Supported formats: .txt, .csv (will extract ISRCs automatically)
                </small>
            </div>
        </div>

        <div class="form-section">
            <div class="form-group">
                <h3>🗑️ Cache Management</h3>
                <button onclick="clearCache()" style="background: #666;">Clear All Cached Data</button>
                <small style="color: #666; display: block; margin-top: 5px;">
                    Cached data expires after 24 hours. Clear to force fresh API calls.
                </small>
            </div>
        </div>

        <div id="results" class="results" style="display: none;"></div>

        <script>
            async function analyzeSingle() {
                const isrc = document.getElementById('single-isrc').value.trim();
                if (!isrc) {
                    alert('Please enter an ISRC');
                    return;
                }
                
                showLoading('🔍 Analyzing ISRC across multiple sources...');
                
                try {
                    const response = await fetch('/api/analyze-single', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ isrc: isrc })
                    });
                    
                    const data = await response.json();
                    
                    if (response.ok) {
                        showSingleResult(data);
                    } else {
                        showError(data.detail || 'Analysis failed');
                    }
                } catch (error) {
                    showError('Network error: ' + error.message);
                }
            }
            
            async function analyzeBulkExport() {
                const isrcs = document.getElementById('bulk-isrcs').value.trim();
                const format = document.getElementById('export-format').value;
                
                if (!isrcs) {
                    alert('Please enter ISRCs');
                    return;
                }
                
                showLoading('📊 Processing ISRCs and generating ' + format.toUpperCase() + ' export...');
                
                try {
                    const endpoint = format === 'excel' ? '/api/bulk-excel' : '/api/bulk-csv';
                    const response = await fetch(endpoint + '?' + new URLSearchParams({ isrcs: isrcs }));
                    
                    if (response.ok) {
                        const blob = await response.blob();
                        const extension = format === 'excel' ? 'xlsx' : format;
                        downloadFile(blob, `prism_metadata_${new Date().toISOString().slice(0,10)}.${extension}`);
                        showSuccess('✅ ' + format.toUpperCase() + ' export completed successfully!');
                    } else {
                        const error = await response.json();
                        showError(error.detail || 'Export failed');
                    }
                } catch (error) {
                    showError('Network error: ' + error.message);
                }
            }
            
            async function analyzeFileExport() {
                const fileInput = document.getElementById('file-upload');
                const file = fileInput.files[0];
                
                if (!file) {
                    alert('Please select a file');
                    return;
                }
                
                showLoading('📄 Processing file and generating export...');
                
                const formData = new FormData();
                formData.append('file', file);
                
                try {
                    const response = await fetch('/api/file-csv', {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (response.ok) {
                        const blob = await response.blob();
                        downloadFile(blob, `prism_file_export_${file.name.split('.')[0]}.csv`);
                        showSuccess('✅ File processed and export generated successfully!');
                    } else {
                        const error = await response.json();
                        showError(error.detail || 'File processing failed');
                    }
                } catch (error) {
                    showError('Network error: ' + error.message);
                }
            }
            
            async function clearCache() {
                if (!confirm('Clear all cached metadata? This will force fresh API calls for all ISRCs.')) {
                    return;
                }
                
                showLoading('🗑️ Clearing cache...');
                
                try {
                    const response = await fetch('/api/cache/clear', { method: 'POST' });
                    
                    if (response.ok) {
                        showSuccess('✅ Cache cleared successfully!');
                    } else {
                        showError('Failed to clear cache');
                    }
                } catch (error) {
                    showError('Network error: ' + error.message);
                }
            }
            
            function showLoading(message) {
                const results = document.getElementById('results');
                results.innerHTML = '<div class="loading">' + message + '</div>';
                results.style.display = 'block';
            }
            
            function showSingleResult(data) {
                const results = document.getElementById('results');
                let confidenceClass = 'confidence-low';
                if (data.confidence >= 80) confidenceClass = 'confidence-high';
                else if (data.confidence >= 60) confidenceClass = 'confidence-medium';
                
                let html = '<h3>🔍 Analysis Results</h3>';
                
                if (data.confidence > 0) {
                    const sourcesList = (data.sources && data.sources.length > 0) ? data.sources.join(', ') : 'None';
                    html += '<div class="success">✅ Metadata Found from ' + sourcesList + '</div>';
                    html += '<div class="track-info">';
                    html += '<strong>ISRC:</strong> ' + data.isrc + '<br>';
                    html += '<strong>Title:</strong> ' + (data.title || 'Unknown') + '<br>';
                    html += '<strong>Artist:</strong> ' + (data.artist || 'Unknown') + '<br>';
                    html += '<strong>Album:</strong> ' + (data.album || 'Unknown') + '<br>';
                    if (data.release_date) html += '<strong>Release Date:</strong> ' + data.release_date + '<br>';
                    if (data.tempo) html += '<strong>Tempo:</strong> ' + data.tempo + ' BPM<br>';
                    if (data.energy) html += '<strong>Energy:</strong> ' + (data.energy * 100).toFixed(1) + '%<br>';
                    html += '<strong>Sources:</strong> ' + sourcesList + '<br>';
                    html += '<strong>Confidence:</strong> <span class="' + confidenceClass + '">' + data.confidence + '%</span><br>';
                    html += '</div>';
                    
                    html += '<div class="export-options">';
                    if (data.spotify_url) {
                        html += '<a href="' + data.spotify_url + '" target="_blank"><button class="export-btn">🎵 Open in Spotify</button></a>';
                    }
                    if (data.youtube_url) {
                        html += '<a href="' + data.youtube_url + '" target="_blank"><button class="export-btn">📺 Watch on YouTube</button></a>';
                    }
                    html += '</div>';
                } else {
                    html += '<div class="error">❌ No metadata found for this ISRC</div>';
                }
                
                results.innerHTML = html;
                results.style.display = 'block';
            }
            
            function showError(message) {
                const results = document.getElementById('results');
                results.innerHTML = '<div class="error">❌ ' + message + '</div>';
                results.style.display = 'block';
            }
            
            function showSuccess(message) {
                const results = document.getElementById('results');
                results.innerHTML = '<div class="success">' + message + '</div>';
                results.style.display = 'block';
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
    </html>
    """
    return HTMLResponse(content=html_content)

@app.post("/api/analyze-single")
async def analyze_single(request: ISRCRequest):
    """Analyze single ISRC with caching"""
    cleaned_isrc = clean_isrc(request.isrc)
    
    if not validate_isrc(cleaned_isrc):
        raise HTTPException(status_code=400, detail="Invalid ISRC format")
    
    metadata = await collect_metadata(cleaned_isrc)
    return metadata

@app.get("/api/bulk-csv")
async def bulk_csv(isrcs: str = Query(..., description="ISRCs to process")):
    """Process multiple ISRCs and return CSV"""
    isrc_text = isrcs.replace('\n', ',').replace('\r', ',')
    isrc_list = []
    
    for isrc in isrc_text.split(','):
        cleaned = clean_isrc(isrc)
        if validate_isrc(cleaned):
            isrc_list.append(cleaned)
    
    if not isrc_list:
        raise HTTPException(status_code=400, detail="No valid ISRCs found")
    
    logger.info(f"Processing {len(isrc_list)} ISRCs for CSV export")
    
    metadata_list = []
    for i, isrc in enumerate(isrc_list):
        logger.info(f"Processing ISRC {i+1}/{len(isrc_list)}: {isrc}")
        metadata = await collect_metadata(isrc)
        metadata_list.append(metadata)
        
        if i < len(isrc_list) - 1:
            await asyncio.sleep(0.5)
    
    csv_content = create_csv_export(metadata_list)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=prism_metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

@app.get("/api/bulk-excel")
async def bulk_excel(isrcs: str = Query(..., description="ISRCs to process")):
    """Process multiple ISRCs and return Excel file"""
    if not EXCEL_AVAILABLE:
        raise HTTPException(status_code=500, detail="Excel export not available. Install xlsxwriter.")
    
    isrc_text = isrcs.replace('\n', ',').replace('\r', ',')
    isrc_list = []
    
    for isrc in isrc_text.split(','):
        cleaned = clean_isrc(isrc)
        if validate_isrc(cleaned):
            isrc_list.append(cleaned)
    
    if not isrc_list:
        raise HTTPException(status_code=400, detail="No valid ISRCs found")
    
    logger.info(f"Processing {len(isrc_list)} ISRCs for Excel export")
    
    metadata_list = []
    for i, isrc in enumerate(isrc_list):
        logger.info(f"Processing ISRC {i+1}/{len(isrc_list)}: {isrc}")
        metadata = await collect_metadata(isrc)
        metadata_list.append(metadata)
        
        if i < len(isrc_list) - 1:
            await asyncio.sleep(0.5)
    
    excel_file = create_excel_export(metadata_list)
    
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=prism_metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"}
    )

@app.post("/api/file-csv")
async def file_csv(file: UploadFile = File(...)):
    """Process uploaded file and return CSV"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    content = await file.read()
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        text = content.decode('latin-1')
    
    isrc_list = extract_isrcs_from_text(text)
    
    if not isrc_list:
        raise HTTPException(status_code=400, detail="No valid ISRCs found in file")
    
    logger.info(f"Found {len(isrc_list)} ISRCs in file: {file.filename}")
    
    metadata_list = []
    for i, isrc in enumerate(isrc_list):
        logger.info(f"Processing ISRC {i+1}/{len(isrc_list)}: {isrc}")
        metadata = await collect_metadata(isrc)
        metadata_list.append(metadata)
        
        if i < len(isrc_list) - 1:
            await asyncio.sleep(0.5)
    
    csv_content = create_csv_export(metadata_list)
    
    filename = f"prism_export_{file.filename.split('.')[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/cache/clear")
async def clear_cache_endpoint(isrc: Optional[str] = None):
    """Clear cache endpoint"""
    cache.clear(isrc)
    return {"status": "success", "message": f"Cache cleared for {'all ISRCs' if not isrc else isrc}"}

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "PRISM Analytics - Metadata Aggregator",
        "version": "1.1.0",
        "timestamp": datetime.now().isoformat(),
        "apis_configured": {
            "spotify": bool(os.getenv('SPOTIFY_CLIENT_ID') and os.getenv('SPOTIFY_CLIENT_SECRET')),
            "youtube": bool(os.getenv('YOUTUBE_API_KEY')),
            "genius": bool(os.getenv('GENIUS_API_KEY')),
            "lastfm": bool(os.getenv('LASTFM_API_KEY')),
            "discogs": bool(os.getenv('DISCOGS_API_KEY'))
        },
        "cache_enabled": True,
        "excel_export": EXCEL_AVAILABLE
    }

if __name__ == "__main__":
    print("🎵 PRISM Analytics - Metadata Aggregator v1.1")
    print("✅ Phase 1 Features: YouTube, Caching, Excel Export")
    print("🚀 Starting server...")
    
    uvicorn.run(app, host="127.0.0.1", port=5000, log_level="info")