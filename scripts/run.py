#!/usr/bin/env python3
"""
PRISM Analytics - Enhanced Metadata Intelligence System
Main Application Entry Point
"""

import os
import sys
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, Query, Response, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import json
import io
import csv
from datetime import datetime

# Import configurations
from config.settings import Config
from src.services.api_clients import APIClientManager
from src.services.metadata_collector_async import AsyncMetadataCollector
from src.models.database import DatabaseManager, Track, TrackCredit, TrackLyrics

# Excel support
try:
    import xlsxwriter
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    print("⚠️ xlsxwriter not installed. Excel export will be limited.")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============= REQUEST MODELS =============
class ISRCAnalysisRequest(BaseModel):
    isrc: str = Field(..., description="International Standard Recording Code")
    include_lyrics: bool = Field(default=True, description="Include lyrics from Genius")
    include_credits: bool = Field(default=True, description="Include credits information")
    force_refresh: bool = Field(default=False, description="Skip cache and force refresh")

class BulkAnalysisRequest(BaseModel):
    isrcs: List[str] = Field(..., description="List of ISRCs to analyze")
    include_lyrics: bool = Field(default=False, description="Include lyrics (slower)")
    export_format: str = Field(default="csv", description="Export format: csv, excel, json")

class ExportRequest(BaseModel):
    isrcs: List[str] = Field(..., description="ISRCs to export")
    format: str = Field(default="csv", description="Export format")
    include_confidence: bool = Field(default=True, description="Include confidence metrics")

# ============= ENHANCED CONFIDENCE SCORER =============
class EnhancedConfidenceScorer:
    """Advanced confidence scoring with multi-factor analysis"""
    
    @staticmethod
    def calculate_score(metadata: Dict[str, Any]) -> Dict[str, Any]:
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
        scores["data_sources"] = min(100, len(sources) * 33.33)
        
        essential = ["title", "artist", "album", "duration_ms", "release_date"]
        present = sum(1 for field in essential if metadata.get(field))
        scores["essential_fields"] = (present / len(essential)) * 100
        
        audio = ["tempo", "key", "energy", "danceability", "valence"]
        audio_present = sum(1 for field in audio if metadata.get(field) is not None)
        scores["audio_features"] = (audio_present / len(audio)) * 100
        
        ids = ["spotify_id", "musicbrainz_id", "youtube_video_id"]
        ids_present = sum(1 for field in ids if metadata.get(field))
        scores["external_ids"] = (ids_present / len(ids)) * 100
        
        if metadata.get("popularity"):
            scores["popularity_metrics"] += 50
        if metadata.get("youtube_views"):
            scores["popularity_metrics"] += 50
            
        if metadata.get("has_lyrics"):
            scores["lyrics_availability"] = 100
            
        if metadata.get("credits", []):
            scores["credits_completeness"] = min(100, len(metadata["credits"]) * 20)
            
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

