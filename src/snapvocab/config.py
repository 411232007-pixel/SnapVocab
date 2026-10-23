"""Settings from .env plus the fixed resource limits (see docs/architecture.md 7.1)."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_PIXELS = 4000 * 4000
MODEL_IMAGE_EDGE = 1568
ALLOWED_IMAGE_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}
ALLOWED_ATTACHMENT_HOSTS = {"cdn.discordapp.com", "media.discordapp.net"}

IMAGE_RATE_LIMIT = (3, 60.0)  # requests per window (seconds), per user
EXPORT_COOLDOWN = 30.0
MAX_CONCURRENT_VISION = 2
VISION_TIMEOUT = 60.0
CHOICE_TIMEOUT = 300.0
EXPORT_MAX_FILES = 8

TIMEZONE = "Asia/Taipei"


@dataclass(frozen=True)
class Settings:
    token: str
    channel_id: int
    db_path: Path
    log_level: str


def load_settings() -> Settings:
    load_dotenv()
    token = os.environ.get("DISCORD_TOKEN", "").strip()
    channel = os.environ.get("CHANNEL_ID", "").strip()
    if not token:
        raise SystemExit("DISCORD_TOKEN 未設定，請在 .env 填入。")
    if not channel.isdigit():
        raise SystemExit("CHANNEL_ID 未設定或格式錯誤，請在 .env 填入數字 ID。")
    return Settings(
        token=token,
        channel_id=int(channel),
        db_path=Path(os.environ.get("DB_PATH", "data/snapvocab.db")),
        log_level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    )
