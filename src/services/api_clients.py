"""
PRISM Analytics - API Clients
Authenticated clients for music metadata APIs with rate limiting
"""
import requests
import time
import base64
import hashlib
import hmac
from datetime import datetime, timedelta
from threading import Lock
from typing import Dict, Optional, Any
import json
import logging

logger = logging.getLogger(__name__)

class RateLimiter:
    """Thread-safe rate limiter for API requests"""
    
    def __init__(self, requests_per_minute: int, requests_per_second: float = None):
        self.requests_per_minute = requests_per_minute
        self.requests_per_second = requests_per_second
        self.request_times = []
        self.lock = Lock()
        
    def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        with self.lock:
            now = time.time()
            
            # Clean old requests (older than 1 minute)
            self.request_times = [t for t in self.request_times if now - t < 60]
            
            # Check per-minute limit
            if len(self.request_times) >= self.requests_per_minute:
                sleep_time = 60 - (now - self.request_times[0])
                if sleep_time > 0:
                    logger.info(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                    time.sleep(sleep_time)
                    
            # Check per-second limit
            if self.requests_per_second:
                recent_requests = [t for t in self.request_times if now - t < 1]
                if len(recent_requests) >= self.requests_per_second:
                    time.sleep(1.0 / self.requests_per_second)
                    
            self.request_times.append(now)

class SpotifyClient:
    """Spotify Web API client with OAuth2 authentication"""
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expires = None
        self.rate_limiter = RateLimiter(requests_per_minute=100)
        
        # Spotify uses different rate limits per endpoint
        self.search_limiter = RateLimiter(requests_per_second=10)
        self.track_limiter = RateLimiter(requests_per_second=20)
        
    def _get_access_token(self) -> str:
        """Get OAuth2 access token using client credentials flow"""
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token
            
        # Prepare authentication
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
        self.token_expires = datetime.now() + timedelta(seconds=expires_in - 60)  # 60s buffer
        
        logger.info("✅ Spotify access token obtained")
        return self.access_token
        
    def _make_request(self, endpoint: str, params: dict = None, limiter: RateLimiter = None) -> dict:
        """Make authenticated request to Spotify API"""
        if limiter is None:
            limiter = self.rate_limiter
            
        limiter.wait_if_needed()
        
        headers = {
            'Authorization': f'Bearer {self._get_access_token()}',
            'Content-Type': 'application/json'
        }
        
        url = f"https://api.spotify.com/v1{endpoint}"
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 429:  # Rate limited
            retry_after = int(response.headers.get('Retry-After', 1))
            logger.warning(f"Spotify rate limited, waiting {retry_after} seconds")
            time.sleep(retry_after)
            return self._make_request(endpoint, params, limiter)
            
        if response.status_code != 200:
            logger.error(f"Spotify API error: {response.status_code} - {response.text}")
            return None
            
        return response.json()
        
    def search_track(self, query: str, limit: int = 1) -> Optional[dict]:
        """Search for tracks on Spotify"""
        params = {
            'q': query,
            'type': 'track',
            'limit': limit
        }
        return self._make_request('/search', params, self.search_limiter)
        
    def get_track(self, track_id: str) -> Optional[dict]:
        """Get track details by Spotify ID"""
        return self._make_request(f'/tracks/{track_id}', limiter=self.track_limiter)
        
    def get_audio_features(self, track_id: str) -> Optional[dict]:
        """Get audio features for a track"""
        return self._make_request(f'/audio-features/{track_id}', limiter=self.track_limiter)
        
    def search_by_isrc(self, isrc: str) -> Optional[dict]:
        """Search for track by ISRC"""
        return self.search_track(f'isrc:{isrc}')

class YouTubeClient:
    """YouTube Data API v3 client"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.rate_limiter = RateLimiter(requests_per_minute=100)
        self.daily_quota = 10000  # YouTube has daily quota limits
        self.quota_used = 0
        
    def _make_request(self, endpoint: str, params: dict) -> Optional[dict]:
        """Make request to YouTube API"""
        if self.quota_used >= self.daily_quota:
            logger.error("YouTube API daily quota exceeded")
            return None
            
        self.rate_limiter.wait_if_needed()
        
        params['key'] = self.api_key
        url = f"https://www.googleapis.com/youtube/v3{endpoint}"
        
        response = requests.get(url, params=params)
        
        if response.status_code == 403:
            error_data = response.json()
            if 'quotaExceeded' in error_data.get('error', {}).get('message', ''):
                logger.error("YouTube API quota exceeded")
                self.quota_used = self.daily_quota
                return None
                
        if response.status_code != 200:
            logger.error(f"YouTube API error: {response.status_code} - {response.text}")
            return None
            
        # Estimate quota cost (search costs 100 units)
        self.quota_used += 100
        
        return response.json()
        
    def search_videos(self, query: str, max_results: int = 5) -> Optional[dict]:
        """Search for videos"""
        params = {
            'part': 'id,snippet',
            'q': query,
            'type': 'video',
            'maxResults': max_results
        }
        return self._make_request('/search', params)
        
    def get_video_details(self, video_id: str) -> Optional[dict]:
        """Get detailed video information"""
        params = {
            'part': 'snippet,statistics,contentDetails',
            'id': video_id
        }
        return self._make_request('/videos', params)

class LastFMClient:
    """Last.fm API client"""
    
    def __init__(self, api_key: str, shared_secret: str):
        self.api_key = api_key
        self.shared_secret = shared_secret
        self.rate_limiter = RateLimiter(requests_per_minute=60)
        
    def _generate_signature(self, params: dict) -> str:
        """Generate API signature for authenticated requests"""
        # Sort parameters and create signature string
        sorted_params = sorted(params.items())
        sig_string = ''.join([f"{k}{v}" for k, v in sorted_params])
        sig_string += self.shared_secret
        
        return hashlib.md5(sig_string.encode('utf-8')).hexdigest()
        
    def _make_request(self, method: str, params: dict, signed: bool = False) -> Optional[dict]:
        """Make request to Last.fm API"""
        self.rate_limiter.wait_if_needed()
        
        params.update({
            'method': method,
            'api_key': self.api_key,
            'format': 'json'
        })
        
        if signed:
            params['api_sig'] = self._generate_signature(params)
            
        response = requests.get('https://ws.audioscrobbler.com/2.0/', params=params)
        
        if response.status_code != 200:
            logger.error(f"Last.fm API error: {response.status_code} - {response.text}")
            return None
            
        data = response.json()
        if 'error' in data:
            logger.error(f"Last.fm API error: {data['error']} - {data.get('message', '')}")
            return None
            
        return data
        
    def get_track_info(self, artist: str, track: str) -> Optional[dict]:
        """Get track information"""
        params = {
            'artist': artist,
            'track': track
        }
        return self._make_request('track.getInfo', params)
        
    def get_track_tags(self, artist: str, track: str) -> Optional[dict]:
        """Get track tags"""
        params = {
            'artist': artist,
            'track': track
        }
        return self._make_request('track.getTopTags', params)

class MusicBrainzClient:
    """MusicBrainz API client"""
    
    def __init__(self):
        self.rate_limiter = RateLimiter(requests_per_second=1)  # Very conservative
        self.headers = {
            'User-Agent': 'PRISM-Analytics/1.0 (contact@precise.digital)'
        }
        
    def _make_request(self, endpoint: str, params: dict) -> Optional[dict]:
        """Make request to MusicBrainz API"""
        self.rate_limiter.wait_if_needed()
        
        params['fmt'] = 'json'
        url = f"https://musicbrainz.org/ws/2{endpoint}"
        
        response = requests.get(url, params=params, headers=self.headers)
        
        if response.status_code == 503:  # Service unavailable
            logger.warning("MusicBrainz temporarily unavailable")
            time.sleep(2)
            return None
            
        if response.status_code != 200:
            logger.error(f"MusicBrainz API error: {response.status_code}")
            return None
            
        return response.json()
        
    def search_recording_by_isrc(self, isrc: str) -> Optional[dict]:
        """Search for recording by ISRC"""
        params = {
            'query': f'isrc:{isrc}',
            'inc': 'artist-credits+releases+tags'
        }
        return self._make_request('/recording/', params)
        
    def get_recording(self, recording_id: str) -> Optional[dict]:
        """Get recording details"""
        params = {
            'inc': 'artist-credits+releases+tags+artist-rels+work-rels'
        }
        return self._make_request(f'/recording/{recording_id}', params)

class APIClientManager:
    """Manages all API clients"""
    
    def __init__(self, config: dict):
        self.spotify = SpotifyClient(
            config.get('SPOTIFY_CLIENT_ID'),
            config.get('SPOTIFY_CLIENT_SECRET')
        ) if config.get('SPOTIFY_CLIENT_ID') else None
        
        self.youtube = YouTubeClient(
            config.get('YOUTUBE_API_KEY')
        ) if config.get('YOUTUBE_API_KEY') else None
        
        self.lastfm = LastFMClient(
            config.get('LASTFM_API_KEY'),
            config.get('LASTFM_SHARED_SECRET')
        ) if config.get('LASTFM_API_KEY') else None
        
        self.musicbrainz = MusicBrainzClient()
        
    def validate_clients(self) -> dict:
        """Validate which API clients are available (sync)"""
        status = {}
        
        if self.spotify:
            try:
                self.spotify._get_access_token()
                status['spotify'] = 'available'
            except Exception as e:
                status['spotify'] = f'error: {str(e)}'
        else:
            status['spotify'] = 'not configured'
            
        status['youtube'] = 'available' if self.youtube else 'not configured'
        status['lastfm'] = 'available' if self.lastfm else 'not configured'
        status['musicbrainz'] = 'available'
        
        return status
        
    async def validate_clients_async(self) -> dict:
        """Validate which API clients are available (async)"""
        import asyncio
        
        # Run validation in executor to not block event loop
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.validate_clients)