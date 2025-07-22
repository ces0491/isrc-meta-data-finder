"""
PRISM Analytics - FastAPI Main Application
ISRC Metadata Aggregation Microservice
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator
import logging
from datetime import datetime
import asyncio
import uvicorn
import os

# Import our services
from src.models.database import DatabaseManager, init_database
from src.services.api_clients import APIClientManager
from src.services.metadata_collector_async import AsyncMetadataCollector
from config.settings import Config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state
db_manager = None
api_clients = None
metadata_collector = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    global db_manager, api_clients, metadata_collector
    
    # Startup
    logger.info("🚀 Starting PRISM Analytics Metadata Service")
    
    try:
        # Initialize database
        init_database()
        db_manager = DatabaseManager()
        logger.info("✅ Database initialized")
        
        # Initialize API clients
        config = Config()
        api_config = config.get_api_config()
        api_clients = APIClientManager(api_config)
        
        # Validate API clients
        client_status = await api_clients.validate_clients_async()
        logger.info(f"📡 API Clients Status: {client_status}")
        
        # Initialize metadata collector
        metadata_collector = AsyncMetadataCollector(api_clients, db_manager)
        logger.info("✅ Async Metadata Collector initialized")
        
        # Store in app state
        app.state.db_manager = db_manager
        app.state.api_clients = api_clients
        app.state.metadata_collector = metadata_collector
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down PRISM Analytics Metadata Service")
    if db_manager:
        # Close any remaining database connections
        pass

# Create FastAPI app with lifespan
app = FastAPI(
    title="PRISM Analytics - ISRC Metadata Service",
    description="Comprehensive ISRC metadata aggregation from multiple music industry sources",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Pydantic models for request/response validation
class ISRCAnalysisRequest(BaseModel):
    isrc: str = Field(..., min_length=12, max_length=12, description="International Standard Recording Code")
    comprehensive: bool = Field(True, description="Include extended metadata (lyrics, credits, technical data)")
    include_lyrics: bool = Field(True, description="Fetch lyrics data")
    include_credits: bool = Field(True, description="Fetch detailed credits")
    include_technical: bool = Field(True, description="Fetch audio technical features")
    
    @validator('isrc')
    def validate_isrc_format(cls, v):
        import re
        v = v.upper().strip()
        if not re.match(r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$', v):
            raise ValueError('Invalid ISRC format. Expected: 2 letters + 3 alphanumeric + 7 digits')
        return v

class BulkAnalysisRequest(BaseModel):
    isrc_list: List[str] = Field(..., min_items=1, max_items=100, description="List of ISRCs to analyze")
    comprehensive: bool = Field(False, description="Use comprehensive analysis for bulk requests")

class MetadataResponse(BaseModel):
    isrc: str
    metadata: Dict[str, Any]
    audio_features: Dict[str, Any] = {}
    platform_ids: Dict[str, str] = {}
    confidence_score: float = Field(..., ge=0, le=100)
    data_completeness: float = Field(..., ge=0, le=100)
    analysis_timestamp: str
    processing_time_ms: int
    status: str

class BulkAnalysisResponse(BaseModel):
    total_requested: int
    processed: int
    failed: int
    results: List[Dict[str, Any]]
    errors: List[Dict[str, str]]
    total_processing_time_ms: int
    status: str

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str
    components: Dict[str, Any]
    uptime_seconds: float

# Dependency injection
async def get_metadata_collector():
    if not metadata_collector:
        raise HTTPException(status_code=503, detail="Metadata collector not available")
    return metadata_collector

async def get_db_manager():
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")
    return db_manager

# API Routes
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main application interface"""
    try:
        with open("templates/index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(
            content="<h1>PRISM Analytics - ISRC Metadata Service</h1><p>API documentation available at <a href='/docs'>/docs</a></p>"
        )

@app.post("/api/analyze-isrc-enhanced", response_model=MetadataResponse)
async def analyze_isrc_enhanced(
    request: ISRCAnalysisRequest,
    collector: AsyncMetadataCollector = Depends(get_metadata_collector)
):
    """Comprehensive ISRC metadata analysis"""
    start_time = datetime.now()
    
    try:
        logger.info(f"🎵 Starting analysis for ISRC: {request.isrc}")
        
        result = await collector.analyze_isrc_async(
            isrc=request.isrc,
            comprehensive=request.comprehensive,
            include_lyrics=request.include_lyrics,
            include_credits=request.include_credits,
            include_technical=request.include_technical
        )
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        response = MetadataResponse(
            isrc=request.isrc,
            metadata={
                'title': result.get('title'),
                'artist': result.get('artist'),
                'album': result.get('album'),
                'duration_ms': result.get('duration_ms'),
                'release_date': result.get('release_date')
            },
            audio_features=result.get('audio_features', {}),
            platform_ids=result.get('platform_ids', {}),
            confidence_score=result.get('confidence_score', 0.0),
            data_completeness=result.get('data_completeness', 0.0),
            analysis_timestamp=result.get('last_updated', datetime.now().isoformat()),
            processing_time_ms=processing_time,
            status='success'
        )
        
        logger.info(f"✅ Analysis completed for {request.isrc} - Confidence: {response.confidence_score:.1f}%")
        return response
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"❌ Analysis failed for {request.isrc}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

