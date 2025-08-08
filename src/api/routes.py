"""
ISRC Meta Data Finder - API Routes
RESTful API endpoints for metadata analysis
"""

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, BackgroundTasks, Request, Depends
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from typing import Any  # Still need Any from typing
import json
import io
import csv
from datetime import datetime
import logging
import re

logger = logging.getLogger(__name__)

# Create API router
router = APIRouter(prefix="/api/v1", tags=["metadata"])

# ============= REQUEST/RESPONSE MODELS =============

class ISRCAnalysisRequest(BaseModel):
    """Single ISRC analysis request"""
    isrc: str = Field(..., description="International Standard Recording Code")
    include_lyrics: bool = Field(default=True, description="Include lyrics from Genius API")
    include_credits: bool = Field(default=True, description="Include detailed credits")
    include_technical: bool = Field(default=True, description="Include technical audio features")
    force_refresh: bool = Field(default=False, description="Force refresh, skip cache")

class ISRCAnalysisResponse(BaseModel):
    """ISRC analysis response"""
    isrc: str
    status: str
    metadata: dict[str, Any]
    confidence_score: float
    data_completeness: float
    quality_rating: str
    sources: list[str]
    processing_time_ms: int
    cached: bool
    timestamp: str

class BulkAnalysisRequest(BaseModel):
    """Bulk analysis request"""
    isrcs: list[str] = Field(..., description="List of ISRCs to analyze", max_length=100)
    comprehensive: bool = Field(default=False, description="Comprehensive analysis (slower)")
    parallel: bool = Field(default=True, description="Process in parallel")

class BulkAnalysisResponse(BaseModel):
    """Bulk analysis response"""
    total: int
    successful: int
    failed: int
    results: list[dict[str, Any]]
    errors: list[dict[str, str]]
    processing_time_seconds: float
    timestamp: str

class ExportRequest(BaseModel):
    """Export request"""
    isrcs: list[str] = Field(..., description="ISRCs to export")
    format: str = Field(default="csv", description="Export format: csv, excel, json, xml")
    include_confidence: bool = Field(default=True)
    include_technical: bool = Field(default=True)
    include_lyrics: bool = Field(default=False)

class SearchRequest(BaseModel):
    """Search request"""
    query: str = Field(..., description="Search query")
    search_type: str = Field(default="all", description="Search type: title, artist, album, all")
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)

class StatsResponse(BaseModel):
    """Statistics response"""
    total_tracks: int
    tracks_with_spotify: int
    tracks_with_youtube: int
    tracks_with_musicbrainz: int
    tracks_with_lyrics: int
    average_confidence: float
    average_completeness: float
    last_updated: str
    database_size_mb: float

# ============= DEPENDENCIES =============

async def get_app_state(request: Request) -> dict[str, Any]:
    """Get app state from request"""
    return {
        "metadata_collector": request.app.state.metadata_collector,
        "confidence_scorer": request.app.state.confidence_scorer,
        "export_service": request.app.state.export_service,
        "db_manager": request.app.state.db_manager,
        "api_clients": request.app.state.api_clients
    }

# ============= UTILITY FUNCTIONS =============

def validate_isrc(isrc: str) -> bool:
    """Validate ISRC format"""
    pattern = r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$'
    return bool(re.match(pattern, isrc.upper().strip()))

def clean_isrc(isrc: str) -> str:
    """Clean and normalize ISRC"""
    cleaned = re.sub(r'[-\s]', '', isrc.upper().strip())
    return cleaned

def extract_isrcs_from_text(text: str) -> list[str]:
    """Extract ISRCs from text"""
    pattern = r'\b[A-Z]{2}[-\s]?[A-Z0-9]{3}[-\s]?[0-9]{7}\b'
    matches = re.findall(pattern, text.upper())
    
    isrcs = []
    for match in matches:
        cleaned = clean_isrc(match)
        if validate_isrc(cleaned):
            isrcs.append(cleaned)
    
    return list(set(isrcs))

# ============= MAIN ROUTES =============

