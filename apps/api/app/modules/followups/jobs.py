from app.integrations.ai.transcription import register_transcription_task
from app.worker.registry import register_handler
from .audio import process_audio,validate_transcription,complete_transcription

register_transcription_task('reflection.transcribe',on_validate=validate_transcription,on_complete=complete_transcription)
register_handler('followups.audio',process_audio,lease_seconds=150,heartbeat_seconds=20,timeout_seconds=90,workload='media')
