#!/usr/bin/env python3
"""
PRISM Analytics - Final Working Version
ISRC Metadata to CSV Tool - Production Ready
"""

import asyncio
import csv
import io
import logging
import os
import re
import sys
import traceback
from datetime import datetime
from typing import List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response, File, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn

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

class ISRCRequest(BaseModel):
    isrc: str

def validate_isrc(isrc: str) -> bool:
    """Validate ISRC format"""
    pattern = r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$'
    return bool(re.match(pattern, isrc.upper().strip()))

def clean_isrc(isrc: str) -> str:
    """Clean ISRC format"""
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

async def get_spotify_metadata(isrc: str) -> dict:
    """Get metadata from Spotify API"""
    try:
        import requests
        import base64
        
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
            return {
                'title': track.get('name', ''),
                'artist': ', '.join([a['name'] for a in track.get('artists', [])]),
                'album': track.get('album', {}).get('name', ''),
                'duration_ms': track.get('duration_ms', ''),
                'release_date': track.get('album', {}).get('release_date', ''),
                'spotify_id': track.get('id', ''),
                'spotify_url': track.get('external_urls', {}).get('spotify', ''),
                'popularity': track.get('popularity', ''),
                'confidence': 85
            }
        else:
            return {'error': 'No tracks found for this ISRC'}
            
    except Exception as e:
        return {'error': f'Spotify API error: {str(e)}'}

async def get_musicbrainz_metadata(isrc: str) -> dict:
    """Get metadata from MusicBrainz API"""
    try:
        import requests
        
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
            
            return {
                'title': recording.get('title', ''),
                'artist': artist_name,
                'musicbrainz_id': recording.get('id', ''),
                'length': recording.get('length', ''),
                'confidence': 75
            }
        else:
            return {'error': 'No recordings found for this ISRC'}
            
    except Exception as e:
        return {'error': f'MusicBrainz API error: {str(e)}'}

async def collect_metadata(isrc: str) -> dict:
    """Collect metadata from available sources"""
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
        'popularity': '',
        'confidence': 0,
        'source': '',
        'last_updated': datetime.now().isoformat()
    }
    
    # Try Spotify first
    logger.info(f"Checking Spotify for ISRC: {isrc}")
    spotify_data = await get_spotify_metadata(isrc)
    
    if 'error' not in spotify_data:
        result.update(spotify_data)
        result['source'] = 'Spotify'
        logger.info(f"Found on Spotify: {result['title']} by {result['artist']}")
        return result
    
    # Try MusicBrainz if Spotify fails
    logger.info(f"Checking MusicBrainz for ISRC: {isrc}")
    mb_data = await get_musicbrainz_metadata(isrc)
    
    if 'error' not in mb_data:
        result.update(mb_data)
        result['source'] = 'MusicBrainz'
        logger.info(f"Found on MusicBrainz: {result['title']} by {result['artist']}")
        return result
    
    # No data found
    logger.warning(f"No metadata found for ISRC: {isrc}")
    result['title'] = 'NOT FOUND'
    result['artist'] = 'NOT FOUND'
    result['source'] = 'None'
    
    return result

def create_csv_export(metadata_list: List[dict]) -> str:
    """Create CSV from metadata list"""
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
        'Popularity', 'Confidence', 'Source', 'Last_Updated'
    ]
    
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    
    for item in metadata_list:
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
            'Popularity': item.get('popularity', ''),
            'Confidence': item.get('confidence', 0),
            'Source': item.get('source', ''),
            'Last_Updated': item.get('last_updated', '')
        })
    
    return output.getvalue()

# Create FastAPI app
app = FastAPI(
    title="PRISM Analytics - ISRC to CSV Tool",
    description="Transform ISRC codes into comprehensive metadata CSV exports",
    version="1.0.0"
)

