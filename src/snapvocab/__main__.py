import logging
from pathlib import Path

from .bot import SnapVocabBot
from .config import load_settings
from .storage import Database
from .vision import ClaudeVision


def main() -> None:
    settings = load_settings()
    Path("data").mkdir(exist_ok=True)
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("data/snapvocab.log", encoding="utf-8")],
    )
    bot = SnapVocabBot(settings, Database(settings.db_path), ClaudeVision())
    bot.run(settings.token, log_handler=None)


if __name__ == "__main__":
    main()
