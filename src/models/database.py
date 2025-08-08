# src/models/database.py
# Production-ready database manager with PostgreSQL support for Render

import os
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    text,  # Added this import for SQL text execution
    inspect,  # Added for table inspection
    func,  # Added for SQL functions
)
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

Base = declarative_base()


class Track(Base):
    """Main track metadata table"""

    __tablename__ = "tracks"

    isrc = Column(String(12), primary_key=True)
    title = Column(String(500))
    artist = Column(String(500))
    album = Column(String(500))
    duration_ms = Column(Integer)
    release_date = Column(String(10))

    # Audio features
    key = Column(String(10))
    mode = Column(Integer)
    tempo = Column(Float)
    time_signature = Column(Integer)
    energy = Column(Float)
    danceability = Column(Float)
    valence = Column(Float)
    loudness = Column(Float)
    speechiness = Column(Float)
    acousticness = Column(Float)
    instrumentalness = Column(Float)
    liveness = Column(Float)

    # Platform IDs
    spotify_id = Column(String(50))
    spotify_url = Column(String(500))
    youtube_video_id = Column(String(20))
    youtube_url = Column(String(500))
    youtube_views = Column(Integer)
    musicbrainz_recording_id = Column(String(50))
    discogs_release_id = Column(Integer)

    # Popularity metrics
    popularity = Column(Integer)

    # Quality metrics
    confidence_score = Column(Float, default=0.0)
    data_completeness = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)


class TrackCredit(Base):
    """Track credits"""

    __tablename__ = "track_credits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    isrc = Column(String(12), ForeignKey("tracks.isrc"), nullable=False)
    person_name = Column(String(255), nullable=False)
    credit_type = Column(String(50), nullable=False)
    role_details = Column(JSON)
    source_api = Column(String(50))
    source_confidence = Column(Float, default=0.0)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TrackLyrics(Base):
    """Track lyrics"""

    __tablename__ = "track_lyrics"

    isrc = Column(String(12), ForeignKey("tracks.isrc"), primary_key=True)
    lyrics_text = Column(Text)
    genius_song_id = Column(Integer)
    genius_url = Column(String(500))
    language_code = Column(String(5))
    copyright_info = Column(JSON)
    explicit_content = Column(Boolean, default=False)
    content_rating = Column(String(20))
    source_api = Column(String(50))
    source_url = Column(String(500))
    confidence_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AnalysisHistory(Base):
    """Track analysis history for monitoring"""
    
    __tablename__ = "analysis_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    isrc = Column(String(12), ForeignKey("tracks.isrc"))
    analysis_type = Column(String(50))
    status = Column(String(20))
    confidence_score = Column(Float)
    processing_time_ms = Column(Integer)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)


