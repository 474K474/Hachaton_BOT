from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str = ""
    admin_ids: str = ""
    database_url: str = "sqlite+aiosqlite:///data/events.db"

    tg_channels: str = "Yandex4Developers:Яндекс"

    timepad_enabled: bool = True
    timepad_token: str = ""
    timepad_cities: str = "Санкт-Петербург,Москва"
    timepad_category_ids: str = ""

    collect_interval_hours: int = 6
    digest_hour: int = 10

    timezone: str = "Europe/Moscow"
    log_level: str = "INFO"

    user_agent: str = "EventsBot/0.1 (+https://github.com/474K474/Hachaton_BOT)"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x) for x in _split(self.admin_ids) if x.isdigit()}

    @property
    def channels(self) -> dict[str, str]:
        """{'Yandex4Developers': 'Яндекс'}"""
        result: dict[str, str] = {}
        for item in _split(self.tg_channels):
            name, _, org = item.partition(":")
            result[name.strip().lstrip("@")] = org.strip() or name.strip()
        return result

    @property
    def timepad_city_list(self) -> list[str]:
        return _split(self.timepad_cities)

    @property
    def timepad_category_id_list(self) -> list[int]:
        return [int(x) for x in _split(self.timepad_category_ids) if x.isdigit()]


def _split(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