# ============= EXPORT SERVICE =============
class ExportService:
    """Enhanced export service with multiple formats"""
    
    @staticmethod
    def create_csv(metadata_list: List[Dict]) -> str:
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
            "Spotify_ID", "MusicBrainz_ID", "YouTube_ID", "Tempo", "Key",
            "Energy", "Danceability", "Valence", "Popularity",
            "Confidence_Score", "Quality_Rating", "Sources"
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
                "MusicBrainz_ID": item.get("musicbrainz_id", ""),
                "YouTube_ID": item.get("youtube_video_id", ""),
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
    def create_excel(metadata_list: List[Dict]) -> io.BytesIO:
        """Create Excel export with PRISM branding"""
        if not EXCEL_AVAILABLE:
            raise ValueError("Excel export not available")
            
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        
        # Define PRISM brand colors
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
            'font_color': '#1A1A1A'
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
        
        # Create main sheet
        worksheet = workbook.add_worksheet('Metadata')
        
        # Add PRISM branding
        worksheet.merge_range(0, 0, 0, 17, 'PRISM Analytics - Metadata Export', title_format)
        worksheet.merge_range(1, 0, 1, 17, f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        
        # Headers
        headers = [
            'ISRC', 'Title', 'Artist', 'Album', 'Duration (ms)', 'Release Date',
            'Spotify ID', 'MusicBrainz ID', 'YouTube ID', 'Views',
            'Tempo', 'Key', 'Energy', 'Danceability', 'Valence',
            'Popularity', 'Confidence %', 'Quality'
        ]
        
        for col, header in enumerate(headers):
            worksheet.write(3, col, header, header_format)
            
        # Set column widths
        widths = [12, 30, 30, 30, 12, 12, 15, 15, 15, 12, 10, 8, 8, 12, 8, 10, 12, 10]
        for i, width in enumerate(widths):
            worksheet.set_column(i, i, width)
            
        # Write data
        for row_idx, item in enumerate(metadata_list):
            row = row_idx + 4
            
            worksheet.write(row, 0, item.get("isrc", ""))
            worksheet.write(row, 1, item.get("title", ""))
            worksheet.write(row, 2, item.get("artist", ""))
            worksheet.write(row, 3, item.get("album", ""))
            worksheet.write(row, 4, item.get("duration_ms", ""))
            worksheet.write(row, 5, item.get("release_date", ""))
            worksheet.write(row, 6, item.get("spotify_id", ""))
            worksheet.write(row, 7, item.get("musicbrainz_id", ""))
            worksheet.write(row, 8, item.get("youtube_video_id", ""))
            worksheet.write(row, 9, item.get("youtube_views", ""))
            worksheet.write(row, 10, item.get("tempo", ""))
            worksheet.write(row, 11, item.get("key", ""))
            worksheet.write(row, 12, item.get("energy", ""))
            worksheet.write(row, 13, item.get("danceability", ""))
            worksheet.write(row, 14, item.get("valence", ""))
            worksheet.write(row, 15, item.get("popularity", ""))
            
            # Confidence with color
            confidence = item.get("confidence_score", 0)
            if confidence >= 80:
                worksheet.write(row, 16, confidence, high_confidence)
            elif confidence >= 60:
                worksheet.write(row, 16, confidence, medium_confidence)
            else:
                worksheet.write(row, 16, confidence, low_confidence)
                
            worksheet.write(row, 17, item.get("quality_rating", ""))
            
        # Add summary sheet
        summary = workbook.add_worksheet('Summary')
        summary.merge_range(0, 0, 0, 1, 'PRISM Analytics Summary', title_format)
        
        # Statistics
        total = len(metadata_list)
        avg_confidence = sum(item.get("confidence_score", 0) for item in metadata_list) / max(total, 1)
        
        stats = [
            ('Total Tracks', str(total)),
            ('Average Confidence', f'{avg_confidence:.1f}%'),
            ('Spotify Coverage', f'{sum(1 for item in metadata_list if item.get("spotify_id"))}/{total}'),
            ('YouTube Coverage', f'{sum(1 for item in metadata_list if item.get("youtube_video_id"))}/{total}'),
            ('MusicBrainz Coverage', f'{sum(1 for item in metadata_list if item.get("musicbrainz_id"))}/{total}')
        ]
        
        for row_idx, (label, value) in enumerate(stats):
            summary.write(row_idx + 2, 0, label)
            summary.write(row_idx + 2, 1, value)
            
        workbook.close()
        output.seek(0)
        return output

# ============= APPLICATION FACTORY =============
def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    
    app = FastAPI(
        title="PRISM Analytics Engine",
        description="Metadata Intelligence Component - Phase 2",
        version="2.0.0",
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
    db_manager.create_tables()
    
    api_clients = APIClientManager(api_config)
    metadata_collector = AsyncMetadataCollector(api_clients, db_manager)
    confidence_scorer = EnhancedConfidenceScorer()
    export_service = ExportService()
    
    # Store in app state
    app.state.config = config
    app.state.db_manager = db_manager
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
    """Serve main interface"""
    template_path = Path("templates/index.html")
    if template_path.exists():
        return HTMLResponse(content=template_path.read_text())
    
    # Use the enhanced template from main.py if template file doesn't exist
    template_path_enhanced = Path("templates/enhanced_index.html")
    if template_path_enhanced.exists():
        return HTMLResponse(content=template_path_enhanced.read_text())
    
    # Fallback to main.py if it exists
    main_path = Path("main.py")
    if main_path.exists():
        # Try to extract the HTML from main.py
        try:
            import subprocess
            result = subprocess.run([sys.executable, "main.py"], capture_output=True, text=True, timeout=1)
        except:
            pass
    
    return HTMLResponse(content="<h1>PRISM Analytics Engine</h1><p>Template not found</p>")

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    
    # Get database stats
    session = app.state.db_manager.get_session()
    try:
        track_count = session.query(Track).count()
        lyrics_count = session.query(TrackLyrics).count()
    finally:
        app.state.db_manager.close_session(session)
    
    # Check API clients
    api_status = await app.state.api_clients.validate_clients_async()
    
    return {
        "status": "healthy",
        "service": "PRISM Analytics Engine",
        "version": "2.0.0",
        "timestamp": datetime.now().isoformat(),
        "database": {
            "total_tracks": track_count,
            "tracks_with_lyrics": lyrics_count
        },
        "apis": api_status,
        "features": {
            "excel_export": EXCEL_AVAILABLE,
            "enhanced_confidence": True,
            "database_storage": True
        }
    }

@app.get("/api/stats")
async def get_statistics():
    """Get database statistics"""
    session = app.state.db_manager.get_session()
    try:
        total_tracks = session.query(Track).count()
        
        # Calculate average confidence
        tracks = session.query(Track).all()
        if tracks:
            avg_confidence = sum(track.confidence_score or 0 for track in tracks) / len(tracks)
        else:
            avg_confidence = 0
            
        tracks_with_lyrics = session.query(TrackLyrics).count()
        
        # Platform coverage
        spotify_coverage = session.query(Track).filter(Track.spotify_id.isnot(None)).count()
        youtube_coverage = session.query(Track).filter(Track.youtube_video_id.isnot(None)).count()
        musicbrainz_coverage = session.query(Track).filter(Track.musicbrainz_recording_id.isnot(None)).count()
        
        return {
            "total_tracks": total_tracks,
            "avg_confidence": avg_confidence,
            "tracks_with_lyrics": tracks_with_lyrics,
            "spotify_coverage": spotify_coverage,
            "youtube_coverage": youtube_coverage,
            "musicbrainz_coverage": musicbrainz_coverage
        }
    finally:
        app.state.db_manager.close_session(session)

@app.post("/api/analyze-enhanced")
async def analyze_enhanced(request: ISRCAnalysisRequest):
    """Enhanced ISRC analysis with confidence scoring"""
    
    # Clean ISRC
    isrc = request.isrc.upper().strip()
    
    # Validate format
    import re
    if not re.match(r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$', isrc):
        raise HTTPException(status_code=400, detail="Invalid ISRC format")
    
    try:
        # Analyze with metadata collector
        result = await app.state.metadata_collector.analyze_isrc_async(
            isrc,
            comprehensive=request.include_lyrics
        )
        
        # Calculate confidence
        confidence_data = app.state.confidence_scorer.calculate_score(result)
        
        # Merge confidence data
        result.update({
            "confidence": confidence_data["confidence_score"],
            "data_completeness": confidence_data["data_completeness"],
            "confidence_details": confidence_data
        })
        
        return result
        
    except Exception as e:
        logger.error(f"Analysis failed for {isrc}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bulk-csv")
async def bulk_csv_export(isrcs: str = Query(..., description="Comma-separated ISRCs")):
    """Bulk CSV export"""
    
    # Parse ISRCs
    isrc_list = [isrc.strip().upper() for isrc in isrcs.split(",") if isrc.strip()]
    
    if not isrc_list:
        raise HTTPException(status_code=400, detail="No valid ISRCs provided")
    
    # Collect metadata
    metadata_list = []
    for isrc in isrc_list:
        try:
            result = await app.state.metadata_collector.analyze_isrc_async(isrc, comprehensive=False)
            confidence_data = app.state.confidence_scorer.calculate_score(result)
            result.update({
                "confidence_score": confidence_data["confidence_score"],
                "quality_rating": confidence_data["quality_rating"]
            })
            metadata_list.append(result)
        except Exception as e:
            logger.error(f"Failed to analyze {isrc}: {e}")
            
    # Create CSV
    csv_content = app.state.export_service.create_csv(metadata_list)
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=prism_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        }
    )

@app.get("/api/bulk-excel")
async def bulk_excel_export(isrcs: str = Query(..., description="Comma-separated ISRCs")):
    """Bulk Excel export with summary"""
    
    if not EXCEL_AVAILABLE:
        raise HTTPException(status_code=500, detail="Excel export not available")
    
    # Parse ISRCs
    isrc_list = [isrc.strip().upper() for isrc in isrcs.split(",") if isrc.strip()]
    
    if not isrc_list:
        raise HTTPException(status_code=400, detail="No valid ISRCs provided")
    
    # Collect metadata
    metadata_list = []
    for isrc in isrc_list:
        try:
            result = await app.state.metadata_collector.analyze_isrc_async(isrc, comprehensive=False)
            confidence_data = app.state.confidence_scorer.calculate_score(result)
            result.update({
                "confidence_score": confidence_data["confidence_score"],
                "quality_rating": confidence_data["quality_rating"]
            })
            metadata_list.append(result)
        except Exception as e:
            logger.error(f"Failed to analyze {isrc}: {e}")
            
    # Create Excel
    excel_file = app.state.export_service.create_excel(metadata_list)
    
    return StreamingResponse(
        excel_file,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename=prism_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        }
    )

