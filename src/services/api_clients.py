# type: ignore
"""
PRISM Analytics - Simple API Clients
Focus on working functionality over perfect types
"""
import requests
import time
import base64
from datetime import datetime, timedelta
from threading import Lock
import json
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """Simple rate limiter"""
    
    def __init__(self, requests_per_minute):
        self.requests_per_minute = requests_per_minute
        self.request_times = []
        self.lock = Lock()
        
    def wait_if_needed(self):
        """Wait if needed"""
        with self.lock:
            now = time.time()
            # Clean old requests
            self.request_times = [t for t in self.request_times if now - t < 60]
            
            if len(self.request_times) >= self.requests_per_minute:
                sleep_time = 60 - (now - self.request_times[0])
                if sleep_time > 0:
                    logger.info(f"Rate limiting: sleeping {sleep_time:.1f} seconds")
                    time.sleep(sleep_time)
                    
            self.request_times.append(now)

# src/services/api_clients.py - Add YouTube client
class YouTubeClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.rate_limiter = RateLimiter(100)  # Adjust based on quota
    
    def search_by_isrc(self, isrc):
        self.rate_limiter.wait_if_needed()
        params = {
            'part': 'snippet,contentDetails',
            'q': f'"{isrc}"',  # Search for ISRC in description
            'type': 'video',
            'videoCategoryId': '10',  # Music category
            'maxResults': 5,
            'key': self.api_key
        }
        response = requests.get(f"{self.base_url}/search", params=params)
        if response.status_code == 200:
            return response.json()
        return None

class SpotifyClient:
    """Simple Spotify client"""
    
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expires = None
        self.rate_limiter = RateLimiter(100)
        
    def _get_access_token(self):
        """Get access token"""
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token
            
        # Get new token
        auth_string = f"{self.client_id}:{self.client_secret}"
        auth_bytes = auth_string.encode('utf-8')
        auth_b64 = base64.b64encode(auth_bytes).decode('utf-8')
        
        headers = {
            'Authorization': f'Basic {auth_b64}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {'grant_type': 'client_credentials'}
        
        response = requests.post('https://accounts.spotify.com/api/token', 
                               headers=headers, data=data)
        
        if response.status_code != 200:
            raise Exception(f"Spotify auth failed: {response.text}")
            
        token_data = response.json()
        self.access_token = token_data['access_token']
        expires_in = token_data['expires_in']
        self.token_expires = datetime.now() + timedelta(seconds=expires_in - 60)
        
        logger.info("✅ Spotify token obtained")
        return self.access_token
        
    def _make_request(self, endpoint, params=None):
        """Make API request"""
        self.rate_limiter.wait_if_needed()
        
        headers = {
            'Authorization': f'Bearer {self._get_access_token()}',
            'Content-Type': 'application/json'
        }
        
        url = f"https://api.spotify.com/v1{endpoint}"
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', '1'))
            logger.warning(f"Spotify rate limited, waiting {retry_after} seconds")
            time.sleep(retry_after)
            return self._make_request(endpoint, params)
            
        if response.status_code != 200:
            logger.error(f"Spotify API error: {response.status_code}")
            return None
            
        return response.json()
        
    def search_by_isrc(self, isrc):
        """Search by ISRC"""
        params = {
            'q': f'isrc:{isrc}',
            'type': 'track',
            'limit': 1
        }
        return self._make_request('/search', params)
        
    def get_audio_features(self, track_id):
        """Get audio features"""
        return self._make_request(f'/audio-features/{track_id}')

class MusicBrainzClient:
    """Simple MusicBrainz client"""
    
    def __init__(self):
        self.rate_limiter = RateLimiter(60)  # Conservative
        self.headers = {
            'User-Agent': 'PRISM-Analytics/1.0'
        }
        
    def _make_request(self, endpoint, params):
        """Make request"""
        self.rate_limiter.wait_if_needed()
        
        params['fmt'] = 'json'
        url = f"https://musicbrainz.org/ws/2{endpoint}"
        
        response = requests.get(url, params=params, headers=self.headers)
        
        if response.status_code == 503:
            logger.warning("MusicBrainz unavailable")
            time.sleep(2)
            return None
            
        if response.status_code != 200:
            logger.error(f"MusicBrainz error: {response.status_code}")
            return None
            
        try:
            return response.json()
        except:
            return None
        
    def search_recording_by_isrc(self, isrc):
        """Search by ISRC"""
        params = {
            'query': f'isrc:{isrc}',
            'inc': 'artist-credits+releases'
        }
        return self._make_request('/recording/', params)

# src/services/api_clients.py
class GeniusClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.base_url = "https://api.genius.com"
        self.rate_limiter = RateLimiter(100)
        
    def search_song(self, title, artist):
        self.rate_limiter.wait_if_needed()
        headers = {'Authorization': f'Bearer {self.api_key}'}
        params = {'q': f'{title} {artist}'}
        
        response = requests.get(
            f"{self.base_url}/search",
            headers=headers,
            params=params
        )
        
        if response.status_code == 200:
            data = response.json()
            hits = data.get('response', {}).get('hits', [])
            if hits:
                return hits[0]['result']
        return None

class APIClientManager:
    """Simple API client manager"""
    
    def __init__(self, config):
        self.spotify = None
        self.musicbrainz = MusicBrainzClient()
        
        # Only create clients if we have credentials
        if config.get('SPOTIFY_CLIENT_ID') and config.get('SPOTIFY_CLIENT_SECRET'):
            self.spotify = SpotifyClient(
                config['SPOTIFY_CLIENT_ID'],
                config['SPOTIFY_CLIENT_SECRET']
            )
        
        # Add other clients as needed
        self.youtube = None  # Placeholder
        self.lastfm = None   # Placeholder
        
    def validate_clients(self):
        """Check which clients work"""
        status = {}
        
        if self.spotify:
            try:
                self.spotify._get_access_token()
                status['spotify'] = 'available'
            except Exception as e:
                status['spotify'] = f'error: {str(e)}'
        else:
            status['spotify'] = 'not configured'
            
        status['musicbrainz'] = 'available'
        status['youtube'] = 'not configured'
        status['lastfm'] = 'not configured'
        
        return status
        
    async def validate_clients_async(self):
        """Async version"""
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.validate_clients)