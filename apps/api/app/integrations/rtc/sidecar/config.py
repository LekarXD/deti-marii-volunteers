from dataclasses import dataclass,field
from pathlib import Path
import os

@dataclass(frozen=True)
class Settings:
    secret:str=field(repr=False)
    data_dir:Path=Path('/data/opora-boards')
    auth_url:str=''
    max_message_bytes:int=4*1024*1024
    max_awareness_bytes:int=64*1024
    max_connections_per_room:int=100
    max_rooms:int=100
    idle_timeout_s:int=90
    board_retention_days:int=30
    cleanup_interval_s:int=6*3600
    compact_after_updates:int=500
    awareness_per_second:int=30
    awareness_burst:int=60
    sync_requests_burst:int=4
    sync_requests_per_minute:int=6
    max_awareness_clients:int=1000
    jwt_leeway_s:int=5
    introspect_seconds:int=10
    @property
    def board_db_path(self):return self.data_dir/'opora-boards.sqlite3'

def load_settings():
    secret=os.getenv('OPORA_RTC_BOARD_SECRET','');auth_url=os.getenv('OPORA_RTC_BOARD_AUTH_URL','')
    if len(secret)<32 or not auth_url:raise RuntimeError('Opora board secret and authorization endpoint are required')
    return Settings(secret=secret,data_dir=Path(os.getenv('OPORA_RTC_BOARD_DATA_DIR','/data/opora-boards')),auth_url=auth_url)