@router.post("/analyze", response_model=ISRCAnalysisResponse)
async def analyze_single_isrc(
    request: ISRCAnalysisRequest,
    app_state: dict[str, Any] = Depends(get_app_state)
):
    """
    Analyze a single ISRC with comprehensive metadata collection
    
    This endpoint performs deep analysis including:
    - Multi-source metadata aggregation
    - Confidence scoring
    - Lyrics and credits (optional)
    - Technical audio features (optional)
    """
    
    start_time = datetime.now()
    
    # Clean and validate ISRC
    isrc = clean_isrc(request.isrc)
    if not validate_isrc(isrc):
        raise HTTPException(status_code=400, detail="Invalid ISRC format")
    
    try:
        # Get metadata collector from app state
        collector = app_state.get("metadata_collector")
        if not collector:
            raise HTTPException(status_code=500, detail="Metadata collector not initialized")
        
        # Perform analysis
        result = await collector.analyze_isrc_async(
            isrc,
            comprehensive=request.include_lyrics and request.include_credits
        )
        
        # Calculate confidence
        scorer = app_state.get("confidence_scorer")
        if scorer:
            confidence_data = scorer.calculate_score(result)
        else:
            confidence_data = {
                "confidence_score": 0,
                "data_completeness": 0,
                "quality_rating": "Unknown"
            }
        
        # Calculate processing time
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return ISRCAnalysisResponse(
            isrc=isrc,
            status="success",
            metadata=result,
            confidence_score=confidence_data["confidence_score"],
            data_completeness=confidence_data.get("data_completeness", 0),
            quality_rating=confidence_data.get("quality_rating", "Unknown"),
            sources=result.get("sources", []),
            processing_time_ms=processing_time,
            cached=False,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Analysis failed for {isrc}: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@router.post("/analyze/bulk", response_model=BulkAnalysisResponse)
async def analyze_bulk_isrcs(
    request: BulkAnalysisRequest,
    background_tasks: BackgroundTasks,
    app_state: dict[str, Any] = Depends(get_app_state)
):
    """
    Analyze multiple ISRCs in bulk
    
    Features:
    - Batch processing up to 100 ISRCs
    - Parallel or sequential processing
    - Progress tracking
    - Error handling per ISRC
    """
    
    start_time = datetime.now()
    
    # Validate all ISRCs
    valid_isrcs = []
    for isrc in request.isrcs:
        cleaned = clean_isrc(isrc)
        if validate_isrc(cleaned):
            valid_isrcs.append(cleaned)
    
    if not valid_isrcs:
        raise HTTPException(status_code=400, detail="No valid ISRCs provided")
    
    # Get collector
    collector = app_state.get("metadata_collector")
    if not collector:
        raise HTTPException(status_code=500, detail="Metadata collector not initialized")
    
    # Perform bulk analysis
    results, errors = await collector.bulk_analyze_async(
        valid_isrcs,
        comprehensive=request.comprehensive
    )
    
    processing_time = (datetime.now() - start_time).total_seconds()
    
    return BulkAnalysisResponse(
        total=len(valid_isrcs),
        successful=len(results),
        failed=len(errors),
        results=results,
        errors=errors,
        processing_time_seconds=processing_time,
        timestamp=datetime.now().isoformat()
    )

@router.post("/export")
async def export_metadata(
    request: ExportRequest,
    app_state: dict[str, Any] = Depends(get_app_state)
):
    """
    Export metadata in various formats
    
    Supported formats:
    - CSV: Spreadsheet compatible
    - Excel: Multi-sheet with formatting
    - JSON: API integration
    - XML: Legacy system support
    """
    
    # Validate ISRCs
    valid_isrcs = [clean_isrc(isrc) for isrc in request.isrcs if validate_isrc(clean_isrc(isrc))]
    
    if not valid_isrcs:
        raise HTTPException(status_code=400, detail="No valid ISRCs provided")
    
    # Get services
    export_service = app_state.get("export_service")
    if not export_service:
        raise HTTPException(status_code=500, detail="Export service not initialized")
    
    collector = app_state.get("metadata_collector")
    if not collector:
        raise HTTPException(status_code=500, detail="Metadata collector not initialized")
    
    # Collect metadata for export
    metadata_list = []
    
    for isrc in valid_isrcs:
        try:
            result = await collector.analyze_isrc_async(isrc, comprehensive=False)
            metadata_list.append(result)
        except Exception as e:
            logger.error(f"Failed to get metadata for {isrc}: {e}")
    
    # Generate export based on format
    if request.format == "csv":
        content = export_service.create_csv(metadata_list)
        return Response(
            content=content,
            media_type="text/csv",
            headers={
                "Content-Disposition": f"attachment; filename=isrc_meta_data_export_{datetime.now().strftime('%Y%m%d')}.csv"
            }
        )
    
    elif request.format == "excel":
        excel_file = export_service.create_excel(metadata_list)
        return StreamingResponse(
            excel_file,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename=isrc_meta_data_export_{datetime.now().strftime('%Y%m%d')}.xlsx"
            }
        )
    
    elif request.format == "json":
        return Response(
            content=json.dumps(metadata_list, indent=2),
            media_type="application/json",
            headers={
                "Content-Disposition": f"attachment; filename=isrc_meta_data_export_{datetime.now().strftime('%Y%m%d')}.json"
            }
        )
    
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {request.format}")

