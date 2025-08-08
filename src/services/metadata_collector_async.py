# src/services/metadata_collector_async.py
"""
Async Metadata Collector - Complete Fixed Version
Compatible with simple DatabaseManager from run.py
"""

import asyncio
import logging
import os
import re
import sys
from datetime import datetime

# Add path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

logger = logging.getLogger(__name__)


class AsyncMetadataCollector:
    """Simple async metadata collector compatible with run.py DatabaseManager"""

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
            batch = isrc_list[i : i + batch_size]

            # Process batch
            tasks = [self._analyze_single_safe(isrc, comprehensive) for isrc in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect results
            for isrc, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    errors.append({"isrc": isrc, "error": str(result)})
                elif result:
                    results.append(result)
                else:
                    errors.append({"isrc": isrc, "error": "No data found"})

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
        pattern = r"^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$"
        return bool(re.match(pattern, isrc.upper()))

    async def _get_cached_data_async(self, isrc):
        """Get cached data"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._get_cached_sync, isrc)

    def _get_cached_sync(self, isrc):
        """Sync cache lookup using the simple database manager"""
        try:
            # Use the get_track_by_isrc method from DatabaseManager
            track_data = self.db_manager.get_track_by_isrc(isrc)
            if track_data:
                # Ensure the data has the expected structure
                if not isinstance(track_data, dict):
                    return None
                return track_data
            return None
        except Exception as e:
            logger.error(f"Cache lookup error: {e}")
            return None

    def _is_stale(self, cached_data, max_age_hours=24):
        """Check if data is stale"""
        if not cached_data or not cached_data.get("last_updated"):
            return True
        try:
            # Handle both string and datetime formats
            last_updated = cached_data["last_updated"]
            if isinstance(last_updated, str):
                last_updated = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
            elif not isinstance(last_updated, datetime):
                return True
                
            age_hours = (datetime.now() - last_updated).total_seconds() / 3600
            return age_hours > max_age_hours
        except Exception as e:
            logger.error(f"Error checking staleness: {e}")
            return True

    async def _collect_data_async(self, isrc):
        """Collect data from APIs"""
        raw_data = {}

        # Collect from Spotify
        if self.api_clients and self.api_clients.spotify:
            try:
                spotify_data = await self._collect_spotify_async(isrc)
                if spotify_data:
                    raw_data["spotify"] = spotify_data
            except Exception as e:
                logger.error(f"Spotify collection failed: {e}")

        # Collect from MusicBrainz
        if self.api_clients and self.api_clients.musicbrainz:
            try:
                mb_data = await self._collect_musicbrainz_async(isrc)
                if mb_data:
                    raw_data["musicbrainz"] = mb_data
            except Exception as e:
                logger.error(f"MusicBrainz collection failed: {e}")

        # Collect from YouTube
        if self.api_clients and self.api_clients.youtube:
            try:
                youtube_data = await self._collect_youtube_async(isrc, raw_data)
                if youtube_data:
                    raw_data["youtube"] = youtube_data
            except Exception as e:
                logger.error(f"YouTube collection failed: {e}")

        return raw_data

    async def _collect_spotify_async(self, isrc):
        """Collect from Spotify"""
        try:
            loop = asyncio.get_event_loop()

            # Search by ISRC
            track = await loop.run_in_executor(
                None, self.api_clients.spotify.search_by_isrc, isrc
            )

            if not track:
                return None

            track_id = track.get("id")
            if not track_id:
                return None

            # Get audio features
            audio_features = await loop.run_in_executor(
                None, self.api_clients.spotify.get_audio_features, track_id
            )

            return {
                "source": "spotify",
                "track_id": track_id,
                "title": track.get("name"),
                "artist": ", ".join([a["name"] for a in track.get("artists", [])]),
                "album": track.get("album", {}).get("name"),
                "duration_ms": track.get("duration_ms"),
                "release_date": track.get("album", {}).get("release_date"),
                "popularity": track.get("popularity"),
                "spotify_url": track.get("external_urls", {}).get("spotify"),
                "audio_features": audio_features,
                "confidence": 0.85,
            }
        except Exception as e:
            logger.error(f"Spotify async collection error: {e}")
            return None

    async def _collect_musicbrainz_async(self, isrc):
        """Collect from MusicBrainz"""
        try:
            loop = asyncio.get_event_loop()

            recording = await loop.run_in_executor(
                None, self.api_clients.musicbrainz.search_recording_by_isrc, isrc
            )

            if not recording:
                return None

            return {
                "source": "musicbrainz",
                "recording_id": recording.get("id"),
                "title": recording.get("title"),
                "artist": self._extract_artist_name(recording),
                "length": recording.get("length"),
                "confidence": 0.9,
            }
        except Exception as e:
            logger.error(f"MusicBrainz async collection error: {e}")
            return None

    async def _collect_youtube_async(self, isrc, raw_data):
        """Collect from YouTube"""
        try:
            # Use title and artist from other sources if available
            title = None
            artist = None
            
            if "spotify" in raw_data:
                title = raw_data["spotify"].get("title")
                artist = raw_data["spotify"].get("artist")
            elif "musicbrainz" in raw_data:
                title = raw_data["musicbrainz"].get("title")
                artist = raw_data["musicbrainz"].get("artist")
            
            if not title or not artist:
                return None
            
            loop = asyncio.get_event_loop()
            video_data = await loop.run_in_executor(
                None, self.api_clients.youtube.search_by_isrc, isrc, title, artist
            )
            
            if not video_data:
                return None
            
            return {
                "source": "youtube",
                "video_id": video_data.get("id"),
                "title": video_data.get("snippet", {}).get("title"),
                "channel": video_data.get("snippet", {}).get("channelTitle"),
                "views": int(video_data.get("statistics", {}).get("viewCount", 0)),
                "youtube_url": f"https://www.youtube.com/watch?v={video_data.get('id')}",
                "confidence": 0.7,
            }
        except Exception as e:
            logger.error(f"YouTube async collection error: {e}")
            return None

    def _extract_artist_name(self, recording):
        """Extract artist from MusicBrainz data"""
        try:
            artist_credits = recording.get("artist-credit", [])
            if artist_credits:
                return ", ".join([credit.get("name", "") for credit in artist_credits if credit.get("name")])
            return ""
        except:
            return ""

    async def _aggregate_data_async(self, raw_data, isrc):
        """Aggregate data from sources"""
        result = {
            "isrc": isrc,
            "title": None,
            "artist": None,
            "album": None,
            "duration_ms": None,
            "release_date": None,
            "popularity": None,
            "tempo": None,
            "key": None,
            "mode": None,
            "energy": None,
            "danceability": None,
            "valence": None,
            "spotify_id": None,
            "spotify_url": None,
            "musicbrainz_id": None,
            "youtube_video_id": None,
            "youtube_url": None,
            "youtube_views": None,
            "sources": [],
            "confidence": 0.0,
            "data_completeness": 0.0,
            "last_updated": datetime.now().isoformat(),
        }

        source_scores = []

        # Process each source
        for source_name, source_data in raw_data.items():
            if not source_data:
                continue

            confidence = source_data.get("confidence", 0.0)
            result["sources"].append(source_name.capitalize())

            # Take first good values
            if not result["title"] and source_data.get("title"):
                result["title"] = source_data["title"]
            if not result["artist"] and source_data.get("artist"):
                result["artist"] = source_data["artist"]
            if not result["album"] and source_data.get("album"):
                result["album"] = source_data["album"]

            # Spotify-specific data
            if source_name == "spotify":
                result["duration_ms"] = source_data.get("duration_ms")
                result["release_date"] = source_data.get("release_date")
                result["popularity"] = source_data.get("popularity")
                result["spotify_id"] = source_data.get("track_id")
                result["spotify_url"] = source_data.get("spotify_url")
                
                # Audio features
                audio_features = source_data.get("audio_features", {})
                if audio_features:
                    result["tempo"] = audio_features.get("tempo")
                    result["key"] = audio_features.get("key")
                    result["mode"] = audio_features.get("mode")
                    result["energy"] = audio_features.get("energy")
                    result["danceability"] = audio_features.get("danceability")
                    result["valence"] = audio_features.get("valence")

            # MusicBrainz-specific data
            elif source_name == "musicbrainz":
                result["musicbrainz_id"] = source_data.get("recording_id")
                if not result["duration_ms"] and source_data.get("length"):
                    result["duration_ms"] = source_data["length"]

            # YouTube-specific data
            elif source_name == "youtube":
                result["youtube_video_id"] = source_data.get("video_id")
                result["youtube_url"] = source_data.get("youtube_url")
                result["youtube_views"] = source_data.get("views")

            source_scores.append(confidence)

        # Calculate confidence
        if source_scores:
            result["confidence"] = sum(source_scores) / len(source_scores) * 100

        # Calculate completeness
        essential_fields = ["title", "artist", "album", "duration_ms"]
        completed = sum(1 for field in essential_fields if result.get(field))
        result["data_completeness"] = (completed / len(essential_fields)) * 100

        return result

    async def _store_data_async(self, data):
        """Store data in database"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._store_data_sync, data)

    def _store_data_sync(self, data):
        """Sync store data using the simple database manager"""
        try:
            # Save using the database manager's save_track_metadata method
            self.db_manager.save_track_metadata(data)
            logger.info(f"✅ Stored data for {data['isrc']}")
            
        except Exception as e:
            logger.error(f"❌ Storage error: {e}")
            # Don't raise to prevent crashes, just log the error