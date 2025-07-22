#!/usr/bin/env python3
"""
PRISM Analytics - FastAPI Application Runner
Production-ready ISRC metadata aggregation microservice
"""
import uvicorn
import logging
import sys
import os
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import get_config
from main import app

def setup_logging(config):
    """Configure application logging"""
    
    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure logging format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # File handler
    file_handler = logging.FileHandler(config.LOG_FILE)
    file_handler.setFormatter(logging.Formatter(log_format))
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(logging.Formatter(log_format))
    
    # Root logger configuration
    logging.basicConfig(
        level=getattr(logging, config.LOG_LEVEL, logging.INFO),
        handlers=[file_handler, console_handler],
        format=log_format
    )
    
    # Reduce noise from external libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    logger = logging.getLogger(__name__)
    logger.info(f"📋 Logging configured - Level: {config.LOG_LEVEL}")
    
    return logger

def validate_environment():
    """Validate required environment configuration"""
    from config.settings import Config
    
    validation = Config.validate_required_config()
    
    print("\n🔧 PRISM Analytics Configuration Validation")
    print("=" * 60)
    
    critical_issues = []
    
    for service, status in validation.items():
        if "configured" in status or "created" in status:
            status_icon = "✅"
        elif "Missing" in status or "error" in status.lower():
            status_icon = "❌"
            critical_issues.append(f"{service}: {status}")
        else:
            status_icon = "⚠️"
            
        print(f"{status_icon} {service.capitalize()}: {status}")
    
    if critical_issues:
        print(f"\n❌ Critical configuration issues found:")
        for issue in critical_issues:
            print(f"   • {issue}")
        print("\n⚠️  Some features may not work properly.")
        print("   Check your .env file and API credentials.")
    
    print("\n" + "=" * 60)
    
    return len(critical_issues) == 0

def run_development():
    """Run in development mode with auto-reload"""
    config = get_config('development')
    logger = setup_logging(config)
    
    logger.info("🚀 Starting PRISM Analytics in DEVELOPMENT mode")
    logger.info("🎵 ISRC Metadata Aggregation Microservice")
    logger.info("📊 Transforming Music Data into Actionable Insights")
    logger.info(f"🌐 Server will start at http://{config.HOST}:{config.PORT}")
    logger.info("📚 API Documentation: http://127.0.0.1:5000/docs")
    logger.info("📖 Alternative docs: http://127.0.0.1:5000/redoc")
    
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
        reload_dirs=["src", "config", "templates", "static"],
        log_level="info",
        access_log=True
    )

def run_production():
    """Run in production mode"""
    config = get_config('production')
    logger = setup_logging(config)
    
    logger.info("🚀 Starting PRISM Analytics in PRODUCTION mode")
    logger.info("🎵 ISRC Metadata Aggregation Microservice")
    
    # Production configuration
    uvicorn.run(
        "main:app",
        host=config.HOST,
        port=config.PORT,
        workers=4,  # Multiple worker processes
        log_level="info",
        access_log=True,
        proxy_headers=True,
        forwarded_allow_ips="*"
    )

def run_with_gunicorn():
    """Run with Gunicorn for production (Linux/Unix only)"""
    config = get_config('production')
    
    gunicorn_config = {
        'bind': f"{config.HOST}:{config.PORT}",
        'workers': 4,
        'worker_class': 'uvicorn.workers.UvicornWorker',
        'worker_connections': 1000,
        'max_requests': 10000,
        'max_requests_jitter': 1000,
        'timeout': 120,
        'keepalive': 5,
        'access_logfile': 'logs/access.log',
        'error_logfile': 'logs/error.log',
        'log_level': 'info'
    }
    
    print("🚀 Starting with Gunicorn for production...")
    print("   Use this for production deployments on Linux/Unix systems")
    
    os.execvp('gunicorn', [
        'gunicorn',
        'main:app',
        f'--bind={gunicorn_config["bind"]}',
        f'--workers={gunicorn_config["workers"]}',
        f'--worker-class={gunicorn_config["worker_class"]}',
        f'--worker-connections={gunicorn_config["worker_connections"]}',
        f'--max-requests={gunicorn_config["max_requests"]}',
        f'--timeout={gunicorn_config["timeout"]}',
        f'--access-logfile={gunicorn_config["access_logfile"]}',
        f'--error-logfile={gunicorn_config["error_logfile"]}',
        f'--log-level={gunicorn_config["log_level"]}'
    ])

def main():
    """Main entry point with environment detection"""
    
    # Validate environment first
    config_ok = validate_environment()
    
    if not config_ok:
        print("\n⚠️  Continuing with partial configuration...")
        print("   Some features may not work properly.\n")
    
    # Determine run mode
    env = os.getenv('FLASK_ENV', 'development').lower()
    run_mode = sys.argv[1] if len(sys.argv) > 1 else env
    
    if run_mode in ['dev', 'development']:
        run_development()
    elif run_mode in ['prod', 'production']:
        run_production()
    elif run_mode == 'gunicorn':
        run_with_gunicorn()
    else:
        print("🤔 Unknown run mode. Available options:")
        print("   python run.py dev        - Development mode with auto-reload")
        print("   python run.py prod       - Production mode with uvicorn")
        print("   python run.py gunicorn   - Production mode with gunicorn")
        print("\nEnvironment variables:")
        print("   FLASK_ENV=development    - Default development mode")
        print("   FLASK_ENV=production     - Default production mode")
        
        # Default to development
        print("\n🚀 Defaulting to development mode...")
        run_development()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n👋 PRISM Analytics stopped by user")
    except Exception as e:
        print(f"\n❌ Failed to start PRISM Analytics: {e}")
        sys.exit(1)