# PRISM Analytics Engine - Usage Guide

## Metadata Intelligence Platform for Music Industry Professionals

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Understanding ISRCs](#understanding-isrcs)
3. [Web Interface Guide](#web-interface-guide)
4. [API Integration](#api-integration)
5. [Understanding Results](#understanding-results)
6. [Bulk Operations](#bulk-operations)
7. [Export Formats](#export-formats)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)
10. [API Rate Limits](#api-rate-limits)

---

## Quick Start

### Accessing the Platform

1. **Web Interface**: Navigate to `http://localhost:5000` (development) or your production URL
2. **API Documentation**: Access interactive docs at `/api/docs`
3. **Health Check**: Verify system status at `/api/health`

### First Analysis

1. Enter an ISRC code (e.g., `USRC17607839`)
2. Select analysis options:
   - ✅ **Include Lyrics & Credits** - Retrieves songwriter and producer information
   - ✅ **Comprehensive Analysis** - Performs deep metadata collection
   - ⬜ **Force Refresh** - Bypasses cache for fresh data
3. Click **ANALYZE METADATA**
4. Review results and export as needed

---

## Understanding ISRCs

### What is an ISRC?

The **International Standard Recording Code** (ISRC) is a unique 12-character identifier for audio recordings.

### ISRC Format

```text

US-RC1-76-07839
│  │   │  └─ Designation Code (5 digits)
│  │   └──── Year of Reference (2 digits)  
│  └──────── Registrant Code (3 alphanumeric)
└─────────── Country Code (2 letters)
```

**Example**: `USRC17607839`

- **US**: United States
- **RC1**: Registrant code
- **76**: Year 1976 or 2076
- **07839**: Unique designation

### Valid ISRC Patterns

✅ **Valid**:

- `USRC17607839`
- `GBUM71505080`
- `DEUM21900123`

❌ **Invalid**:

- `US-RC1-76-07839` (contains hyphens)
- `USRC176078` (too short)
- `12RC17607839` (starts with numbers)

---

## Web Interface Guide

### System Status Dashboard

The top section displays real-time metrics:

| Metric | Description |
|--------|-------------|
| **Total Tracks** | Number of tracks in database |
| **Avg Confidence** | Average metadata confidence score |
| **With Lyrics** | Tracks with lyrics data |
| **API Calls Today** | Daily API usage count |

### API Status Indicators

- **Active (Black badge)**: API is configured and operational
- **Inactive (Gray badge)**: API not configured or unavailable
- **Pulsing dot**: Real-time connection active

### Single ISRC Analysis

#### Input Options

1. **ISRC Code Field**
   - Auto-formats to uppercase
   - Removes invalid characters
   - Validates format in real-time

2. **Analysis Options**

   | Option | Purpose | Impact on Speed |
   |--------|---------|-----------------|
   | Include Lyrics & Credits | Fetches Genius data | +2-3 seconds |
   | Comprehensive Analysis | All available sources | +3-5 seconds |
   | Force Refresh | Bypasses cache | +1-2 seconds |

#### Results Display

The results section shows:

- **Confidence Score**: Overall data quality (0-100%)
- **Quality Rating**: Excellent / Good / Fair / Poor
- **Metadata Fields**: All retrieved information
- **Export Options**: Platform-specific links and downloads

---

## API Integration

### Authentication

No authentication required for local development. For production, set API keys in environment variables.

### Core Endpoints

#### 1. Single ISRC Analysis

```bash
POST /api/analyze-enhanced
Content-Type: application/json

{
  "isrc": "USRC17607839",
  "include_lyrics": true,
  "include_credits": true,
  "force_refresh": false
}
```

**Response**:

```json
{
  "isrc": "USRC17607839",
  "title": "Track Title",
  "artist": "Artist Name",
  "album": "Album Name",
  "confidence": 92.5,
  "quality_rating": "Excellent",
  "sources": ["Spotify", "MusicBrainz", "YouTube", "Genius"],
  "spotify_id": "4iV5W9uYEdYUVa79Axb7Rh",
  "tempo": 120.0,
  "key": 5,
  "energy": 0.75,
  "processing_time_ms": 1234
}
```

#### 2. Bulk Analysis

```bash
POST /api/bulk-analyze
Content-Type: application/json

{
  "isrcs": ["USRC17607839", "GBUM71505080"],
  "comprehensive": false
}
```

#### 3. Export Endpoints

```bash
# CSV Export
GET /api/bulk-csv?isrcs=USRC17607839,GBUM71505080

# Excel Export with formatting
GET /api/bulk-excel?isrcs=USRC17607839,GBUM71505080

# JSON Export
GET /api/export/json?isrcs=USRC17607839,GBUM71505080
```

---

## Understanding Results

### Confidence Score Calculation

The 8-factor weighted scoring system evaluates:

| Factor | Weight | Description |
|--------|--------|-------------|
| **Data Sources** | 25% | Number of APIs returning data |
| **Essential Fields** | 20% | Title, artist, album, duration, release date |
| **Audio Features** | 15% | Tempo, key, energy, danceability, valence |
| **External IDs** | 10% | Spotify ID, MusicBrainz ID, YouTube ID |
| **Popularity Metrics** | 10% | Streaming counts, view counts |
| **Lyrics Availability** | 10% | Lyrics and language detection |
| **Credits Completeness** | 5% | Songwriter, producer credits |
| **Cross-validation** | 5% | Data consistency across sources |

### Quality Ratings

| Rating | Score Range | Interpretation |
|--------|-------------|----------------|
| **Excellent** | 90-100% | High confidence, multiple sources agree |
| **Good** | 75-89% | Reliable data, minor gaps |
| **Fair** | 60-74% | Usable data, some missing elements |
| **Poor** | 40-59% | Limited data, needs verification |
| **Insufficient** | <40% | Unreliable, manual review required |

### Data Sources

| Source | Type | Provides |
|--------|------|----------|
| **Spotify** | Streaming | Audio features, popularity, IDs |
| **MusicBrainz** | Database | Credits, recordings, releases |
| **YouTube** | Video | View counts, video IDs |
| **Genius** | Lyrics | Lyrics, songwriter credits |
| **Last.fm** | Social | Tags, listening stats |
| **Discogs** | Database | Release info, credits |

---

## Bulk Operations

### Preparing Bulk Data

#### Input Formats

**Comma-separated**:

```text
USRC17607839,GBUM71505080,DEUM21900123
```

**Line-separated**:

```text
USRC17607839
GBUM71505080
DEUM21900123
```

**Mixed (with spaces)**:

```text
USRC17607839, GBUM71505080
DEUM21900123 FRFR21800456
```

### Upload Limits

| Tier | Max ISRCs | Processing Time |
|------|-----------|-----------------|
| **Single** | 1 | ~2-5 seconds |
| **Batch** | 10 | ~20-30 seconds |
| **Bulk** | 100 | ~2-3 minutes |
| **Enterprise** | 1000+ | ~15-20 minutes |

### CSV Upload

```bash
POST /api/upload/csv
Content-Type: multipart/form-data

File: catalog.csv
```

**CSV Format**:

```csv
ISRC,Title,Artist
USRC17607839,Track 1,Artist 1
GBUM71505080,Track 2,Artist 2
```

---

## Export Formats

### CSV Export

**Best for**: Spreadsheet analysis, data import

```csv
# PRISM Metadata Export
# Generated: 2025-01-15 10:30:00
# Total Records: 3
#
ISRC,Title,Artist,Album,Duration_MS,Confidence_Score
USRC17607839,Song Title,Artist Name,Album Name,234000,92.5
```

### Excel Export

**Best for**: Professional reports, multi-sheet analysis

Features:

- **Sheet 1**: Track Metadata with color-coded confidence
- **Sheet 2**: Summary statistics and charts
- **Sheet 3**: Quality distribution analysis
- PRISM branding and formatting
- Hyperlinks to streaming platforms

### JSON Export

**Best for**: API integration, database import

```json
{
  "export_date": "2025-01-15T10:30:00Z",
  "total_records": 3,
  "results": [
    {
      "isrc": "USRC17607839",
      "metadata": {...},
      "confidence_score": 92.5,
      "sources": ["Spotify", "MusicBrainz"]
    }
  ]
}
```

---

## Best Practices

### For Record Labels

1. **Catalog Audit**
   - Process entire catalog quarterly
   - Focus on tracks with <70% confidence
   - Verify new releases before distribution

2. **Quality Control**

   ```text
   Confidence > 90%: Ready for distribution
   Confidence 70-90%: Review metadata
   Confidence < 70%: Manual verification required
   ```

3. **Missing Data Priority**
   - Credits (highest royalty impact)
   - Audio features (playlist placement)
   - YouTube IDs (video monetization)

### For Publishers

1. **Rights Verification**
   - Check songwriter credits monthly
   - Validate publishing splits
   - Monitor territory availability

2. **Royalty Optimization**
   - Focus on tracks missing credits
   - Verify composer information
   - Update PRO registrations

### For Distributors

1. **Pre-Release Checks**
   - Validate all metadata 48 hours before release
   - Ensure platform IDs are present
   - Check for duplicate ISRCs

2. **Platform Coverage**

   ```text
   Essential: Spotify, Apple Music, YouTube
   Important: Amazon, Deezer, Tidal
   Regional: Platform-specific requirements
   ```

---

## Troubleshooting

### Common Issues

#### "Invalid ISRC Format"

**Problem**: ISRC contains invalid characters or wrong length

**Solution**:

- Remove hyphens and spaces
- Ensure exactly 12 characters
- Use uppercase letters

**Example Fix**:

```text
Wrong: us-rc1-76-07839
Right: USRC17607839
```

#### "No Data Found"

**Possible Causes**:

1. ISRC not registered in any database
2. Very new release (not yet indexed)
3. Regional restrictions
4. Private/unreleased track

**Solutions**:

- Verify ISRC with distributor
- Wait 24-48 hours for new releases
- Try alternative ISRC if available

#### Low Confidence Scores

**Common Reasons**:

- Limited platform availability
- Missing audio features
- No credits information
- Inconsistent metadata

**Improvement Steps**:

1. Register with MusicBrainz
2. Ensure Spotify distribution
3. Add credits to Genius
4. Update YouTube Content ID

### API Errors

| Error Code | Meaning | Solution |
|------------|---------|----------|
| 400 | Invalid request | Check ISRC format |
| 404 | Not found | Verify ISRC exists |
| 429 | Rate limited | Wait before retry |
| 500 | Server error | Contact support |
| 503 | Service unavailable | Try again later |

---

## API Rate Limits

### Per-Service Limits

| Service | Requests/Min | Daily Limit | Notes |
|---------|--------------|-------------|-------|
| **Spotify** | 180 | Unlimited* | Token refresh every hour |
| **YouTube** | 100 | 10,000 quota | Cost varies by endpoint |
| **MusicBrainz** | 50 | Unlimited | 1 req/sec average |
| **Genius** | 100 | Unlimited* | Requires API key |
| **Last.fm** | 60 | Unlimited* | Optional service |
| **Discogs** | 60 | Unlimited* | User token required |

*Subject to fair use policies

### Rate Limit Handling

The system automatically:

1. Queues requests when limits approached
2. Implements exponential backoff
3. Caches results for 24 hours
4. Prioritizes essential data sources

### Optimization Tips

1. **Use Caching**
   - Default cache: 24 hours
   - Force refresh only when needed
   - Bulk process during off-peak hours

2. **Batch Processing**
   - Group ISRCs by 10-20
   - Process overnight for large catalogs
   - Use async endpoints for bulk operations

3. **Priority Management**

   ```text
   High Priority: New releases, high-value tracks
   Medium Priority: Catalog updates, quarterly audits
   Low Priority: Historical data, archived content
   ```

---

## Support & Resources

### Documentation

- **API Reference**: `/api/docs`
- **GitHub**: [https://github.com/ces0491/isrc-meta-data-finder](https://github.com/ces0491/isrc-meta-data-finder)

### Response Times

- **Critical Issues**: 2 hours
- **Standard Support**: 24 hours
- **Feature Requests**: 48-72 hours

### System Requirements

- **Browser**: Chrome 90+, Firefox 88+, Safari 14+
- **API**: REST, JSON responses
- **Export**: CSV, Excel, JSON formats
- **Database**: PostgreSQL 12+ (production)

---

## Appendix: Field Definitions

| Field | Type | Description | Example |
|-------|------|-------------|---------|
| `isrc` | string | International Standard Recording Code | USRC17607839 |
| `title` | string | Track title | "Bohemian Rhapsody" |
| `artist` | string | Primary artist name | "Queen" |
| `album` | string | Album title | "A Night at the Opera" |
| `duration_ms` | integer | Track length in milliseconds | 354000 |
| `release_date` | string | Release date (YYYY-MM-DD) | "1975-10-31" |
| `tempo` | float | Beats per minute | 72.5 |
| `key` | integer | Musical key (0-11) | 5 |
| `mode` | integer | Major (1) or Minor (0) | 1 |
| `energy` | float | Energy level (0.0-1.0) | 0.75 |
| `danceability` | float | Danceability score (0.0-1.0) | 0.45 |
| `valence` | float | Musical positivity (0.0-1.0) | 0.33 |
| `popularity` | integer | Popularity score (0-100) | 89 |
| `spotify_id` | string | Spotify track ID | "4iV5W9uYEdYUVa79Axb7Rh" |
| `youtube_video_id` | string | YouTube video ID | "dQw4w9WgXcQ" |
| `musicbrainz_recording_id` | string | MusicBrainz ID | "b1234567-89ab-cdef" |

---
