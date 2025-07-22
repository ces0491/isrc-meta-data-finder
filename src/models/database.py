# type: ignore
"""
PRISM Analytics - Simple Database Models
Focus on working functionality
"""
from datetime import datetime
from sqlalchemy import create_engine, Column, String, Integer, Float, DateTime, Text, JSON, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
import os

Base = declarative_base()

class Track(Base):
    """Main track metadata table"""
    __tablename__ = 'tracks'
    
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
    youtube_video_id = Column(String(20))
    musicbrainz_recording_id = Column(String(50))
    discogs_release_id = Column(Integer)
    
    # Quality metrics
    confidence_score = Column(Float, default=0.0)
    data_completeness = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

class TrackCredit(Base):
    """Track credits"""
    __tablename__ = 'track_credits'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    isrc = Column(String(12), ForeignKey('tracks.isrc'), nullable=False)
    person_name = Column(String(255), nullable=False)
    credit_type = Column(String(50), nullable=False)
    role_details = Column(JSON)
    source_api = Column(String(50))
    source_confidence = Column(Float, default=0.0)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class TrackLyrics(Base):
    """Track lyrics"""
    __tablename__ = 'track_lyrics'
    
    isrc = Column(String(12), ForeignKey('tracks.isrc'), primary_key=True)
    lyrics_text = Column(Text)
    language_code = Column(String(5))
    copyright_info = Column(JSON)
    explicit_content = Column(Boolean, default=False)
    content_rating = Column(String(20))
    source_api = Column(String(50))
    source_url = Column(String(500))
    confidence_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class DatabaseManager:
    """Simple database manager"""
    
    def __init__(self, database_url=None):
        if database_url is None:
            # Default to SQLite
            db_path = os.path.join(os.path.dirname(__file__), '../../data/prism_analytics.db')
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            database_url = f'sqlite:///{db_path}'
        
        self.engine = create_engine(database_url, echo=False)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
    def create_tables(self):
        """Create all tables"""
        Base.metadata.create_all(bind=self.engine)
        
    def get_session(self):
        """Get database session"""
        return self.SessionLocal()
        
    def close_session(self, session):
        """Close database session"""
        session.close()

# Global database manager
db_manager = DatabaseManager()

def init_database():
    """Initialize database"""
    db_manager.create_tables()
    print("✅ Database initialized")

if __name__ == "__main__":
    init_database()