class DatabaseManager:
    """Production-ready database manager with PostgreSQL support"""

    def __init__(self, database_url: Optional[str] = None):
        """
        Initialize database manager with automatic PostgreSQL/SQLite detection
        """
        if database_url is None:
            database_url = os.getenv("DATABASE_URL")
        
        # Check if we're in production (Render sets this)
        is_production = os.getenv("RENDER") is not None
        
        if database_url:
            # Render uses postgresql:// but SQLAlchemy needs postgresql+psycopg2://
            if database_url.startswith("postgresql://"):
                database_url = database_url.replace("postgresql://", "postgresql+psycopg2://", 1)
                logger.info("🐘 Using PostgreSQL database (production)")
                
                # Production engine configuration
                self.engine = create_engine(
                    database_url,
                    echo=False,  # Set to True for debugging
                    pool_size=5,  # Connection pool size
                    max_overflow=10,  # Maximum overflow connections
                    pool_pre_ping=True,  # Test connections before using
                    pool_recycle=300,  # Recycle connections after 5 minutes
                )
            else:
                # Non-PostgreSQL database URL
                logger.info("📦 Using provided database URL")
                self.engine = create_engine(database_url, echo=False)
        else:
            # Fallback to SQLite for local development
            db_dir = os.path.join(os.path.dirname(__file__), "../../data")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "isrc_meta_data.db")
            database_url = f"sqlite:///{db_path}"
            logger.info(f"💾 Using SQLite database (development): {db_path}")
            
            # SQLite engine configuration
            self.engine = create_engine(
                database_url,
                echo=False,
                connect_args={"check_same_thread": False},  # For SQLite
                poolclass=NullPool  # Disable pooling for SQLite
            )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine
        )
        
        # Store connection info
        self.database_url = database_url
        self.is_production = is_production
        
        # Log database type
        if "postgresql" in database_url:
            logger.info("✅ Connected to PostgreSQL database")
        else:
            logger.info("✅ Connected to SQLite database")

    def create_tables(self):
        """Create all tables in the database"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info("✅ Database tables created/verified successfully")
            
            # Verify tables were created
            inspector = inspect(self.engine)
            tables = inspector.get_table_names()
            logger.info(f"📊 Available tables: {', '.join(tables)}")
            
            return True
        except Exception as e:
            logger.error(f"❌ Failed to create tables: {e}")
            raise

    def get_session(self):
        """Get a new database session"""
        return self.SessionLocal()

    def close_session(self, session):
        """Close a database session"""
        try:
            session.close()
        except Exception as e:
            logger.error(f"Error closing session: {e}")

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            with self.engine.connect() as conn:
                # Fixed: Using text() function instead of Text class
                result = conn.execute(text("SELECT 1"))
                result.fetchone()
                logger.info("✅ Database connection test successful")
                return True
        except Exception as e:
            logger.error(f"❌ Database connection test failed: {e}")
            return False

    def get_stats(self) -> dict:
        """Get database statistics"""
        session = self.get_session()
        try:
            stats = {
                "total_tracks": session.query(Track).count(),
                "tracks_with_lyrics": session.query(TrackLyrics).count(),
                "total_credits": session.query(TrackCredit).count(),
                "analyses_performed": session.query(AnalysisHistory).count(),
                "database_type": "PostgreSQL" if "postgresql" in self.database_url else "SQLite",
                "is_production": self.is_production
            }
            
            # Average confidence score
            avg_confidence = session.query(func.avg(Track.confidence_score)).scalar()
            stats["avg_confidence"] = float(avg_confidence) if avg_confidence else 0.0
            
            # Platform coverage
            stats["spotify_coverage"] = session.query(Track).filter(
                Track.spotify_id.isnot(None)
            ).count()
            stats["youtube_coverage"] = session.query(Track).filter(
                Track.youtube_video_id.isnot(None)
            ).count()
            stats["musicbrainz_coverage"] = session.query(Track).filter(
                Track.musicbrainz_recording_id.isnot(None)
            ).count()
            
            return stats
        except Exception as e:
            logger.error(f"Error getting stats: {e}")
            return {
                "error": str(e),
                "database_type": "PostgreSQL" if "postgresql" in self.database_url else "SQLite"
            }
        finally:
            self.close_session(session)

    def cleanup_old_records(self, days: int = 30):
        """Clean up old analysis history records (for production)"""
        if not self.is_production:
            logger.info("Skipping cleanup in development mode")
            return
        
        session = self.get_session()
        try:
            from datetime import timedelta
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            deleted = session.query(AnalysisHistory).filter(
                AnalysisHistory.created_at < cutoff_date
            ).delete()
            
            session.commit()
            logger.info(f"🧹 Cleaned up {deleted} old analysis records")
            return deleted
        except Exception as e:
            session.rollback()
            logger.error(f"Cleanup failed: {e}")
            return 0
        finally:
            self.close_session(session)


# Global database manager instance
db_manager = None


def get_db_manager() -> DatabaseManager:
    """Get or create the global database manager"""
    global db_manager
    if db_manager is None:
        db_manager = DatabaseManager()
    return db_manager


def init_database():
    """Initialize database and create tables"""
    manager = get_db_manager()
    manager.create_tables()
    if manager.test_connection():
        stats = manager.get_stats()
        logger.info(f"📊 Database initialized with {stats.get('total_tracks', 0)} tracks")
        return True
    return False


if __name__ == "__main__":
    # Test database initialization
    logging.basicConfig(level=logging.INFO)
    
    print("🔧 Testing database configuration...")
    
    try:
        # Initialize database
        if init_database():
            print("✅ Database initialization successful!")
            
            # Get and display statistics
            manager = get_db_manager()
            stats = manager.get_stats()
            
            print("\n📊 Database Statistics:")
            for key, value in stats.items():
                print(f"  {key}: {value}")
        else:
            print("❌ Database initialization failed!")
    except Exception as e:
        print(f"❌ Error during initialization: {e}")
        import traceback
        traceback.print_exc()