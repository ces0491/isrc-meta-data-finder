#!/usr/bin/env python3
"""
PRISM Analytics - Simple Working FastAPI App
Focus on functionality over perfect type annotations
"""
# type: ignore

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel, validator
import logging
from datetime import datetime
import asyncio
import uvicorn
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Configure logging
logging.basicConfig(level=logging.INFO)
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
        # Initialize components with error handling
        try:
            from src.models.database import DatabaseManager, init_database
            init_database()
            db_manager = DatabaseManager()
            logger.info("✅ Database initialized")
        except Exception as e:
            logger.error(f"❌ Database init failed: {e}")
            db_manager = None
        
        try:
            from src.services.api_clients import APIClientManager
            from config.settings import Config
            
            config = Config()
            api_config = {
                'SPOTIFY_CLIENT_ID': getattr(config, 'SPOTIFY_CLIENT_ID', None),
                'SPOTIFY_CLIENT_SECRET': getattr(config, 'SPOTIFY_CLIENT_SECRET', None),
                'YOUTUBE_API_KEY': getattr(config, 'YOUTUBE_API_KEY', None),
                'LASTFM_API_KEY': getattr(config, 'LASTFM_API_KEY', None),
                'LASTFM_SHARED_SECRET': getattr(config, 'LASTFM_SHARED_SECRET', None)
            }
            
            api_clients = APIClientManager(api_config)
            logger.info("✅ API clients initialized")
        except Exception as e:
            logger.error(f"❌ API clients init failed: {e}")
            api_clients = None
        
        try:
            if api_clients and db_manager:
                from src.services.metadata_collector_async import AsyncMetadataCollector
                metadata_collector = AsyncMetadataCollector(api_clients, db_manager)
                logger.info("✅ Metadata collector initialized")
        except Exception as e:
            logger.error(f"❌ Metadata collector init failed: {e}")
            metadata_collector = None
        
        # Store in app state
        app.state.db_manager = db_manager
        app.state.api_clients = api_clients
        app.state.metadata_collector = metadata_collector
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down")

# Create FastAPI app
app = FastAPI(
    title="PRISM Analytics - ISRC Metadata Service",
    description="ISRC metadata aggregation microservice",
    version="1.0.0",
    lifespan=lifespan
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Simple Pydantic models (no complex validation)
class ISRCRequest(BaseModel):
    isrc: str
    comprehensive: bool = True
    
    @validator('isrc')
    def validate_isrc(cls, v):
        v = v.upper().strip()
        if len(v) != 12:
            raise ValueError('ISRC must be 12 characters')
        return v

class BulkRequest(BaseModel):
    isrc_list: list
    comprehensive: bool = False

# Simple dependency functions
def get_metadata_collector():
    if not metadata_collector:
        raise HTTPException(status_code=503, detail="Service not available")
    return metadata_collector

def get_db_manager():
    if not db_manager:
        raise HTTPException(status_code=503, detail="Database not available")
    return db_manager

# Routes
@app.get("/")
async def root():
    """Main page"""
    try:
        with open("templates/index.html", "r") as f:
            return HTMLResponse(content=f.read())
    except:
        return HTMLResponse(
            content="<h1>PRISM Analytics</h1><p>API docs: <a href='/docs'>/docs</a></p>"
        )

@app.post("/api/analyze-isrc-enhanced")
async def analyze_isrc(
    request: ISRCRequest,
    collector = Depends(get_metadata_collector)
):
    """Analyze single ISRC"""
    try:
        logger.info(f"🎵 Analyzing ISRC: {request.isrc}")
        
        result = await collector.analyze_isrc_async(
            isrc=request.isrc,
            comprehensive=request.comprehensive
        )
        
        return {
            'isrc': request.isrc,
            'metadata': {
                'title': result.get('title'),
                'artist': result.get('artist'),
                'album': result.get('album'),
                'duration_ms': result.get('duration_ms'),
                'release_date': result.get('release_date')
            },
            'audio_features': result.get('audio_features', {}),
            'platform_ids': result.get('platform_ids', {}),
            'confidence_score': result.get('confidence_score', 0.0),
            'data_completeness': result.get('data_completeness', 0.0),
            'status': 'success'
        }
        
    except Exception as e:
        logger.error(f"❌ Analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/bulk-metadata-analysis")
async def bulk_analyze(
    request: BulkRequest,
    collector = Depends(get_metadata_collector)
):
    """Bulk ISRC analysis"""
    try:
        logger.info(f"📊 Bulk analyzing {len(request.isrc_list)} ISRCs")
        
        results, errors = await collector.bulk_analyze_async(
            isrc_list=request.isrc_list,
            comprehensive=request.comprehensive
        )
        
        return {
            'total_requested': len(request.isrc_list),
            'processed': len(results),
            'failed': len(errors),
            'results': results,
            'errors': errors,
            'status': 'completed'
        }
        
    except Exception as e:
        logger.error(f"❌ Bulk analysis failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/track/{isrc}/metadata")
async def get_track_metadata(
    isrc: str,
    db = Depends(get_db_manager),
    collector = Depends(get_metadata_collector)
):
    """Get cached metadata"""
    try:
        isrc = isrc.upper().strip()
        
        session = db.get_session()
        try:
            from src.models.database import Track
            track = session.query(Track).filter(Track.isrc == isrc).first()
            
            if not track:
                raise HTTPException(status_code=404, detail="Track not found")
            
            return collector._track_to_dict(track)
            
        finally:
            db.close_session(session)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Metadata retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def health_check():
    """Health check"""
    try:
        status = {
            'status': 'healthy',
            'service': 'PRISM Analytics',
            'version': '1.0.0',
            'timestamp': datetime.now().isoformat(),
            'components': {
                'database': 'healthy' if db_manager else 'unavailable',
                'metadata_collector': 'healthy' if metadata_collector else 'unavailable',
                'api_clients': 'healthy' if api_clients else 'unavailable'
            }
        }
        
        return status
        
    except Exception as e:
        logger.error(f"❌ Health check error: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }

@app.get("/api/stats")
async def get_stats(db = Depends(get_db_manager)):
    """Get statistics"""
    try:
        session = db.get_session()
        try:
            from src.models.database import Track
            
            total_tracks = session.query(Track).count()
            high_confidence = session.query(Track).filter(Track.confidence_score >= 80).count()
            
            return {
                'total_tracks_analyzed': total_tracks,
                'high_confidence_tracks': high_confidence,
                'confidence_rate': (high_confidence / total_tracks * 100) if total_tracks > 0 else 0,
                'timestamp': datetime.now().isoformat()
            }
            
        finally:
            db.close_session(session)
            
    except Exception as e:
        logger.error(f"❌ Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Development server
if __name__ == "__main__":
    logger.info("🎵 PRISM Analytics - Starting Development Server")
    
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=5000,
        reload=True,
        log_level="info"
    )