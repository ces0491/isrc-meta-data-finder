# type: ignore
"""
PRISM Analytics - Simple Async Metadata Collector
Focus on working functionality
"""
import asyncio
import re
import logging
from datetime import datetime
import sys
import os

# Add path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logger = logging.getLogger(__name__)

class AsyncMetadataCollector:
    """Simple async metadata collector"""
    
    def __init__(self, api_clients, db_manager):
        self.api_clients = api_clients
        self.db_manager = db_manager
        
    async def analyze_isrc_async(self, isrc, comprehensive=True, **kwargs):
        """Analyze ISRC async"""
        if not self._validate_isrc(isrc):
            raise ValueError(f"Invalid ISRC: {isrc}")
            
        logger.info(f"🎵 Analyzing {isrc}")
        
        # Check cache first
        cached = await self._get_cached_data_async(isrc)
        if cached and not self._is_stale(cached):
            logger.info(f"📋 Using cached data for {isrc}")
            return cached
            
        # Collect data
        raw_data = await self._collect_data_async(isrc)
        
        # Aggregate
        result = await self._aggregate_data_async(raw_data, isrc)
        
        # Store
        await self._store_data_async(result)
        
        return result
        
    async def bulk_analyze_async(self, isrc_list, comprehensive=False):
        """Bulk analysis"""
        logger.info(f"📊 Bulk analyzing {len(isrc_list)} ISRCs")
        
        results = []
        errors = []
        
        # Process in small batches
        batch_size = 5
        for i in range(0, len(isrc_list), batch_size):
            batch = isrc_list[i:i + batch_size]
            
            # Process batch
            tasks = [self._analyze_single_safe(isrc, comprehensive) for isrc in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Collect results
            for isrc, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    errors.append({'isrc': isrc, 'error': str(result)})
                elif result:
                    results.append({
                        'isrc': isrc,
                        'status': 'success',
                        'confidence_score': result.get('confidence_score', 0),
                        'title': result.get('title'),
                        'artist': result.get('artist')
                    })
                else:
                    errors.append({'isrc': isrc, 'error': 'No data found'})
            
            # Small delay between batches
            if i + batch_size < len(isrc_list):
                await asyncio.sleep(1)
                
        return results, errors
        
    async def _analyze_single_safe(self, isrc, comprehensive):
        """Safe single analysis"""
        try:
            return await self.analyze_isrc_async(isrc, comprehensive)
        except Exception as e:
            logger.error(f"❌ Failed to analyze {isrc}: {e}")
            return None
            
    def _validate_isrc(self, isrc):
        """Validate ISRC format"""
        pattern = r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$'
        return bool(re.match(pattern, isrc.upper()))
        
    async def _get_cached_data_async(self, isrc):
        """Get cached data"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_cached_sync, isrc)
        
    def _get_cached_sync(self, isrc):
        """Sync cache lookup"""
        session = self.db_manager.get_session()
        try:
            from src.models.database import Track
            track = session.query(Track).filter(Track.isrc == isrc).first()
            if track:
                return self._track_to_dict(track)
            return None
        except Exception as e:
            logger.error(f"Cache lookup error: {e}")
            return None
        finally:
            self.db_manager.close_session(session)
            
    def _is_stale(self, cached_data, max_age_hours=24):
        """Check if data is stale"""
        if not cached_data.get('last_updated'):
            return True
        try:
            last_updated = datetime.fromisoformat(cached_data['last_updated'])
            age_hours = (datetime.now() - last_updated).total_seconds() / 3600
            return age_hours > max_age_hours
        except:
            return True
            
    async def _collect_data_async(self, isrc):
        """Collect data from APIs"""
        raw_data = {}
        
        # Collect from Spotify
        if self.api_clients.spotify:
            try:
                spotify_data = await self._collect_spotify_async(isrc)
                raw_data['spotify'] = spotify_data
            except Exception as e:
                logger.error(f"Spotify collection failed: {e}")
                raw_data['spotify'] = None
        
        # Collect from MusicBrainz
        try:
            mb_data = await self._collect_musicbrainz_async(isrc)
            raw_data['musicbrainz'] = mb_data
        except Exception as e:
            logger.error(f"MusicBrainz collection failed: {e}")
            raw_data['musicbrainz'] = None
            
        return raw_data

    async def _collect_credits_async(self, isrc, recording_id):
    """Collect credits from MusicBrainz"""
    # Get detailed recording info with credits
    params = {
        'inc': 'artist-credits+releases+work-rels',
        'fmt': 'json'
    }
    result = await self._make_mb_request(f'/recording/{recording_id}', params)
    
    credits = []
    if result and 'relations' in result:
        for relation in result['relations']:
            if relation.get('artist'):
                credits.append({
                    'person_name': relation['artist']['name'],
                    'credit_type': relation['type'],
                    'role_details': relation.get('attributes', {})
                })
    return credits

    async def _collect_spotify_async(self, isrc):
        """Collect from Spotify"""
        loop = asyncio.get_event_loop()
        
        # Search by ISRC
        search_result = await loop.run_in_executor(
            None, self.api_clients.spotify.search_by_isrc, isrc
        )
        
        if not search_result or not search_result.get('tracks', {}).get('items'):
            return None
            
        track = search_result['tracks']['items'][0]
        track_id = track['id']
        
        # Get audio features
        audio_features = await loop.run_in_executor(
            None, self.api_clients.spotify.get_audio_features, track_id
        )
        
        return {
            'source': 'spotify',
            'track_id': track_id,
            'title': track.get('name'),
            'artist': ', '.join([a['name'] for a in track.get('artists', [])]),
            'album': track.get('album', {}).get('name'),
            'duration_ms': track.get('duration_ms'),
            'release_date': track.get('album', {}).get('release_date'),
            'audio_features': audio_features,
            'confidence': 0.85
        }
        
    async def _collect_musicbrainz_async(self, isrc):
        """Collect from MusicBrainz"""
        loop = asyncio.get_event_loop()
        
        search_result = await loop.run_in_executor(
            None, self.api_clients.musicbrainz.search_recording_by_isrc, isrc
        )
        
        if not search_result or not search_result.get('recordings'):
            return None
            
        recording = search_result['recordings'][0]
        
        return {
            'source': 'musicbrainz',
            'recording_id': recording['id'],
            'title': recording.get('title'),
            'artist': self._extract_artist_name(recording),
            'length': recording.get('length'),
            'confidence': 0.9
        }
        
    def _extract_artist_name(self, recording):
        """Extract artist from MusicBrainz data"""
        artist_credits = recording.get('artist-credit', [])
        if artist_credits:
            return ', '.join([credit.get('name', '') for credit in artist_credits])
        return ''
        
    async def _aggregate_data_async(self, raw_data, isrc):
        """Aggregate data from sources"""
        result = {
            'isrc': isrc,
            'title': None,
            'artist': None,
            'album': None,
            'duration_ms': None,
            'release_date': None,
            'audio_features': {},
            'platform_ids': {},
            'confidence_score': 0.0,
            'data_completeness': 0.0,
            'last_updated': datetime.now().isoformat()
        }
        
        source_scores = []
        
        # Process each source
        for source_name, source_data in raw_data.items():
            if not source_data:
                continue
                
            confidence = source_data.get('confidence', 0.0)
            
            # Take first good values
            if not result['title'] and source_data.get('title'):
                result['title'] = source_data['title']
            if not result['artist'] and source_data.get('artist'):
                result['artist'] = source_data['artist']
            if not result['album'] and source_data.get('album'):
                result['album'] = source_data['album']
                
            # Spotify-specific data
            if source_name == 'spotify':
                result['duration_ms'] = source_data.get('duration_ms')
                result['release_date'] = source_data.get('release_date')
                result['audio_features'] = source_data.get('audio_features', {})
                result['platform_ids']['spotify_id'] = source_data.get('track_id')
                
            # MusicBrainz-specific data
            elif source_name == 'musicbrainz':
                result['platform_ids']['musicbrainz_recording_id'] = source_data.get('recording_id')
                
            source_scores.append(confidence)
            
        # Calculate confidence
        if source_scores:
            result['confidence_score'] = sum(source_scores) / len(source_scores) * 100
            
        # Calculate completeness
        essential_fields = ['title', 'artist', 'album', 'duration_ms']
        completed = sum(1 for field in essential_fields if result.get(field))
        result['data_completeness'] = (completed / len(essential_fields)) * 100
        
        return result
        
    async def _store_data_async(self, data):
        """Store data in database"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._store_data_sync, data)
        
    def _store_data_sync(self, data):
        """Sync store data"""
        session = self.db_manager.get_session()
        try:
            from src.models.database import Track
            
            # Get or create track
            track = session.query(Track).filter(Track.isrc == data['isrc']).first()
            if not track:
                track = Track(isrc=data['isrc'])
                session.add(track)
                
            # Update basic info
            track.title = data.get('title')
            track.artist = data.get('artist')
            track.album = data.get('album')
            track.duration_ms = data.get('duration_ms')
            track.release_date = data.get('release_date')
            
            # Audio features
            audio_features = data.get('audio_features', {})
            if audio_features:
                track.tempo = audio_features.get('tempo')
                track.key = audio_features.get('key')
                track.mode = audio_features.get('mode')
                track.energy = audio_features.get('energy')
                track.danceability = audio_features.get('danceability')
                track.valence = audio_features.get('valence')
                track.loudness = audio_features.get('loudness')
                track.speechiness = audio_features.get('speechiness')
                track.acousticness = audio_features.get('acousticness')
                track.instrumentalness = audio_features.get('instrumentalness')
                track.liveness = audio_features.get('liveness')
                track.time_signature = audio_features.get('time_signature')
                
            # Platform IDs
            platform_ids = data.get('platform_ids', {})
            track.spotify_id = platform_ids.get('spotify_id')
            track.musicbrainz_recording_id = platform_ids.get('musicbrainz_recording_id')
            
            # Quality scores
            track.confidence_score = data.get('confidence_score', 0.0)
            track.data_completeness = data.get('data_completeness', 0.0)
            track.last_updated = datetime.now()
            
            session.commit()
            logger.info(f"✅ Stored data for {data['isrc']}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Storage error: {e}")
            raise
        finally:
            self.db_manager.close_session(session)
            
    def _track_to_dict(self, track):
        """Convert track to dict"""
        return {
            'isrc': track.isrc,
            'title': track.title,
            'artist': track.artist,
            'album': track.album,
            'duration_ms': track.duration_ms,
            'release_date': track.release_date,
            'audio_features': {
                'tempo': track.tempo,
                'key': track.key,
                'mode': track.mode,
                'energy': track.energy,
                'danceability': track.danceability,
                'valence': track.valence,
                'loudness': track.loudness,
                'speechiness': track.speechiness,
                'acousticness': track.acousticness,
                'instrumentalness': track.instrumentalness,
                'liveness': track.liveness,
                'time_signature': track.time_signature,
            } if track.tempo is not None else {},
            'platform_ids': {
                'spotify_id': track.spotify_id,
                'musicbrainz_recording_id': track.musicbrainz_recording_id,
            },
            'confidence_score': track.confidence_score or 0.0,
            'data_completeness': track.data_completeness or 0.0,
            'last_updated': track.last_updated.isoformat() if track.last_updated else None
        }