# src/services/metadata_collector_async.py
"""
Async Metadata Collector - Complete Version with Last.fm and Discogs
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
        
        # First, try to get basic info from primary sources
        primary_title = None
        primary_artist = None
        primary_album = None

        # Collect from Spotify
        if self.api_clients and self.api_clients.spotify:
            try:
                spotify_data = await self._collect_spotify_async(isrc)
                if spotify_data:
                    raw_data["spotify"] = spotify_data
                    primary_title = spotify_data.get("title")
                    primary_artist = spotify_data.get("artist")
                    primary_album = spotify_data.get("album")
            except Exception as e:
                logger.error(f"Spotify collection failed: {e}")

        # Collect from MusicBrainz
        if self.api_clients and self.api_clients.musicbrainz:
            try:
                mb_data = await self._collect_musicbrainz_async(isrc)
                if mb_data:
                    raw_data["musicbrainz"] = mb_data
                    if not primary_title:
                        primary_title = mb_data.get("title")
                        primary_artist = mb_data.get("artist")
            except Exception as e:
                logger.error(f"MusicBrainz collection failed: {e}")

        # Now collect from secondary sources using the title/artist we found
        if primary_title and primary_artist:
            
            # Collect from YouTube
            if self.api_clients and self.api_clients.youtube:
                try:
                    youtube_data = await self._collect_youtube_async(isrc, raw_data)
                    if youtube_data:
                        raw_data["youtube"] = youtube_data
                except Exception as e:
                    logger.error(f"YouTube collection failed: {e}")
            
            # Collect from Last.fm
            if self.api_clients and self.api_clients.lastfm:
                try:
                    lastfm_data = await self._collect_lastfm_async(isrc, primary_title, primary_artist)
                    if lastfm_data:
                        raw_data["lastfm"] = lastfm_data
                except Exception as e:
                    logger.error(f"Last.fm collection failed: {e}")
            
            # Collect from Discogs
            if self.api_clients and self.api_clients.discogs:
                try:
                    discogs_data = await self._collect_discogs_async(isrc, primary_title, primary_artist, primary_album)
                    if discogs_data:
                        raw_data["discogs"] = discogs_data
                except Exception as e:
                    logger.error(f"Discogs collection failed: {e}")
            
            # Collect from Genius (if available)
            if self.api_clients and self.api_clients.genius:
                try:
                    genius_data = await self._collect_genius_async(primary_title, primary_artist)
                    if genius_data:
                        raw_data["genius"] = genius_data
                except Exception as e:
                    logger.error(f"Genius collection failed: {e}")

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

    async def _collect_lastfm_async(self, isrc, title=None, artist=None):
        """Collect metadata from Last.fm"""
        try:
            if not title or not artist:
                return None
            
            loop = asyncio.get_event_loop()
            
            # Get track info
            track_info = await loop.run_in_executor(
                None, 
                self.api_clients.lastfm.get_track_info,
                artist,
                title
            )
            
            if not track_info:
                # Try searching instead
                search_result = await loop.run_in_executor(
                    None,
                    self.api_clients.lastfm.search_track,
                    title,
                    artist
                )
                if search_result:
                    # Get full info for the found track
                    track_info = await loop.run_in_executor(
                        None,
                        self.api_clients.lastfm.get_track_info,
                        search_result.get('artist', artist),
                        search_result.get('name', title)
                    )
            
            if not track_info:
                return None
            
            # Get tags for genre information
            tags = await loop.run_in_executor(
                None,
                self.api_clients.lastfm.get_track_tags,
                artist,
                title
            )
            
            # Get album info if available
            album_info = None
            if track_info.get('album'):
                album_info = await loop.run_in_executor(
                    None,
                    self.api_clients.lastfm.get_album_info,
                    artist,
                    track_info['album'].get('title', '')
                )
            
            # Format the response
            return {
                "source": "lastfm",
                "title": track_info.get("name"),
                "artist": track_info.get("artist", {}).get("name") if isinstance(track_info.get("artist"), dict) else track_info.get("artist"),
                "album": track_info.get("album", {}).get("title") if track_info.get("album") else None,
                "mbid": track_info.get("mbid"),
                "duration": int(track_info.get("duration", 0)) if track_info.get("duration") else None,
                "playcount": int(track_info.get("playcount", 0)) if track_info.get("playcount") else 0,
                "listeners": int(track_info.get("listeners", 0)) if track_info.get("listeners") else 0,
                "url": track_info.get("url"),
                "tags": [tag.get("name") for tag in (tags or [])[:5]] if tags else [],
                "genres": [tag.get("name") for tag in (tags or []) if tag.get("count", 0) > 50][:3] if tags else [],
                "wiki_summary": track_info.get("wiki", {}).get("summary") if track_info.get("wiki") else None,
                "album_info": {
                    "title": album_info.get("name") if album_info else None,
                    "release_date": album_info.get("wiki", {}).get("published") if album_info and album_info.get("wiki") else None,
                    "tracks_count": len(album_info.get("tracks", {}).get("track", [])) if album_info and album_info.get("tracks") else None
                } if album_info else None,
                "confidence": 0.75
            }
            
        except Exception as e:
            logger.error(f"Last.fm collection error: {e}")
            return None

    async def _collect_discogs_async(self, isrc, title=None, artist=None, album=None):
        """Collect metadata from Discogs"""
        try:
            if not title or not artist:
                return None
            
            loop = asyncio.get_event_loop()
            
            # Search for the release
            search_result = await loop.run_in_executor(
                None,
                self.api_clients.discogs.search_release,
                title,
                artist,
                "release"
            )
            
            if not search_result:
                # Try searching with album name if available
                if album:
                    search_result = await loop.run_in_executor(
                        None,
                        self.api_clients.discogs.search_release,
                        album,
                        artist,
                        "master"
                    )
            
            if not search_result:
                return None
            
            # Get the release ID and fetch detailed information
            release_id = None
            master_id = None
            
            if search_result.get("type") == "release":
                release_id = search_result.get("id")
            elif search_result.get("type") == "master":
                master_id = search_result.get("id")
                # Get the main release for this master
                master_info = await loop.run_in_executor(
                    None,
                    self.api_clients.discogs.get_master_release,
                    master_id
                )
                if master_info and master_info.get("main_release"):
                    release_id = master_info["main_release"]
            
            # Get detailed release information
            release_data = None
            if release_id:
                release_data = await loop.run_in_executor(
                    None,
                    self.api_clients.discogs.get_release,
                    release_id
                )
            
            if not release_data:
                return None
            
            # Extract credits
            credits = self.api_clients.discogs.extract_credits_from_release(release_data)
            
            # Find the specific track in the tracklist
            track_data = None
            if "tracklist" in release_data:
                for track in release_data["tracklist"]:
                    if track.get("title", "").lower() == title.lower():
                        track_data = track
                        break
                # If exact match not found, use first track as fallback
                if not track_data and release_data["tracklist"]:
                    track_data = release_data["tracklist"][0]
            
            # Format the response
            return {
                "source": "discogs",
                "release_id": release_id,
                "master_id": master_id or search_result.get("master_id"),
                "title": track_data.get("title") if track_data else title,
                "artist": ", ".join([a.get("name", "") for a in release_data.get("artists", [])]),
                "album": release_data.get("title"),
                "duration": track_data.get("duration") if track_data else None,
                "position": track_data.get("position") if track_data else None,
                "catalog_number": release_data.get("labels", [{}])[0].get("catno") if release_data.get("labels") else None,
                "label": release_data.get("labels", [{}])[0].get("name") if release_data.get("labels") else None,
                "release_year": release_data.get("year"),
                "release_date": release_data.get("released"),
                "country": release_data.get("country"),
                "formats": [f.get("name") for f in release_data.get("formats", [])],
                "genres": release_data.get("genres", []),
                "styles": release_data.get("styles", []),
                "barcode": next((i.get("value") for i in release_data.get("identifiers", []) 
                               if i.get("type") == "Barcode"), None),
                "credits": credits,
                "tracklist_count": len(release_data.get("tracklist", [])),
                "discogs_url": f"https://www.discogs.com/release/{release_id}",
                "thumb": search_result.get("thumb"),
                "cover_image": search_result.get("cover_image"),
                "confidence": 0.8
            }
            
        except Exception as e:
            logger.error(f"Discogs collection error: {e}")
            return None

    async def _collect_genius_async(self, title, artist):
        """Collect from Genius (placeholder for existing implementation)"""
        try:
            if not self.api_clients.genius:
                return None
                
            loop = asyncio.get_event_loop()
            
            # Search for the song
            song = await loop.run_in_executor(
                None,
                self.api_clients.genius.search_song,
                title,
                artist
            )
            
            if not song:
                return None
            
            # Get detailed song info
            song_id = song.get("id")
            if song_id:
                song_details = await loop.run_in_executor(
                    None,
                    self.api_clients.genius.get_song_details,
                    song_id
                )
                
                if song_details:
                    return {
                        "source": "genius",
                        "song_id": song_id,
                        "title": song_details.get("title"),
                        "artist": song_details.get("primary_artist", {}).get("name"),
                        "url": song_details.get("url"),
                        "confidence": 0.7
                    }
            
            return None
            
        except Exception as e:
            logger.error(f"Genius collection error: {e}")
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
            "lastfm_url": None,
            "lastfm_playcount": None,
            "lastfm_listeners": None,
            "discogs_release_id": None,
            "discogs_master_id": None,
            "discogs_url": None,
            "genres": [],
            "styles": [],
            "tags": [],
            "label": None,
            "catalog_number": None,
            "credits": [],
            "sources": [],
            "confidence": 0.0,
            "data_completeness": 0.0,
            "last_updated": datetime.now().isoformat(),
        }

        source_scores = []
        all_credits = []
        all_genres = set()
        all_styles = set()
        all_tags = set()

        # Process each source
        for source_name, source_data in raw_data.items():
            if not source_data:
                continue

            confidence = source_data.get("confidence", 0.0)
            result["sources"].append(source_name.capitalize())
            source_scores.append(confidence)

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

            # Last.fm-specific data
            elif source_name == "lastfm":
                result["lastfm_url"] = source_data.get("url")
                result["lastfm_playcount"] = source_data.get("playcount")
                result["lastfm_listeners"] = source_data.get("listeners")
                
                # Add genres and tags
                if source_data.get("genres"):
                    all_genres.update(source_data["genres"])
                if source_data.get("tags"):
                    all_tags.update(source_data["tags"])
                
                # Use duration if not already set
                if not result["duration_ms"] and source_data.get("duration"):
                    result["duration_ms"] = source_data["duration"]

            # Discogs-specific data
            elif source_name == "discogs":
                result["discogs_release_id"] = source_data.get("release_id")
                result["discogs_master_id"] = source_data.get("master_id")
                result["discogs_url"] = source_data.get("discogs_url")
                result["label"] = source_data.get("label")
                result["catalog_number"] = source_data.get("catalog_number")
                
                # Add genres and styles
                if source_data.get("genres"):
                    all_genres.update(source_data["genres"])
                if source_data.get("styles"):
                    all_styles.update(source_data["styles"])
                
                # Add credits
                if source_data.get("credits"):
                    all_credits.extend(source_data["credits"])
                
                # Use release date if not already set
                if not result["release_date"] and source_data.get("release_date"):
                    result["release_date"] = source_data["release_date"]
                elif not result["release_date"] and source_data.get("release_year"):
                    result["release_date"] = str(source_data["release_year"])

            # Genius-specific data
            elif source_name == "genius":
                if source_data.get("url"):
                    result["genius_url"] = source_data["url"]

        # Combine genres, styles, and tags
        result["genres"] = list(all_genres)[:5]  # Top 5 genres
        result["styles"] = list(all_styles)[:5]  # Top 5 styles
        result["tags"] = list(all_tags)[:10]  # Top 10 tags

        # Deduplicate and combine credits
        if all_credits:
            # Remove duplicates based on name and credit type
            seen = set()
            unique_credits = []
            for credit in all_credits:
                key = f"{credit.get('name', '')}_{credit.get('credit_type', '')}"
                if key not in seen:
                    seen.add(key)
                    unique_credits.append(credit)
            result["credits"] = unique_credits[:20]  # Limit to 20 credits

        # Calculate confidence (enhanced with new sources)
        if source_scores:
            # Weight sources based on reliability
            weights = {
                "spotify": 1.2,
                "musicbrainz": 1.0,
                "discogs": 0.9,
                "lastfm": 0.8,
                "youtube": 0.7,
                "genius": 0.6
            }
            
            weighted_scores = []
            for source, score in zip(result["sources"], source_scores):
                weight = weights.get(source.lower(), 1.0)
                weighted_scores.append(score * weight)
            
            result["confidence"] = (sum(weighted_scores) / len(weighted_scores)) * 100

        # Calculate completeness (enhanced)
        essential_fields = [
            "title", "artist", "album", "duration_ms", "release_date",
            "spotify_id", "musicbrainz_id", "youtube_video_id",
            "genres", "label"
        ]
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
            
            # Save lyrics if available
            if data.get("lyrics_data"):
                self.db_manager.save_lyrics(data["isrc"], data["lyrics_data"])
            
            # Save credits if available  
            if data.get("credits"):
                self.db_manager.save_credits(data["isrc"], data["credits"])
                
        except Exception as e:
            logger.error(f"❌ Storage error: {e}")
            # Don't raise to prevent crashes, just log the error