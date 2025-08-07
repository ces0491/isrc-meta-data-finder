import pandas as pd
import json
from datetime import datetime

class ExportService:
    def __init__(self, db_manager):
        self.db_manager = db_manager
    
    def export_to_csv(self, isrc_list):
        """Export metadata to CSV format"""
        session = self.db_manager.get_session()
        try:
            tracks = session.query(Track).filter(Track.isrc.in_(isrc_list)).all()
            
            data = []
            for track in tracks:
                data.append({
                    'ISRC': track.isrc,
                    'Title': track.title,
                    'Artist': track.artist,
                    'Album': track.album,
                    'Duration (ms)': track.duration_ms,
                    'Release Date': track.release_date,
                    'Tempo': track.tempo,
                    'Key': track.key,
                    'Energy': track.energy,
                    'Danceability': track.danceability,
                    'Confidence Score': track.confidence_score,
                    'Data Completeness': track.data_completeness
                })
            
            df = pd.DataFrame(data)
            return df.to_csv(index=False)
        finally:
            self.db_manager.close_session(session)