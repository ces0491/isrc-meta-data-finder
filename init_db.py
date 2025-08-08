#!/usr/bin/env python3
"""
Database initialization script for PRISM Analytics
Run this after deployment to initialize database tables
"""

import os
import sys
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_database():
    """Initialize database tables"""
    try:
        # Update DATABASE_URL for SQLAlchemy if needed
        db_url = os.getenv('DATABASE_URL', '')
        if db_url and db_url.startswith('postgresql://'):
            os.environ['DATABASE_URL'] = db_url.replace('postgresql://', 'postgresql+psycopg2://', 1)
            logger.info("✅ Updated DATABASE_URL for PostgreSQL compatibility")
        
        # Import and initialize database
        from src.models.database import DatabaseManager
        
        logger.info("🔧 Initializing database...")
        db = DatabaseManager()
        
        logger.info("📊 Creating tables...")
        db.create_tables()
        
        logger.info("🔍 Testing connection...")
        if db.test_connection():
            logger.info("✅ Database connection successful!")
        else:
            logger.error("❌ Database connection failed!")
            return False
        
        # Get statistics
        stats = db.get_stats()
        logger.info("\n📊 Database Statistics:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value}")
        
        logger.info("\n✅ Database initialization completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Database initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = init_database()
    sys.exit(0 if success else 1)