@app.post("/api/bulk-metadata-analysis", response_model=BulkAnalysisResponse)
async def bulk_metadata_analysis(
    request: BulkAnalysisRequest,
    background_tasks: BackgroundTasks,
    collector: AsyncMetadataCollector = Depends(get_metadata_collector)
):
    """Bulk ISRC analysis with async processing"""
    start_time = datetime.now()
    
    try:
        logger.info(f"📊 Starting bulk analysis for {len(request.isrc_list)} ISRCs")
        
        # Process ISRCs concurrently
        results, errors = await collector.bulk_analyze_async(
            isrc_list=request.isrc_list,
            comprehensive=request.comprehensive
        )
        
        processing_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        response = BulkAnalysisResponse(
            total_requested=len(request.isrc_list),
            processed=len(results),
            failed=len(errors),
            results=results,
            errors=errors,
            total_processing_time_ms=processing_time,
            status='completed'
        )
        
        logger.info(f"✅ Bulk analysis completed: {len(results)} success, {len(errors)} errors")
        return response
        
    except Exception as e:
        logger.error(f"❌ Bulk analysis failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Bulk analysis failed: {str(e)}")

@app.get("/api/track/{isrc}/metadata")
async def get_track_metadata(
    isrc: str = Field(..., min_length=12, max_length=12),
    db: DatabaseManager = Depends(get_db_manager),
    collector: AsyncMetadataCollector = Depends(get_metadata_collector)
):
    """Retrieve cached metadata for a specific track"""
    try:
        isrc = isrc.upper().strip()
        
        # Validate ISRC format
        import re
        if not re.match(r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$', isrc):
            raise HTTPException(status_code=400, detail="Invalid ISRC format")
        
        session = db.get_session()
        try:
            from src.models.database import Track
            track = session.query(Track).filter(Track.isrc == isrc).first()
            
            if not track:
                raise HTTPException(status_code=404, detail="Track not found in cache")
            
            track_data = collector._track_to_dict(track)
            return track_data
            
        finally:
            db.close_session(session)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Metadata retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export/metadata")
async def export_metadata(
    format: str = Query("json", regex="^(json|csv|xlsx)$"),
    isrc: List[str] = Query(..., description="ISRCs to export"),
    db: DatabaseManager = Depends(get_db_manager)
):
    """Export metadata in various formats"""
    try:
        if not isrc:
            raise HTTPException(status_code=400, detail="No ISRCs specified")
        
        if len(isrc) > 1000:
            raise HTTPException(status_code=400, detail="Maximum 1000 ISRCs per export")
        
        # For now, return JSON export
        # TODO: Implement CSV/XLSX export services
        export_data = {
            'export_timestamp': datetime.now().isoformat(),
            'format': format,
            'isrc_count': len(isrc),
            'isrcs': isrc,
            'note': f'{format.upper()} export functionality pending implementation'
        }
        
        if format == "json":
            return export_data
        else:
            raise HTTPException(
                status_code=501, 
                detail=f"{format.upper()} export not yet implemented"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Export error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Enhanced health check endpoint"""
    try:
        import time
        uptime = time.time() - app.state.start_time if hasattr(app.state, 'start_time') else 0
        
        health_status = {
            'status': 'healthy',
            'service': 'PRISM Analytics - ISRC Metadata Service',
            'version': '1.0.0',
            'timestamp': datetime.now().isoformat(),
            'uptime_seconds': uptime,
            'components': {
                'database': 'healthy' if db_manager else 'unavailable',
                'metadata_collector': 'healthy' if metadata_collector else 'unavailable',
                'api_clients': {}
            }
        }
        
        # Check API clients asynchronously
        if api_clients:
            try:
                client_status = await api_clients.validate_clients_async()
                health_status['components']['api_clients'] = client_status
            except Exception as e:
                health_status['components']['api_clients'] = {'error': str(e)}
        else:
            health_status['components']['api_clients'] = 'unavailable'
        
        # Determine overall status
        critical_components = ['database', 'metadata_collector']
        if any(health_status['components'][comp] == 'unavailable' 
               for comp in critical_components):
            health_status['status'] = 'degraded'
        
        return HealthResponse(**health_status)
        
    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")

@app.get("/api/stats")
async def get_statistics(db: DatabaseManager = Depends(get_db_manager)):
    """Get service statistics"""
    try:
        session = db.get_session()
        try:
            from src.models.database import Track, ExportHistory
            
            total_tracks = session.query(Track).count()
            high_confidence_tracks = session.query(Track).filter(
                Track.confidence_score >= 80
            ).count()
            
            recent_exports = session.query(ExportHistory).filter(
                ExportHistory.status == 'completed'
            ).count()
            
            stats = {
                'total_tracks_analyzed': total_tracks,
                'high_confidence_tracks': high_confidence_tracks,
                'confidence_rate': (high_confidence_tracks / total_tracks * 100) if total_tracks > 0 else 0,
                'total_exports': recent_exports,
                'timestamp': datetime.now().isoformat()
            }
            
            return stats
            
        finally:
            db.close_session(session)
            
    except Exception as e:
        logger.error(f"❌ Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Error handlers
@app.exception_handler(404)
async def not_found_handler(request, exc):
    return {"error": "Endpoint not found", "detail": str(exc)}

@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logger.error(f"Internal server error: {exc}")
    return {"error": "Internal server error", "detail": str(exc)}

# Development server startup
if __name__ == "__main__":
    config = Config()
    
    # Store start time for uptime calculation
    app.state.start_time = datetime.now().timestamp()
    
    logger.info("🎵 PRISM Analytics - ISRC Metadata Service")
    logger.info("Transforming Music Data into Actionable Insights")
    logger.info(f"Starting server on http://{config.HOST}:{config.PORT}")
    
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=config.DEBUG,
        log_level="info"
    )