#!/bin/bash

# PRISM Analytics - Deployment Helper Script
# This script prepares your project for Render deployment

echo "🎵 PRISM Analytics - Deployment Preparation"
echo "=========================================="

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Check if Python is installed
echo "Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d " " -f 2)
    print_success "Python $PYTHON_VERSION found"
else
    print_error "Python 3 not found. Please install Python 3.11+"
    exit 1
fi

# Check if git is initialized
echo "Checking Git..."
if [ -d .git ]; then
    print_success "Git repository found"
else
    print_warning "Git not initialized. Initializing..."
    git init
    print_success "Git initialized"
fi

# Update requirements.txt if needed
echo "Checking requirements.txt..."
if [ -f requirements.txt ]; then
    # Check if psycopg2-binary is in requirements
    if grep -q "psycopg2-binary" requirements.txt; then
        print_success "PostgreSQL support already in requirements.txt"
    else
        print_warning "Adding PostgreSQL support to requirements.txt"
        echo "psycopg2-binary==2.9.7" >> requirements.txt
        print_success "Added psycopg2-binary to requirements.txt"
    fi
else
    print_error "requirements.txt not found!"
    exit 1
fi

# Check for render.yaml
echo "Checking render.yaml..."
if [ -f render.yaml ]; then
    print_success "render.yaml found"
else
    print_error "render.yaml not found! Please create it from the template provided"
    exit 1
fi

# Check for database.py
echo "Checking database configuration..."
if [ -f src/models/database.py ]; then
    # Check if the file has PostgreSQL support
    if grep -q "postgresql+psycopg2" src/models/database.py; then
        print_success "Database has PostgreSQL support"
    else
        print_warning "Database may need PostgreSQL support updates"
        echo "Please ensure src/models/database.py has been updated with PostgreSQL support"
    fi
else
    print_error "src/models/database.py not found!"
    exit 1
fi

# Create .gitignore if it doesn't exist
echo "Checking .gitignore..."
if [ -f .gitignore ]; then
    print_success ".gitignore found"
else
    print_warning "Creating .gitignore"
    cat > .gitignore << 'EOF'
# Python
__pycache__/
*.py[cod]
.env
.venv
venv/
data/*.db
data/cache/*
data/exports/*
logs/*.log
.DS_Store
EOF
    print_success ".gitignore created"
fi

# Check for .env file
echo "Checking environment configuration..."
if [ -f .env ]; then
    print_success ".env file found"
    print_warning "Remember to set environment variables in Render Dashboard, not .env file"
else
    print_warning ".env file not found (this is OK for production)"
fi

# Create init_db.py if it doesn't exist
echo "Checking database initialization script..."
if [ -f init_db.py ]; then
    print_success "init_db.py found"
else
    print_warning "init_db.py not found - you'll need to initialize the database manually after deployment"
fi

# Test imports
echo "Testing Python imports..."
python3 -c "import fastapi; print('  ✓ FastAPI')" 2>/dev/null || print_error "FastAPI not installed"
python3 -c "import uvicorn; print('  ✓ Uvicorn')" 2>/dev/null || print_error "Uvicorn not installed"
python3 -c "import sqlalchemy; print('  ✓ SQLAlchemy')" 2>/dev/null || print_error "SQLAlchemy not installed"
python3 -c "import spotipy; print('  ✓ Spotipy')" 2>/dev/null || print_error "Spotipy not installed"

# Git status
echo ""
echo "Git Status:"
git status --short

# Ready check
echo ""
echo "=========================================="
echo "Deployment Readiness Check Complete!"
echo ""

# Check if all critical files exist
READY=true
[ ! -f render.yaml ] && READY=false && print_error "Missing: render.yaml"
[ ! -f requirements.txt ] && READY=false && print_error "Missing: requirements.txt"
[ ! -f run.py ] && READY=false && print_error "Missing: run.py"
[ ! -f src/models/database.py ] && READY=false && print_error "Missing: src/models/database.py"

if [ "$READY" = true ]; then
    print_success "✨ Your project is ready for deployment!"
    echo ""
    echo "Next steps:"
    echo "1. Commit your changes:"
    echo "   git add ."
    echo "   git commit -m 'Prepare for Render deployment'"
    echo ""
    echo "2. Push to GitHub:"
    echo "   git remote add origin https://github.com/YOUR_USERNAME/prism-analytics.git"
    echo "   git push -u origin main"
    echo ""
    echo "3. Deploy on Render:"
    echo "   - Go to https://dashboard.render.com"
    echo "   - Click 'New +' → 'Blueprint'"
    echo "   - Connect your GitHub repository"
    echo "   - Add your API keys in the Dashboard"
    echo ""
    echo "4. After deployment, initialize the database:"
    echo "   - Go to Render Dashboard → Your Service → Shell"
    echo "   - Run: python init_db.py"
else
    print_error "❌ Some files are missing. Please fix the issues above."
    exit 1
fi