@router.get("/track/{isrc}")
async def get_track_metadata(
    isrc: str,
    refresh: bool = Query(default=False, description="Force refresh from sources"),
    app_state: dict[str, Any] = Depends(get_app_state)
):
    """
    Get metadata for a specific ISRC
    
    Returns cached data if available, otherwise triggers analysis
    """
    
    # Clean and validate
    isrc = clean_isrc(isrc)
    if not validate_isrc(isrc):
        raise HTTPException(status_code=400, detail="Invalid ISRC format")
    
    # Get from database first
    db_manager = app_state.get("db_manager")
    if db_manager and not refresh:
        session = db_manager.get_session()
        try:
            from src.models.database import Track
            track = session.query(Track).filter(Track.isrc == isrc).first()
            if track:
                return {
                    "isrc": track.isrc,
                    "title": track.title,
                    "artist": track.artist,
                    "album": track.album,
                    "cached": True,
                    "last_updated": track.last_updated.isoformat() if track.last_updated else None
                }
        finally:
            db_manager.close_session(session)
    
    # If not cached or refresh requested, analyze
    collector = app_state.get("metadata_collector")
    if collector:
        result = await collector.analyze_isrc_async(isrc, comprehensive=False)
        return result
    
    raise HTTPException(status_code=404, detail="Track not found")

@router.get("/search")
async def search_tracks(
    q: str = Query(..., description="Search query"),
    type: str = Query(default="all", description="Search type: title, artist, album, all"),
    limit: int = Query(default=10, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    app_state: dict[str, Any] = Depends(get_app_state)
):
    """
    Search for tracks in the database
    
    Search across title, artist, album fields
    """
    
    db_manager = app_state.get("db_manager")
    if not db_manager:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    session = db_manager.get_session()
    try:
        from src.models.database import Track
        
        query = session.query(Track)
        
        # Apply search filters
        search_term = f"%{q}%"
        if type == "title":
            query = query.filter(Track.title.ilike(search_term))
        elif type == "artist":
            query = query.filter(Track.artist.ilike(search_term))
        elif type == "album":
            query = query.filter(Track.album.ilike(search_term))
        else:  # all
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    Track.title.ilike(search_term),
                    Track.artist.ilike(search_term),
                    Track.album.ilike(search_term)
                )
            )
        
        # Apply pagination
        total = query.count()
        results = query.offset(offset).limit(limit).all()
        
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "results": [
                {
                    "isrc": track.isrc,
                    "title": track.title,
                    "artist": track.artist,
                    "album": track.album,
                    "confidence_score": track.confidence_score
                }
                for track in results
            ]
        }
        
    finally:
        db_manager.close_session(session)

@router.get("/stats", response_model=StatsResponse)
async def get_statistics(app_state: dict[str, Any] = Depends(get_app_state)):
    """
    Get system statistics
    
    Returns database statistics and API coverage metrics
    """
    
    db_manager = app_state.get("db_manager")
    if not db_manager:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    session = db_manager.get_session()
    try:
        from src.models.database import Track, TrackLyrics
        
        # Basic counts
        total_tracks = session.query(Track).count()
        
        # Platform coverage
        spotify_count = session.query(Track).filter(Track.spotify_id.isnot(None)).count()
        youtube_count = session.query(Track).filter(Track.youtube_video_id.isnot(None)).count()
        musicbrainz_count = session.query(Track).filter(Track.musicbrainz_recording_id.isnot(None)).count()
        lyrics_count = session.query(TrackLyrics).count()
        
        # Calculate averages
        tracks = session.query(Track).all()
        if tracks:
            avg_confidence = sum(t.confidence_score or 0 for t in tracks) / len(tracks)
            avg_completeness = sum(t.data_completeness or 0 for t in tracks) / len(tracks)
        else:
            avg_confidence = 0
            avg_completeness = 0
        
        # Database size (approximate)
        import os
        db_path = "data/isrc_meta_data.db"
        db_size_mb = os.path.getsize(db_path) / (1024 * 1024) if os.path.exists(db_path) else 0
        
        return StatsResponse(
            total_tracks=total_tracks,
            tracks_with_spotify=spotify_count,
            tracks_with_youtube=youtube_count,
            tracks_with_musicbrainz=musicbrainz_count,
            tracks_with_lyrics=lyrics_count,
            average_confidence=avg_confidence,
            average_completeness=avg_completeness,
            last_updated=datetime.now().isoformat(),
            database_size_mb=db_size_mb
        )
        
    finally:
        db_manager.close_session(session)

