"""
PRISM Analytics - Async Metadata Collector
AsyncIO-based metadata collection for FastAPI integration
"""
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any, Tuple
import logging
from datetime import datetime
import re
import time

logger = logging.getLogger(__name__)

class AsyncMetadataCollector:
    """Async metadata collector for FastAPI integration"""
    
    def __init__(self, api_clients, db_manager):
        self.api_clients = api_clients
        self.db_manager = db_manager
        self.session = None  # aiohttp session
        self.confidence_weights = {
            'musicbrainz': 0.30,  # Most authoritative
            'spotify': 0.25,      # Commercial accuracy
            'lastfm': 0.20,       # Community validation
            'youtube': 0.15,      # Video content
            'cross_validation': 0.10  # Multiple source agreement
        }
        
    async def __aenter__(self):
        """Async context manager entry"""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(limit=10)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()
            
    async def analyze_isrc_async(
        self, 
        isrc: str, 
        comprehensive: bool = True,
        include_lyrics: bool = True,
        include_credits: bool = True,
        include_technical: bool = True
    ) -> Dict[str, Any]:
        """
        Async ISRC analysis using multiple sources
        
        Args:
            isrc: The ISRC code to analyze
            comprehensive: Whether to collect extended data
            include_lyrics: Fetch lyrics data
            include_credits: Fetch detailed credits
            include_technical: Fetch audio technical features
            
        Returns:
            Aggregated metadata with confidence scoring
        """
        if not self._validate_isrc(isrc):
            raise ValueError(f"Invalid ISRC format: {isrc}")
            
        logger.info(f"🎵 Starting async analysis for ISRC: {isrc}")
        
        # Check cache first
        cached_data = await self._get_cached_data_async(isrc)
        if cached_data and not self._is_stale(cached_data):
            logger.info(f"📋 Using cached data for {isrc}")
            return cached_data
            
        # Collect data from all sources concurrently
        async with self:  # Initialize aiohttp session
            raw_data = await self._collect_concurrent_data(isrc, comprehensive)
            
        # Aggregate and score the data
        aggregated_data = await self._aggregate_metadata_async(raw_data, isrc)
        
        # Store in database (sync operation)
        await self._store_metadata_async(aggregated_data)
        
        return aggregated_data
        
    async def bulk_analyze_async(
        self,
        isrc_list: List[str],
        comprehensive: bool = False
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Bulk async ISRC analysis with concurrency control
        
        Args:
            isrc_list: List of ISRCs to analyze
            comprehensive: Use comprehensive analysis
            
        Returns:
            Tuple of (successful_results, errors)
        """
        logger.info(f"📊 Starting bulk async analysis for {len(isrc_list)} ISRCs")
        
        results = []
        errors = []
        
        # Process in batches to avoid overwhelming APIs
        batch_size = 10
        for i in range(0, len(isrc_list), batch_size):
            batch = isrc_list[i:i + batch_size]
            
            # Create tasks for this batch
            tasks = [
                self._analyze_single_isrc_safe(isrc, comprehensive)
                for isrc in batch
            ]
            
            # Execute batch concurrently
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process batch results
            for isrc, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    errors.append({
                        'isrc': isrc,
                        'error': str(result)
                    })
                elif result:
                    results.append({
                        'isrc': isrc,
                        'status': 'success',
                        'confidence_score': result.get('confidence_score', 0.0),
                        'title': result.get('title'),
                        'artist': result.get('artist')
                    })
                else:
                    errors.append({
                        'isrc': isrc,
                        'error': 'No data found'
                    })
            
            # Rate limiting between batches
            if i + batch_size < len(isrc_list):
                await asyncio.sleep(2)  # 2 second delay between batches
                
        return results, errors
        
    async def _analyze_single_isrc_safe(
        self,
        isrc: str,
        comprehensive: bool
    ) -> Optional[Dict[str, Any]]:
        """Safely analyze a single ISRC with error handling"""
        try:
            return await self.analyze_isrc_async(isrc, comprehensive)
        except Exception as e:
            logger.error(f"❌ Safe analysis failed for {isrc}: {e}")
            return None
            
    def _validate_isrc(self, isrc: str) -> bool:
        """Validate ISRC format"""
        isrc_pattern = r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$'
        return bool(re.match(isrc_pattern, isrc.upper()))
        
    async def _get_cached_data_async(self, isrc: str) -> Optional[Dict]:
        """Async check for cached track data"""
        # Run database query in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, 
            self._get_cached_data_sync, 
            isrc
        )
        
    def _get_cached_data_sync(self, isrc: str) -> Optional[Dict]:
        """Synchronous database query for cached data"""
        session = self.db_manager.get_session()
        try:
            from src.models.database import Track
            track = session.query(Track).filter(Track.isrc == isrc).first()
            if track:
                return self._track_to_dict(track)
            return None
        finally:
            self.db_manager.close_session(session)
            
    def _is_stale(self, cached_data: Dict, max_age_hours: int = 24) -> bool:
        """Check if cached data is stale"""
        if not cached_data.get('last_updated'):
            return True
            
        last_updated = datetime.fromisoformat(cached_data['last_updated'])
        age_hours = (datetime.now() - last_updated).total_seconds() / 3600
        return age_hours > max_age_hours
        
    async def _collect_concurrent_data(self, isrc: str, comprehensive: bool) -> Dict[str, Any]:
        """Collect data from all sources concurrently"""
        
        # Define collection tasks
        collection_tasks = {
            'musicbrainz': self._collect_musicbrainz_async(isrc),
            'spotify': self._collect_spotify_async(isrc),
        }
        
        if self.api_clients.lastfm:
            collection_tasks['lastfm'] = self._collect_lastfm_async(isrc)
            
        if self.api_clients.youtube:
            collection_tasks['youtube'] = self._collect_youtube_async(isrc)
        
        # Execute all tasks concurrently
        results = await asyncio.gather(
            *collection_tasks.values(),
            return_exceptions=True
        )
        
        # Map results back to source names
        raw_data = {}
        for source_name, result in zip(collection_tasks.keys(), results):
            if isinstance(result, Exception):
                logger.error(f"❌ {source_name} collection failed for {isrc}: {result}")
                raw_data[source_name] = None
            else:
                raw_data[source_name] = result
                logger.info(f"✅ {source_name} data collected for {isrc}")
                
        return raw_data
        
    async def _collect_musicbrainz_async(self, isrc: str) -> Optional[Dict]:
        """Async MusicBrainz data collection"""
        if not self.api_clients.musicbrainz:
            return None
            
        try:
            # Use the sync client but run in executor
            loop = asyncio.get_event_loop()
            
            search_result = await loop.run_in_executor(
                None,
                self.api_clients.musicbrainz.search_recording_by_isrc,
                isrc
            )
            
            if not search_result or not search_result.get('recordings'):
                return None
                
            recording = search_result['recordings'][0]
            recording_id = recording['id']
            
            # Get detailed data
            detailed_data = await loop.run_in_executor(
                None,
                self.api_clients.musicbrainz.get_recording,
                recording_id
            )
            
            return {
                'source': 'musicbrainz',
                'recording_id': recording_id,
                'title': recording.get('title'),
                'artist': self._extract_artist_name(recording),
                'length': recording.get('length'),
                'releases': recording.get('releases', []),
                'tags': recording.get('tags', []),
                'relations': detailed_data.get('relations', []) if detailed_data else [],
                'confidence': 0.9,
                'raw_data': recording
            }
            
        except Exception as e:
            logger.error(f"❌ MusicBrainz async collection error: {e}")
            return None
            
    async def _collect_spotify_async(self, isrc: str) -> Optional[Dict]:
        """Async Spotify data collection"""
        if not self.api_clients.spotify:
            return None
            
        try:
            # Run Spotify API calls in executor to avoid blocking
            loop = asyncio.get_event_loop()
            
            # Search by ISRC
            search_result = await loop.run_in_executor(
                None,
                self.api_clients.spotify.search_by_isrc,
                isrc
            )
            
            if not search_result or not search_result.get('tracks', {}).get('items'):
                return None
                
            track = search_result['tracks']['items'][0]
            track_id = track['id']
            
            # Get audio features
            audio_features = await loop.run_in_executor(
                None,
                self.api_clients.spotify.get_audio_features,
                track_id
            )
            
            return {
                'source': 'spotify',
                'track_id': track_id,
                'title': track.get('name'),
                'artist': ', '.join([artist['name'] for artist in track.get('artists', [])]),
                'album': track.get('album', {}).get('name'),
                'duration_ms': track.get('duration_ms'),
                'popularity': track.get('popularity'),
                'release_date': track.get('album', {}).get('release_date'),
                'audio_features': audio_features,
                'confidence': 0.85,
                'raw_data': track
            }
            
        except Exception as e:
            logger.error(f"❌ Spotify async collection error: {e}")
            return None
            
    async def _collect_lastfm_async(self, isrc: str) -> Optional[Dict]:
        """Async Last.fm data collection"""
        # Last.fm doesn't support ISRC search directly
        # Would need artist/track from other sources first
        return None
        
    async def _collect_youtube_async(self, isrc: str) -> Optional[Dict]:
        """Async YouTube data collection"""
        # YouTube doesn't support ISRC search directly
        # Would need artist/track from other sources first
        return None
        
    async def _aggregate_metadata_async(self, raw_data: Dict[str, Any], isrc: str) -> Dict[str, Any]:
        """Async metadata aggregation with confidence scoring"""
        
        aggregated = {
            'isrc': isrc,
            'title': None,
            'artist': None,
            'album': None,
            'duration_ms': None,
            'release_date': None,
            'audio_features': {},
            'credits': [],
            'platform_ids': {},
            'confidence_score': 0.0,
            'data_completeness': 0.0,
            'source_data': raw_data,
            'last_updated': datetime.now().isoformat()
        }
        
        source_scores = []
        field_votes = {
            'title': {},
            'artist': {},
            'album': {}
        }
        
        # Process each source
        for source_name, source_data in raw_data.items():
            if not source_data:
                continue
                
            source_confidence = source_data.get('confidence', 0.0)
            source_weight = self.confidence_weights.get(source_name, 0.1)
            
            # Collect field votes with weights
            for field in ['title', 'artist', 'album']:
                value = source_data.get(field)
                if value:
                    if value not in field_votes[field]:
                        field_votes[field][value] = 0
                    field_votes[field][value] += source_weight * source_confidence
                    
            # Collect specific data
            if source_name == 'spotify':
                if source_data.get('audio_features'):
                    aggregated['audio_features'] = source_data['audio_features']
                aggregated['platform_ids']['spotify_id'] = source_data.get('track_id')
                aggregated['duration_ms'] = source_data.get('duration_ms')
                
            elif source_name == 'musicbrainz':
                aggregated['platform_ids']['musicbrainz_recording_id'] = source_data.get('recording_id')
                
            source_scores.append(source_weight * source_confidence)
            
        # Select best values based on weighted votes
        for field, votes in field_votes.items():
            if votes:
                best_value = max(votes.items(), key=lambda x: x[1])[0]
                aggregated[field] = best_value
                
        # Calculate overall confidence score
        if source_scores:
            aggregated['confidence_score'] = sum(source_scores) / len(source_scores) * 100
            
        # Calculate data completeness
        essential_fields = ['title', 'artist', 'album', 'duration_ms']
        completed_fields = sum(1 for field in essential_fields if aggregated.get(field))
        aggregated['data_completeness'] = (completed_fields / len(essential_fields)) * 100
        
        return aggregated
        
    async def _store_metadata_async(self, metadata: Dict[str, Any]) -> None:
        """Async metadata storage in database"""
        # Run database operations in executor to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            self._store_metadata_sync,
            metadata
        )
        
    def _store_metadata_sync(self, metadata: Dict[str, Any]) -> None:
        """Synchronous database storage"""
        session = self.db_manager.get_session()
        try:
            from src.models.database import Track
            
            # Check if track exists
            track = session.query(Track).filter(Track.isrc == metadata['isrc']).first()
            
            if not track:
                track = Track(isrc=metadata['isrc'])
                session.add(track)
                
            # Update track data
            track.title = metadata.get('title')
            track.artist = metadata.get('artist')
            track.album = metadata.get('album')
            track.duration_ms = metadata.get('duration_ms')
            track.release_date = metadata.get('release_date')
            
            # Audio features from Spotify
            audio_features = metadata.get('audio_features', {})
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
            platform_ids = metadata.get('platform_ids', {})
            track.spotify_id = platform_ids.get('spotify_id')
            track.musicbrainz_recording_id = platform_ids.get('musicbrainz_recording_id')
            
            # Metadata quality scores
            track.confidence_score = metadata.get('confidence_score', 0.0)
            track.data_completeness = metadata.get('data_completeness', 0.0)
            track.last_updated = datetime.now()
            
            session.commit()
            logger.info(f"✅ Stored metadata for {metadata['isrc']}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Database storage error: {e}")
            raise
        finally:
            self.db_manager.close_session(session)
            
    def _extract_artist_name(self, recording: Dict) -> str:
        """Extract artist name from MusicBrainz recording"""
        artist_credits = recording.get('artist-credit', [])
        if artist_credits:
            return ', '.join([credit.get('name', '') for credit in artist_credits])
        return ''
        
    def _track_to_dict(self, track) -> Dict[str, Any]:
        """Convert SQLAlchemy Track object to dictionary"""
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
            },
            'platform_ids': {
                'spotify_id': track.spotify_id,
                'musicbrainz_recording_id': track.musicbrainz_recording_id,
            },
            'confidence_score': track.confidence_score,
            'data_completeness': track.data_completeness,
            'last_updated': track.last_updated.isoformat() if track.last_updated else None
        }