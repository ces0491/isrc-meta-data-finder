"""
ISRC Meta Data Finder - API Clients
Complete implementation with modern Python 3.11 type hints
"""

import base64
import hashlib
import logging
import time
import requests
import asyncio
from datetime import datetime, timedelta
from threading import Lock
from typing import Any
from urllib.parse import quote

logger = logging.getLogger(__name__)


class RateLimiter:
    """Thread-safe rate limiter"""
    
    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = requests_per_minute
        self.request_times: list[float] = []
        self.lock = Lock()
    
    def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded"""
        with self.lock:
            now = time.time()
            # Clean old requests (older than 60 seconds)
            self.request_times = [t for t in self.request_times if now - t < 60]
            
            if len(self.request_times) >= self.requests_per_minute:
                # Calculate how long to wait
                sleep_time = 60 - (now - self.request_times[0])
                if sleep_time > 0:
                    logger.info(f"Rate limiting: waiting {sleep_time:.1f} seconds")
                    time.sleep(sleep_time)
            
            self.request_times.append(now)


class SpotifyClient:
    """Spotify Web API client with full functionality"""
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token: str | None = None
        self.token_expires: datetime | None = None
        self.rate_limiter = RateLimiter(100)  # Spotify allows ~180 req/min
        self.base_url = "https://api.spotify.com/v1"
    
    def _get_access_token(self) -> str:
        """Get or refresh access token"""
        # Check if we have a valid token
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token
        
        # Get new token
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = auth_string.encode("utf-8")
        auth_b64 = base64.b64encode(auth_bytes).decode("utf-8")
        
        headers = {
            "Authorization": f"Basic {auth_b64}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {"grant_type": "client_credentials"}
        
        try:
            response = requests.post(
                "https://accounts.spotify.com/api/token",
                headers=headers,
                data=data,
                timeout=10
            )
            
            if response.status_code != 200:
                raise Exception(f"Spotify auth failed: {response.status_code}")
            
            token_data = response.json()
            access_token = token_data["access_token"]  # Store in a local variable
            self.access_token = access_token           # Assign to the instance
            expires_in = token_data.get("expires_in", 3600)
            self.token_expires = datetime.now() + timedelta(seconds=expires_in - 60)

            logger.info("✅ Spotify token obtained successfully")
            return access_token # Return the local variable
            
        except Exception as e:
            logger.error(f"Failed to get Spotify token: {e}")
            raise
    
    def _make_request(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Make authenticated API request"""
        self.rate_limiter.wait_if_needed()
        
        headers = {
            "Authorization": f"Bearer {self._get_access_token()}",
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "1"))
                logger.warning(f"Spotify rate limited, waiting {retry_after} seconds")
                time.sleep(retry_after)
                return self._make_request(endpoint, params)
            
            if response.status_code == 404:
                return None  # Not found is not an error
            
            if response.status_code != 200:
                logger.error(f"Spotify API error: {response.status_code} - {response.text}")
                return None
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Spotify request failed: {e}")
            return None
    
    def search_by_isrc(self, isrc: str) -> dict[str, Any] | None:
        """Search for track by ISRC"""
        params = {
            "q": f"isrc:{isrc}",
            "type": "track",
            "limit": 1
        }
        
        result = self._make_request("/search", params)
        
        if result and result.get("tracks", {}).get("items"):
            return result["tracks"]["items"][0]
        
        return None
    
    def get_audio_features(self, track_id: str) -> dict[str, Any] | None:
        """Get audio features for a track"""
        return self._make_request(f"/audio-features/{track_id}")
    
    def get_track(self, track_id: str) -> dict[str, Any] | None:
        """Get detailed track information"""
        return self._make_request(f"/tracks/{track_id}")