@router.post("/upload/csv")
async def upload_csv_file(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks | None = None,
    app_state: dict[str, Any] = Depends(get_app_state)
):
    """
    Upload CSV file with ISRCs for batch processing
    
    CSV should contain ISRC column
    """
    
    if not file.filename or not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are supported")
    
    try:
        # Read CSV
        contents = await file.read()
        text = contents.decode('utf-8')
        
        # Parse CSV
        reader = csv.DictReader(io.StringIO(text))
        isrcs = []
        
        # Look for ISRC column
        for row in reader:
            if 'ISRC' in row:
                isrc = clean_isrc(row['ISRC'])
                if validate_isrc(isrc):
                    isrcs.append(isrc)
            elif 'isrc' in row:
                isrc = clean_isrc(row['isrc'])
                if validate_isrc(isrc):
                    isrcs.append(isrc)
        
        if not isrcs:
            raise HTTPException(status_code=400, detail="No valid ISRCs found in CSV")
        
        # Process in background if background_tasks is available
        collector = app_state.get("metadata_collector")
        if background_tasks and collector:
            background_tasks.add_task(
                collector.bulk_analyze_async,
                isrcs,
                comprehensive=False
            )
            
            return {
                "status": "accepted",
                "isrcs_found": len(isrcs),
                "message": f"Processing {len(isrcs)} ISRCs in background",
                "timestamp": datetime.now().isoformat()
            }
        else:
            return {
                "status": "accepted",
                "isrcs_found": len(isrcs),
                "message": f"Found {len(isrcs)} ISRCs - manual processing required",
                "timestamp": datetime.now().isoformat()
            }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"CSV processing failed: {str(e)}")

@router.delete("/cache/{isrc}")
async def clear_cache_for_isrc(
    isrc: str,
    app_state: dict[str, Any] = Depends(get_app_state)
):
    """
    Clear cached data for a specific ISRC
    
    Forces fresh analysis on next request
    """
    
    isrc = clean_isrc(isrc)
    if not validate_isrc(isrc):
        raise HTTPException(status_code=400, detail="Invalid ISRC format")
    
    # Clear from database
    db_manager = app_state.get("db_manager")
    if db_manager:
        session = db_manager.get_session()
        try:
            from src.models.database import Track, TrackLyrics, TrackCredit
            
            # Delete related records
            session.query(TrackCredit).filter(TrackCredit.isrc == isrc).delete()
            session.query(TrackLyrics).filter(TrackLyrics.isrc == isrc).delete()
            session.query(Track).filter(Track.isrc == isrc).delete()
            session.commit()
            
            return {
                "status": "success",
                "message": f"Cache cleared for {isrc}",
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            session.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")
        finally:
            db_manager.close_session(session)
    
    raise HTTPException(status_code=500, detail="Database not initialized")

@router.get("/credits/{isrc}")
async def get_track_credits(
    isrc: str,
    app_state: dict[str, Any] = Depends(get_app_state)
):
    """
    Get detailed credits for a track
    
    Returns composers, producers, performers, etc.
    """
    
    isrc = clean_isrc(isrc)
    if not validate_isrc(isrc):
        raise HTTPException(status_code=400, detail="Invalid ISRC format")
    
    db_manager = app_state.get("db_manager")
    if not db_manager:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    session = db_manager.get_session()
    try:
        from src.models.database import TrackCredit
        
        credits = session.query(TrackCredit).filter(TrackCredit.isrc == isrc).all()
        
        if not credits:
            raise HTTPException(status_code=404, detail="No credits found for this ISRC")
        
        return {
            "isrc": isrc,
            "credits": [
                {
                    "name": credit.person_name,
                    "type": credit.credit_type,
                    "role_details": json.loads(credit.role_details) if credit.role_details else {},
                    "source": credit.source_api,
                    "confidence": credit.source_confidence
                }
                for credit in credits
            ],
            "total": len(credits)
        }
        
    finally:
        db_manager.close_session(session)

@router.get("/lyrics/{isrc}")
async def get_track_lyrics(
    isrc: str,
    app_state: dict[str, Any] = Depends(get_app_state)
):
    """
    Get lyrics for a track
    
    Returns lyrics text and metadata
    """
    
    isrc = clean_isrc(isrc)
    if not validate_isrc(isrc):
        raise HTTPException(status_code=400, detail="Invalid ISRC format")
    
    db_manager = app_state.get("db_manager")
    if not db_manager:
        raise HTTPException(status_code=500, detail="Database not initialized")
    
    session = db_manager.get_session()
    try:
        from src.models.database import TrackLyrics
        
        lyrics = session.query(TrackLyrics).filter(TrackLyrics.isrc == isrc).first()
        
        if not lyrics:
            raise HTTPException(status_code=404, detail="No lyrics found for this ISRC")
        
        return {
            "isrc": isrc,
            "lyrics": lyrics.lyrics_text,
            "language": lyrics.language_code,
            "explicit": lyrics.explicit_content,
            "copyright": json.loads(lyrics.copyright_info) if lyrics.copyright_info else {},
            "source": lyrics.source_api,
            "source_url": lyrics.source_url
        }
        
    finally:
        db_manager.close_session(session)

# Export router for use in main app
__all__ = ['router']