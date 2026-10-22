import re
from functools import lru_cache
from pydantic import SecretStr
from pydantic_settings import BaseSettings,SettingsConfigDict

class TelegramSettings(BaseSettings):
    model_config=SettingsConfigDict(env_prefix='OPORA_TELEGRAM_',extra='ignore')
    link_enabled:bool=False
    bot_username:str|None=None
    webhook_secret:SecretStr|None=None
    # Shared with the bot process only: lets it open volunteer-scoped bot sessions.
    bot_api_secret:SecretStr|None=None
    def configured(self):
        username=(self.bot_username or '').lstrip('@')
        secret=self.webhook_secret.get_secret_value() if self.webhook_secret else ''
        return bool(self.link_enabled and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}',username) and re.fullmatch(r'[A-Za-z0-9_-]{32,256}',secret))
    def bot_api_configured(self):
        secret=self.bot_api_secret.get_secret_value() if self.bot_api_secret else ''
        return bool(self.configured() and re.fullmatch(r'[A-Za-z0-9_-]{32,256}',secret))
    def username(self):return (self.bot_username or '').lstrip('@')

@lru_cache
def get_telegram_settings():return TelegramSettings()
