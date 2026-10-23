from pathlib import Path

from snapvocab.bot import SnapVocabBot
from snapvocab.bot.formatting import CHANNEL_TOPIC, FIRST_USE_TIP, HELP_TEXT
from snapvocab.config import Settings
from snapvocab.storage import Database
from snapvocab.vision import VisionError

from .conftest import make_card


class FakeVision:
    def __init__(self):
        self.fail = False

    async def generate(self, zh_name):
        if self.fail:
            raise VisionError("暫時無法處理，請稍後再試。")
        return make_card(zh_name=zh_name)


def _bot(db):
    return SnapVocabBot(Settings("x", 1, Path(":memory:"), "INFO"), db, FakeVision())


async def test_first_use_tip_only_on_first_success(db):
    bot = _bot(db)
    first = await bot.lookup_text("111", "雨傘")
    second = await bot.lookup_text("111", "雨傘")
    other_user = await bot.lookup_text("222", "雨傘")
    assert FIRST_USE_TIP in first
    assert FIRST_USE_TIP not in second
    assert FIRST_USE_TIP in other_user  # tip is per user


async def test_failed_lookup_saves_nothing_and_keeps_tip_for_later(db):
    bot = _bot(db)
    bot.vision.fail = True
    assert "暫時無法處理" in await bot.lookup_text("111", "雨傘")
    assert db.stats("111").total == 0
    bot.vision.fail = False
    assert FIRST_USE_TIP in await bot.lookup_text("111", "雨傘")


def test_texts_fit_discord_limits():
    assert len(CHANNEL_TOPIC) <= 1024
    assert len(HELP_TEXT) <= 2000
    assert "一次只能辨識一張" in HELP_TEXT and "一次只能辨識一張" in CHANNEL_TOPIC