@app.post("/api/bulk-analyze")
async def bulk_analyze(request: BulkAnalysisRequest):
    """Bulk analysis with progress tracking"""
    
    results, errors = await app.state.metadata_collector.bulk_analyze_async(
        request.isrcs,
        comprehensive=request.include_lyrics
    )
    
    return {
        "success": len(results),
        "failed": len(errors),
        "results": results,
        "errors": errors,
        "timestamp": datetime.now().isoformat()
    }

# ============= MAIN ENTRY POINT =============
if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("🎵 PRISM Analytics Engine - Phase 2")
    print("Transforming Music Data into Actionable Intelligence")
    print("=" * 60)
    
    # Validate configuration
    config = Config()
    validation = config.validate_required_config()
    
    print("\n📊 Configuration Status:")
    for service, status in validation.items():
        icon = "✅" if status == "configured" else "⚠️"
        print(f"  {icon} {service.capitalize()}: {status}")
    
    print("\n🌐 Server Information:")
    print(f"  Web Interface: http://localhost:5000")
    print(f"  API Documentation: http://localhost:5000/api/docs")
    print(f"  Health Check: http://localhost:5000/api/health")
    
    print("\n🚀 Starting server...")
    print("=" * 60)
    
    # Run server
    uvicorn.run(
        "run:app",
        host="127.0.0.1",
        port=5000,
        reload=True,
        log_level="info"
    )