# 🎵 Music Metadata Intelligence System

![PRISM Analytics](https://img.shields.io/badge/PRISM-Analytics-E50914?style=for-the-badge&logo=music&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.8+-1A1A1A?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.104.1-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Status](https://img.shields.io/badge/Status-Production_Ready-28a745?style=for-the-badge)

Metadata aggregation tool using ISRC codes.

## ✨ Key Features

- 🎵 **Multi-Source Aggregation**: Spotify, YouTube, MusicBrainz, Genius, Last FM and Discogs
- 📊 **8-Factor Confidence Scoring**: Metadata quality assessment
- 💾 **Persistent Storage**: SQLite/PostgreSQL with full ORM support
- ⚡ **Async Processing**: Parallel data collection
- 📈 **Multiple Export Formats**: CSV, Excel, JSON
- 🎨 **Web Interface**: Intuitive, responsive UI
- 📝 **Lyrics & Credits**: Songwriter and producer credits
- 🔧 **RESTful API**: Full OpenAPI documentation
- 🚦 **Rate Limiting**: Responsible API usage with automatic throttling
- 📦 **Bulk Operations**: Process hundreds of ISRCs efficiently

## 📊 Data Sources

| Source | Data Types | Authentication Required |
|--------|------------|------------------------|
| **Spotify** | Audio features, popularity, album info | ✅ Client ID & Secret |
| **MusicBrainz** | Recording details, artist credits | ❌ No auth required |
| **YouTube** | Video views, channel info | ✅ API Key |
| **Genius** | Lyrics, songwriter credits | ✅ API Key |
| **Musixmatch** | Lyrics, translations | ✅ API Key |
| **Last.fm** | Tags, listening statistics | ✅ API Key |
| **Discogs** | Label info, release details | ✅ User Token |

## 🚀 Quick Start

### Prerequisites

- Python 3.11 or higher
- pip (Python package manager)
- At least one API key (Spotify minimum)

### 1. Clone & Setup

```bash

# Clone the repository

git clone https://github.com/ces0491/isrc-meta-data-finder.git
cd isrc-meta-data-finder

# Run automated setup

python setup.py

```

The setup script will:

- Check Python version
- Install all dependencies
- Create directory structure
- Generate `.env` configuration file
- Initialize the database
- Test API connections

### 2. Configure API Keys

Edit `.env` and add your API credentials:

```env

# Required for basic functionality

SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

# Optional but recommended

YOUTUBE_API_KEY=your_youtube_api_key
GENIUS_API_KEY=your_genius_api_key

# Optional

LASTFM_API_KEY=your_lastfm_api_key
DISCOGS_USER_TOKEN=your_discogs_token

*MusicBrainz does not require an API key*

```

#### Getting API Keys

- **Spotify**: [Spotify for Developers](https://developer.spotify.com/dashboard) (FREE)
- **YouTube**: [Google Cloud Console](https://console.cloud.google.com/) (FREE with limits)
- **Genius**: [Genius API](https://genius.com/api-clients) (FREE)
- **Last.fm**: [Last.fm API](https://www.last.fm/api/account/create) (FREE)

### 3. Start the Server

```bash

python run.py

```

The server will start at:

- 🌐 **Web Interface**: [http://localhost:5000](http://localhost:5000)
- 📚 **API Documentation**: [http://localhost:5000/api/docs](http://localhost:5000/api/docs)
- 💚 **Health Check**: [http://localhost:5000/api/health](http://localhost:5000/api/health)

## 📊 API Usage

### Analyze Single ISRC

```bash

curl -X POST "http://localhost:5000/api/analyze-enhanced" \
  -H "Content-Type: application/json" \
  -d '{
    "isrc": "USRC17607839",
    "include_lyrics": true,
    "include_credits": true
  }'

```

#### Response Example

```json

{
  "isrc": "USRC17607839",
  "title": "Track Title",
  "artist": "Artist Name",
  "album": "Album Name",
  "confidence": 92.5,
  "confidence_details": {
    "quality_rating": "Excellent",
    "score_breakdown": {
      "data_sources": 95.0,
      "essential_fields": 100.0,
      "audio_features": 85.0
    }
  },
  "sources": ["Spotify", "MusicBrainz", "YouTube", "Genius"],
  "spotify_id": "4iV5W9uYEdYUVa79Axb7Rh",
  "youtube_video_id": "dQw4w9WgXcQ",
  "tempo": 120.0,
  "key": 5,
  "energy": 0.75,
  "processing_time_ms": 1234
}

```

### Bulk Export

```bash

# CSV Export

curl "http://localhost:5000/api/bulk-csv?isrcs=USRC17607839,GBUM71505080" \
  --output isrc_meta_data_export.csv

# Excel Export (with formatting and summary)

curl "http://localhost:5000/api/bulk-excel?isrcs=USRC17607839,GBUM71505080" \
  --output isrc_meta_data_export.xlsx

```text

### Search Database

```bash

curl "http://localhost:5000/api/search?q=Beatles&type=artist&limit=10"

```

## 🏗️ Project Structure

```text
isrc-meta-data-finder/
├── run.py                  # Main application entry point
├── setup.py                # Automated setup script
├── requirements.txt        # Python dependencies
├── .env                    # API keys and configuration
│
├── src/                    # Source code
│   ├── api/
│   │   └── routes.py       # API endpoint definitions
│   ├── models/
│   │   └── database.py     # SQLAlchemy ORM models
│   └── services/
│       ├── api_clients.py  # External API integrations
│       ├── metadata_collector_async.py  # Async data collection
│       └── export_services.py          # Export functionality
│
├── config/
│   └── settings.py         # Configuration management
│
├── templates/
│   └── index.html          # Web interface
│
├── static/
│   ├── css/
│   │   └── prism-theme.css # PRISM brand styling
│   └── js/
│       └── app.js          # Frontend functionality
│
└── data/
    ├── isrc_meta_data.db   # SQLite database
    ├── cache/              # API response cache
    └── exports/            # Generated export files

```

## 📈 Confidence Scoring System

The system uses an 8-factor weighted scoring algorithm:

| Factor | Weight | Description |
|--------|--------|-------------|
| Data Sources | 25% | Number of APIs returning data |
| Essential Fields | 20% | Title, artist, album, duration, release date |
| Audio Features | 15% | Tempo, key, energy, danceability, valence |
| External IDs | 10% | Spotify ID, MusicBrainz ID, YouTube ID |
| Popularity Metrics | 10% | Streaming counts, view counts |
| Lyrics Availability | 10% | Lyrics and language detection |
| Credits Completeness | 5% | Songwriter, producer credits |
| Cross-validation | 5% | Data consistency across sources |

### Quality Ratings

- **Excellent** (90-100%): High confidence, multiple sources agree
- **Good** (75-89%): Reliable data, minor gaps
- **Fair** (60-74%): Usable data, some missing elements
- **Poor** (40-59%): Limited data, needs verification
- **Insufficient** (<40%): Unreliable, manual review required

## 🔧 Configuration

### Environment Variables

```env

# Server Configuration

HOST=127.0.0.1
PORT=5000
SECRET_KEY=your-secret-key-here

# Database (optional - defaults to SQLite)

DATABASE_URL=postgresql://user:pass@localhost/isrc_meta_data

# Cache Settings

CACHE_TTL_HOURS=24

# Rate Limiting (requests per minute)

SPOTIFY_RATE_LIMIT=180
YOUTUBE_RATE_LIMIT=100
MUSICBRAINZ_RATE_LIMIT=50

```

### Database Options

**SQLite** (Default):

- No configuration needed
- Perfect for development and small deployments
- Database file: `data/isrc_meta_data.db`

**PostgreSQL** (Production):

```bash

# Install PostgreSQL driver

pip install psycopg2-binary

# Set in .env

DATABASE_URL=postgresql://user:password@localhost:5432/isrc_meta_data

```

## 📊 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| **POST** | `/api/analyze-enhanced` | Comprehensive ISRC analysis |
| **GET** | `/api/track/{isrc}` | Get cached track metadata |
| **GET** | `/api/track/{isrc}/credits` | Get detailed credits |
| **GET** | `/api/track/{isrc}/lyrics` | Get lyrics and copyright info |
| **POST** | `/api/bulk-analyze` | Analyze multiple ISRCs |
| **GET** | `/api/bulk-csv` | Export to CSV |
| **GET** | `/api/bulk-excel` | Export to Excel with formatting |
| **GET** | `/api/search` | Search database |
| **GET** | `/api/stats` | Database statistics |
| **GET** | `/api/health` | Service health check |
| **DELETE** | `/api/cache/{isrc}` | Clear cached data |
| **POST** | `/api/upload/csv` | Upload CSV for batch processing |

Full API documentation available at: [http://localhost:5000/api/docs]

## 🎯 Use Cases

### Record Labels

- Catalog metadata audit and enrichment
- Missing metadata identification
- Multi-platform availability tracking
- Rights and credits verification

### Music Publishers

- Songwriter credit verification
- Publishing split validation
- Cross-platform royalty tracking
- Territory rights management

### Music Distributors

- Pre-release metadata validation
- Platform-specific formatting
- ISRC registration verification
- Catalog quality assurance

### Data Analysts

- Music industry trend analysis
- Artist performance metrics
- Genre classification studies
- Market intelligence gathering

## 🐛 Troubleshooting

### Common Issues

## 🔧 Authentication Issues

Based on your error logs, here's how to fix each API authentication issue:

### 1. Spotify API (403 Error)

```bash
# The 403 error indicates invalid or expired credentials
# Get new credentials from: https://developer.spotify.com/dashboard

# 1. Create a new app in Spotify Dashboard
# 2. Copy the Client ID and Client Secret
# 3. Update your .env file:
SPOTIFY_CLIENT_ID=your_new_client_id
SPOTIFY_CLIENT_SECRET=your_new_client_secret
```

### 2. YouTube API (400 Error)

```bash
# 400 error usually means invalid API key or quota exceeded
# Get a new API key from: https://console.cloud.google.com/

# 1. Create a new project in Google Cloud Console
# 2. Enable YouTube Data API v3
# 3. Create credentials (API Key)
# 4. Add to .env:
YOUTUBE_API_KEY=your_youtube_api_key
```

### 3. Discogs API (401 Error)

```bash
# You need a personal access token, not just an API key
# Get from: https://www.discogs.com/settings/developers

# 1. Sign in to Discogs
# 2. Go to Settings > Developers
# 3. Click "Generate new token"
# 4. Add to .env:
DISCOGS_USER_TOKEN=your_personal_token
```

#### ModuleNotFoundError

```bash

# Ensure you're in the project root

cd isrc-meta-data-finder

# Reinstall dependencies

pip install -r requirements.txt

```

#### Spotify API Error

```bash

# Check your credentials in .env

# Ensure no extra spaces or quotes

SPOTIFY_CLIENT_ID=abc123  # ✅ Correct
SPOTIFY_CLIENT_ID="abc123"  # ❌ Wrong

```

#### Database Lock Error

```bash

# Delete and recreate database

rm data/isrc_meta_data.db
python run.py  # Will auto-create new database

```

#### Port Already in Use

```bash

# Change port in .env

PORT=5001

# Or find and kill the process

lsof -i :5000  # Mac/Linux
netstat -ano | findstr :5000  # Windows

```

## 📈 Performance

- **Single ISRC Analysis**: ~2-5 seconds
- **Bulk Processing**: 100 ISRCs in ~2 minutes
- **Database Queries**: <100ms
- **Export Generation**: <5 seconds for 1000 records
- **API Rate Limits**: Automatically managed
- **Concurrent Requests**: Supports async processing

## 🛡️ Security & Compliance

- ✅ API keys stored in environment variables
- ✅ SQL injection protection via ORM
- ✅ Rate limiting on all endpoints
- ✅ CORS headers for web security
- ✅ Input validation on all endpoints
- ✅ Respectful API usage patterns
- ✅ GDPR compliant (no personal data storage)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

---

**Part of the PRISM Analytics Engine** - Transforming Music Data into Actionable Intelligence