class YouTubeClient:
    """YouTube Data API v3 client"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.rate_limiter = RateLimiter(100)  # Conservative rate limiting
    
    def search_by_isrc(self, isrc: str, track_title: str | None = None, 
                      artist: str | None = None) -> dict[str, Any] | None:
        """Search for music video by ISRC"""
        self.rate_limiter.wait_if_needed()
        
        # Build search query
        if track_title and artist:
            query = f'"{artist}" "{track_title}"'
        else:
            query = f'"{isrc}"'
        
        params = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "videoCategoryId": "10",  # Music category
            "maxResults": 5,
            "key": self.api_key
        }
        
        try:
            response = requests.get(f"{self.base_url}/search", params=params, timeout=10)
            
            if response.status_code != 200:
                logger.error(f"YouTube search failed: {response.status_code}")
                return None
            
            data = response.json()
            
            # Look for ISRC in video descriptions
            if data.get("items"):
                for item in data["items"]:
                    snippet = item.get("snippet", {})
                    description = snippet.get("description", "").upper()
                    
                    # Check if ISRC is mentioned in description
                    if isrc in description:
                        return self._get_video_details(item["id"]["videoId"])
                
                # If no exact match, return first result
                if data["items"]:
                    return self._get_video_details(data["items"][0]["id"]["videoId"])
            
            return None
            
        except Exception as e:
            logger.error(f"YouTube search error: {e}")
            return None
    
    def _get_video_details(self, video_id: str) -> dict[str, Any] | None:
        """Get detailed video information including statistics"""
        self.rate_limiter.wait_if_needed()
        
        params = {
            "part": "snippet,statistics,contentDetails",
            "id": video_id,
            "key": self.api_key
        }
        
        try:
            response = requests.get(f"{self.base_url}/videos", params=params, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("items"):
                    return data["items"][0]
            
            return None
            
        except Exception as e:
            logger.error(f"YouTube video details error: {e}")
            return None


class MusicBrainzClient:
    """MusicBrainz API client"""
    
    def __init__(self):
        self.base_url = "https://musicbrainz.org/ws/2"
        self.rate_limiter = RateLimiter(50)  # MusicBrainz: 1 req/sec avg
        self.headers = {
            "User-Agent": "PRISM-Analytics/2.0 (https://precise.digital)"
        }
    
    def search_recording_by_isrc(self, isrc: str) -> dict[str, Any] | None:
        """Search for recording by ISRC"""
        self.rate_limiter.wait_if_needed()
        
        params = {
            "query": f"isrc:{isrc}",
            "fmt": "json",
            "inc": "artist-credits+releases+isrcs"
        }
        
        try:
            response = requests.get(
                f"{self.base_url}/recording/",
                params=params,
                headers=self.headers,
                timeout=15
            )
            
            if response.status_code == 503:
                logger.warning("MusicBrainz service temporarily unavailable")
                time.sleep(2)
                return None
            
            if response.status_code != 200:
                logger.error(f"MusicBrainz error: {response.status_code}")
                return None
            
            data = response.json()
            
            if data.get("recordings"):
                return data["recordings"][0]
            
            return None
            
        except Exception as e:
            logger.error(f"MusicBrainz request error: {e}")
            return None
    
    def get_recording(self, recording_id: str) -> dict[str, Any] | None:
        """Get detailed recording information"""
        self.rate_limiter.wait_if_needed()
        
        params = {
            "fmt": "json",
            "inc": "artist-credits+releases+isrcs+work-rels+artist-rels"
        }
        
        try:
            response = requests.get(
                f"{self.base_url}/recording/{recording_id}",
                params=params,
                headers=self.headers,
                timeout=15
            )
            
            if response.status_code == 200:
                return response.json()
            
            return None
            
        except Exception as e:
            logger.error(f"MusicBrainz recording error: {e}")
            return None


class GeniusClient:
    """Genius API client for lyrics and credits"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.genius.com"
        self.rate_limiter = RateLimiter(100)
        self.headers = {
            "Authorization": f"Bearer {api_key}"
        }
    
    def search_song(self, title: str, artist: str) -> dict[str, Any] | None:
        """Search for a song on Genius"""
        self.rate_limiter.wait_if_needed()
        
        params = {
            "q": f"{title} {artist}"
        }
        
        try:
            response = requests.get(
                f"{self.base_url}/search",
                headers=self.headers,
                params=params,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Genius search failed: {response.status_code}")
                return None
            
            data = response.json()
            hits = data.get("response", {}).get("hits", [])
            
            if hits:
                # Return the most relevant result
                return hits[0]["result"]
            
            return None
            
        except Exception as e:
            logger.error(f"Genius search error: {e}")
            return None
    
    def get_song_details(self, song_id: int) -> dict[str, Any] | None:
        """Get detailed song information including credits"""
        self.rate_limiter.wait_if_needed()
        
        try:
            response = requests.get(
                f"{self.base_url}/songs/{song_id}",
                headers=self.headers,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()["response"]["song"]
            
            return None
            
        except Exception as e:
            logger.error(f"Genius song details error: {e}")
            return None


class LastFmClient:
    """Last.fm API client for music metadata and social listening data"""
    
    def __init__(self, api_key: str, shared_secret: str):
        self.api_key = api_key
        self.shared_secret = shared_secret
        self.base_url = "http://ws.audioscrobbler.com/2.0/"
        self.rate_limiter = RateLimiter(60)
    
    def _make_request(self, params: dict[str, Any]) -> dict[str, Any] | None:
        """Make a request to Last.fm API"""
        self.rate_limiter.wait_if_needed()
        
        # Add API key and format to all requests
        params['api_key'] = self.api_key
        params['format'] = 'json'
        
        try:
            response = requests.get(
                self.base_url,
                params=params,
                timeout=10
            )
            
            if response.status_code == 429:
                logger.warning("Last.fm rate limited, waiting 60 seconds")
                time.sleep(60)
                return self._make_request(params)
            
            if response.status_code != 200:
                logger.error(f"Last.fm API error: {response.status_code} - {response.text}")
                return None
            
            data = response.json()
            
            if 'error' in data:
                logger.error(f"Last.fm API error: {data.get('message', 'Unknown error')}")
                return None
            
            return data
            
        except Exception as e:
            logger.error(f"Last.fm request failed: {e}")
            return None
    
    def search_track(self, title: str, artist: str, limit: int = 5) -> dict[str, Any] | None:
        """Search for a track on Last.fm"""
        params = {
            'method': 'track.search',
            'track': title,
            'artist': artist,
            'limit': limit
        }
        
        result = self._make_request(params)
        
        if result and 'results' in result:
            tracks = result['results'].get('trackmatches', {}).get('track', [])
            if tracks:
                if isinstance(tracks, list) and len(tracks) > 0:
                    return tracks[0]
                elif isinstance(tracks, dict):
                    return tracks
        
        return None
    
    def get_track_info(self, artist: str, track: str, username: str | None = None) -> dict[str, Any] | None:
        """Get detailed track information including play count and listeners"""
        params = {
            'method': 'track.getInfo',
            'artist': artist,
            'track': track,
            'autocorrect': '1'
        }
        
        if username:
            params['username'] = username
        
        result = self._make_request(params)
        
        if result and 'track' in result:
            return result['track']
        
        return None
    
    def get_track_tags(self, artist: str, track: str) -> list[dict[str, Any]] | None:
        """Get top tags for a track"""
        params = {
            'method': 'track.getTopTags',
            'artist': artist,
            'track': track,
            'autocorrect': '1'
        }
        
        result = self._make_request(params)
        
        if result and 'toptags' in result:
            return result['toptags'].get('tag', [])
        
        return None
    
    def get_similar_tracks(self, artist: str, track: str, limit: int = 10) -> list[dict[str, Any]] | None:
        """Get similar tracks"""
        params = {
            'method': 'track.getSimilar',
            'artist': artist,
            'track': track,
            'limit': limit,
            'autocorrect': '1'
        }
        
        result = self._make_request(params)
        
        if result and 'similartracks' in result:
            return result['similartracks'].get('track', [])
        
        return None
    
    def get_artist_info(self, artist: str) -> dict[str, Any] | None:
        """Get detailed artist information"""
        params = {
            'method': 'artist.getInfo',
            'artist': artist,
            'autocorrect': '1'
        }
        
        result = self._make_request(params)
        
        if result and 'artist' in result:
            return result['artist']
        
        return None
    
    def get_album_info(self, artist: str, album: str) -> dict[str, Any] | None:
        """Get detailed album information"""
        params = {
            'method': 'album.getInfo',
            'artist': artist,
            'album': album,
            'autocorrect': '1'
        }
        
        result = self._make_request(params)
        
        if result and 'album' in result:
            return result['album']
        
        return None
    
    def search_by_mbid(self, mbid: str) -> dict[str, Any] | None:
        """Search for a track by MusicBrainz ID"""
        params = {
            'method': 'track.getInfo',
            'mbid': mbid
        }
        
        result = self._make_request(params)
        
        if result and 'track' in result:
            return result['track']
        
        return None
    
    def get_chart_top_tracks(self, limit: int = 50) -> list[dict[str, Any]] | None:
        """Get top tracks chart"""
        params = {
            'method': 'chart.getTopTracks',
            'limit': limit
        }
        
        result = self._make_request(params)
        
        if result and 'tracks' in result:
            return result['tracks'].get('track', [])
        
        return None


class DiscogsClient:
    """Discogs API client for detailed release and label information"""
    
    def __init__(self, user_token: str):
        self.user_token = user_token
        self.base_url = "https://api.discogs.com"
        self.rate_limiter = RateLimiter(60)
        self.headers = {
            "Authorization": f"Discogs token={user_token}",
            "User-Agent": "PRISM-Analytics/2.0"
        }
    
    def _make_request(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any] | None:
        """Make a request to Discogs API"""
        self.rate_limiter.wait_if_needed()
        
        url = f"{self.base_url}{endpoint}"
        
        try:
            response = requests.get(
                url,
                headers=self.headers,
                params=params,
                timeout=15
            )
            
            remaining = response.headers.get('X-Discogs-Ratelimit-Remaining')
            if remaining and int(remaining) < 5:
                logger.warning(f"Discogs rate limit low: {remaining} requests remaining")
                time.sleep(1)
            
            if response.status_code == 429:
                logger.warning("Discogs rate limited, waiting 60 seconds")
                time.sleep(60)
                return self._make_request(endpoint, params)
            
            if response.status_code == 404:
                return None
            
            if response.status_code != 200:
                logger.error(f"Discogs API error: {response.status_code} - {response.text}")
                return None
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Discogs request failed: {e}")
            return None
    
    def search_release(self, title: str, artist: str, type: str = "release") -> dict[str, Any] | None:
        """Search for a release on Discogs"""
        params = {
            'title': title,
            'artist': artist,
            'type': type,
            'per_page': 10
        }
        
        result = self._make_request("/database/search", params)
        
        if result and 'results' in result and result['results']:
            return result['results'][0]
        
        return None
    
    def search_by_barcode(self, barcode: str) -> dict[str, Any] | None:
        """Search for a release by barcode/UPC"""
        params = {
            'barcode': barcode,
            'type': 'release',
            'per_page': 10
        }
        
        result = self._make_request("/database/search", params)
        
        if result and 'results' in result and result['results']:
            return result['results'][0]
        
        return None
    
    def search_by_catno(self, catalog_number: str, label: str | None = None) -> dict[str, Any] | None:
        """Search for a release by catalog number"""
        params = {
            'catno': catalog_number,
            'type': 'release',
            'per_page': 10
        }
        
        if label:
            params['label'] = label
        
        result = self._make_request("/database/search", params)
        
        if result and 'results' in result and result['results']:
            return result['results'][0]
        
        return None
    
    def get_release(self, release_id: int) -> dict[str, Any] | None:
        """Get detailed release information"""
        return self._make_request(f"/releases/{release_id}")
    
    def get_master_release(self, master_id: int) -> dict[str, Any] | None:
        """Get master release information"""
        return self._make_request(f"/masters/{master_id}")
    
    def get_release_versions(self, master_id: int) -> list[dict[str, Any]] | None:
        """Get all versions of a master release"""
        result = self._make_request(f"/masters/{master_id}/versions")
        
        if result and 'versions' in result:
            return result['versions']
        
        return None
    
    def get_artist(self, artist_id: int) -> dict[str, Any] | None:
        """Get detailed artist information"""
        return self._make_request(f"/artists/{artist_id}")
    
    def get_artist_releases(self, artist_id: int, page: int = 1, per_page: int = 50) -> list[dict[str, Any]] | None:
        """Get all releases by an artist"""
        params = {
            'page': page,
            'per_page': per_page,
            'sort': 'year',
            'sort_order': 'desc'
        }
        
        result = self._make_request(f"/artists/{artist_id}/releases", params)
        
        if result and 'releases' in result:
            return result['releases']
        
        return None
    
    def get_label(self, label_id: int) -> dict[str, Any] | None:
        """Get detailed label information"""
        return self._make_request(f"/labels/{label_id}")
    
    def get_label_releases(self, label_id: int, page: int = 1, per_page: int = 50) -> list[dict[str, Any]] | None:
        """Get all releases from a label"""
        params = {
            'page': page,
            'per_page': per_page
        }
        
        result = self._make_request(f"/labels/{label_id}/releases", params)
        
        if result and 'releases' in result:
            return result['releases']
        
        return None
    
    def extract_credits_from_release(self, release_data: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract and format credits from a release"""
        credits: list[dict[str, Any]] = []
        
        # Extract artists
        if 'artists' in release_data:
            for artist in release_data['artists']:
                credits.append({
                    'name': artist.get('name', ''),
                    'credit_type': 'main_artist',
                    'source': 'discogs',
                    'source_confidence': 0.9
                })
        
        # Extract extra artists
        if 'extraartists' in release_data:
            for artist in release_data['extraartists']:
                credits.append({
                    'name': artist.get('name', ''),
                    'credit_type': artist.get('role', 'contributor').lower().replace(' ', '_'),
                    'role_details': artist.get('role', ''),
                    'source': 'discogs',
                    'source_confidence': 0.85
                })
        
        # Extract track-level credits
        if 'tracklist' in release_data:
            for track in release_data['tracklist']:
                if 'extraartists' in track:
                    for artist in track['extraartists']:
                        credits.append({
                            'name': artist.get('name', ''),
                            'credit_type': f"track_{artist.get('role', 'contributor').lower().replace(' ', '_')}",
                            'role_details': f"{artist.get('role', '')} on {track.get('title', 'track')}",
                            'source': 'discogs',
                            'source_confidence': 0.8
                        })
        
        # Remove duplicates
        seen = set()
        unique_credits: list[dict[str, Any]] = []
        for credit in credits:
            credit_key = f"{credit['name']}_{credit['credit_type']}"
            if credit_key not in seen:
                seen.add(credit_key)
                unique_credits.append(credit)
        
        return unique_credits


class APIClientManager:
    """Centralized API client manager"""
    
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.spotify: SpotifyClient | None = None
        self.youtube: YouTubeClient | None = None
        self.musicbrainz: MusicBrainzClient | None = None
        self.genius: GeniusClient | None = None
        self.lastfm: LastFmClient | None = None
        self.discogs: DiscogsClient | None = None
        
        # Initialize clients based on available credentials
        self._initialize_clients()
    
    def _initialize_clients(self) -> None:
        """Initialize all configured API clients"""
        
        # Spotify
        if self.config.get("SPOTIFY_CLIENT_ID") and self.config.get("SPOTIFY_CLIENT_SECRET"):
            try:
                self.spotify = SpotifyClient(
                    self.config["SPOTIFY_CLIENT_ID"],
                    self.config["SPOTIFY_CLIENT_SECRET"]
                )
                logger.info("✅ Spotify client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Spotify: {e}")
        
        # YouTube
        if self.config.get("YOUTUBE_API_KEY"):
            try:
                self.youtube = YouTubeClient(self.config["YOUTUBE_API_KEY"])
                logger.info("✅ YouTube client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize YouTube: {e}")
        
        # MusicBrainz (no auth required)
        try:
            self.musicbrainz = MusicBrainzClient()
            logger.info("✅ MusicBrainz client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize MusicBrainz: {e}")
        
        # Genius
        if self.config.get("GENIUS_API_KEY"):
            try:
                self.genius = GeniusClient(self.config["GENIUS_API_KEY"])
                logger.info("✅ Genius client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Genius: {e}")
        
        # Last.fm
        if self.config.get("LASTFM_API_KEY") and self.config.get("LASTFM_SHARED_SECRET"):
            try:
                self.lastfm = LastFmClient(
                    self.config["LASTFM_API_KEY"],
                    self.config["LASTFM_SHARED_SECRET"]
                )
                logger.info("✅ Last.fm client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Last.fm: {e}")
        
        # Discogs - Fixed initialization
        discogs_token = self.config.get("DISCOGS_USER_TOKEN") or self.config.get("DISCOGS_API_KEY")
        if discogs_token and isinstance(discogs_token, str):
            try:
                self.discogs = DiscogsClient(discogs_token)
                logger.info("✅ Discogs client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Discogs: {e}")
        else:
            logger.info("Discogs client not configured (no valid token found)")
    
    def validate_clients(self) -> dict[str, str]:
        """Check which clients are available"""
        status = {}
        
        # Check each client
        status["spotify"] = "operational" if self.spotify else "not configured"
        status["youtube"] = "operational" if self.youtube else "not configured"
        status["musicbrainz"] = "operational" if self.musicbrainz else "not configured"
        status["genius"] = "operational" if self.genius else "not configured"
        status["lastfm"] = "operational" if self.lastfm else "not configured"
        status["discogs"] = "operational" if self.discogs else "not configured"
        
        return status
    
    async def validate_clients_async(self) -> dict[str, str]:
        """Async version of validate_clients"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.validate_clients)
    
    def get_available_clients(self) -> list[str]:
        """Get list of available client names"""
        available = []
        
        if self.spotify:
            available.append("spotify")
        if self.youtube:
            available.append("youtube")
        if self.musicbrainz:
            available.append("musicbrainz")
        if self.genius:
            available.append("genius")
        if self.lastfm:
            available.append("lastfm")
        if self.discogs:
            available.append("discogs")
        
        return available


# Export all clients
__all__ = [
    'RateLimiter',
    'SpotifyClient',
    'YouTubeClient',
    'MusicBrainzClient',
    'GeniusClient',
    'LastFmClient',
    'DiscogsClient',
    'APIClientManager'
]