@app.get("/", response_class=HTMLResponse)
async def root():
    """Main application interface"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>PRISM Analytics - ISRC to CSV Tool</title>
        <style>
            body { 
                font-family: 'Segoe UI', system-ui, sans-serif; 
                max-width: 900px; 
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
            input, textarea, button { 
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
        </style>
    </head>
    <body>
        <div class="header">
            <div class="logo">P R I S M</div>
            <div class="tagline">Analytics Engine</div>
            <p>Transform Music Data into Actionable Insights</p>
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
                <h3>📊 Bulk ISRC to CSV</h3>
                <textarea id="bulk-isrcs" rows="4" placeholder="Enter multiple ISRCs separated by commas or new lines&#10;Example:&#10;USRC17607839&#10;GBUM71505078&#10;USUM71703861"></textarea>
                <button onclick="analyzeBulkCSV()">Generate CSV Export</button>
            </div>
        </div>

        <div class="form-section">
            <div class="form-group">
                <h3>📄 File Upload</h3>
                <input type="file" id="file-upload" accept=".txt,.csv" />
                <button onclick="analyzeFileCSV()">Upload File & Generate CSV</button>
                <small style="color: #666; display: block; margin-top: 5px;">
                    Supported formats: .txt, .csv (will extract ISRCs automatically)
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
                
                showLoading('🔍 Analyzing ISRC...');
                
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
            
            async function analyzeBulkCSV() {
                const isrcs = document.getElementById('bulk-isrcs').value.trim();
                if (!isrcs) {
                    alert('Please enter ISRCs');
                    return;
                }
                
                showLoading('📊 Processing ISRCs and generating CSV...');
                
                try {
                    const response = await fetch('/api/bulk-csv?' + new URLSearchParams({ isrcs: isrcs }));
                    
                    if (response.ok) {
                        const blob = await response.blob();
                        downloadCSV(blob, `prism_metadata_${new Date().toISOString().slice(0,10)}.csv`);
                        showSuccess('✅ CSV export completed successfully!');
                    } else {
                        const error = await response.json();
                        showError(error.detail || 'Export failed');
                    }
                } catch (error) {
                    showError('Network error: ' + error.message);
                }
            }
            
            async function analyzeFileCSV() {
                const fileInput = document.getElementById('file-upload');
                const file = fileInput.files[0];
                
                if (!file) {
                    alert('Please select a file');
                    return;
                }
                
                showLoading('📄 Processing file and generating CSV...');
                
                const formData = new FormData();
                formData.append('file', file);
                
                try {
                    const response = await fetch('/api/file-csv', {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (response.ok) {
                        const blob = await response.blob();
                        downloadCSV(blob, `prism_file_export_${file.name.split('.')[0]}.csv`);
                        showSuccess('✅ File processed and CSV exported successfully!');
                    } else {
                        const error = await response.json();
                        showError(error.detail || 'File processing failed');
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
                    html += '<div class="success">✅ Metadata Found!</div>';
                    html += '<div class="track-info">';
                    html += '<strong>ISRC:</strong> ' + data.isrc + '<br>';
                    html += '<strong>Title:</strong> ' + (data.title || 'Unknown') + '<br>';
                    html += '<strong>Artist:</strong> ' + (data.artist || 'Unknown') + '<br>';
                    html += '<strong>Album:</strong> ' + (data.album || 'Unknown') + '<br>';
                    if (data.release_date) html += '<strong>Release Date:</strong> ' + data.release_date + '<br>';
                    if (data.source) html += '<strong>Source:</strong> ' + data.source + '<br>';
                    html += '<strong>Confidence:</strong> <span class="' + confidenceClass + '">' + data.confidence + '%</span><br>';
                    if (data.spotify_url) {
                        html += '<strong>Spotify:</strong> <a href="' + data.spotify_url + '" target="_blank">Open in Spotify</a><br>';
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
            
            function downloadCSV(blob, filename) {
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

# REMOVED THE PROBLEMATIC EXPORT ENDPOINT
# The /api/export/{format} endpoint was causing the errors because it referenced
# undefined dependencies (Depends, get_db_manager, ExportService)
# This functionality would need to be reimplemented if needed

@app.post("/api/analyze-single")
async def analyze_single(request: ISRCRequest):
    """Analyze single ISRC"""
    cleaned_isrc = clean_isrc(request.isrc)
    
    if not validate_isrc(cleaned_isrc):
        raise HTTPException(status_code=400, detail="Invalid ISRC format")
    
    metadata = await collect_metadata(cleaned_isrc)
    return metadata

@app.get("/api/bulk-csv")
async def bulk_csv(isrcs: str = Query(..., description="Comma-separated or newline-separated ISRCs")):
    """Process multiple ISRCs and return CSV"""
    # Parse ISRCs from input
    isrc_text = isrcs.replace('\n', ',').replace('\r', ',')
    isrc_list = []
    
    for isrc in isrc_text.split(','):
        cleaned = clean_isrc(isrc)
        if validate_isrc(cleaned):
            isrc_list.append(cleaned)
    
    if not isrc_list:
        raise HTTPException(status_code=400, detail="No valid ISRCs found")
    
    logger.info(f"Processing {len(isrc_list)} ISRCs for CSV export")
    
    # Collect metadata for all ISRCs
    metadata_list = []
    for i, isrc in enumerate(isrc_list):
        logger.info(f"Processing ISRC {i+1}/{len(isrc_list)}: {isrc}")
        metadata = await collect_metadata(isrc)
        metadata_list.append(metadata)
        
        # Rate limiting - be respectful to APIs
        if i < len(isrc_list) - 1:  # Don't sleep after the last one
            await asyncio.sleep(0.5)
    
    # Generate CSV
    csv_content = create_csv_export(metadata_list)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=prism_metadata_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"}
    )

@app.post("/api/file-csv")
async def file_csv(file: UploadFile = File(...)):
    """Process uploaded file and return CSV"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Read file content
    content = await file.read()
    try:
        text = content.decode('utf-8')
    except UnicodeDecodeError:
        text = content.decode('latin-1')
    
    # Extract ISRCs
    isrc_list = extract_isrcs_from_text(text)
    
    if not isrc_list:
        raise HTTPException(status_code=400, detail="No valid ISRCs found in file")
    
    logger.info(f"Found {len(isrc_list)} ISRCs in file: {file.filename}")
    
    # Collect metadata
    metadata_list = []
    for i, isrc in enumerate(isrc_list):
        logger.info(f"Processing ISRC {i+1}/{len(isrc_list)}: {isrc}")
        metadata = await collect_metadata(isrc)
        metadata_list.append(metadata)
        
        # Rate limiting
        if i < len(isrc_list) - 1:
            await asyncio.sleep(0.5)
    
    # Generate CSV
    csv_content = create_csv_export(metadata_list)
    
    filename = f"prism_export_{file.filename.split('.')[0]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "PRISM Analytics - ISRC to CSV Tool",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "spotify_configured": bool(os.getenv('SPOTIFY_CLIENT_ID') and os.getenv('SPOTIFY_CLIENT_SECRET'))
    }

if __name__ == "__main__":
    print("🎵 PRISM Analytics - ISRC to CSV Tool")
    print("✅ Environment variables loaded")
    print("🚀 Starting server...")
    
    uvicorn.run(app, host="127.0.0.1", port=5000, log_level="info")