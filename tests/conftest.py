import pytest

from snapvocab.models import Card
from snapvocab.storage import Database


def make_card(**overrides) -> Card:
    base = dict(
        zh_name="雨傘", en_word="umbrella", en_pos="noun",
        en_example="Take an umbrella.", en_example_zh="帶把傘吧。",
        ja_word="傘", ja_kana="かさ", ja_romaji="kasa",
        ja_example="傘を持っていきます。", ja_example_zh="帶傘去。", note="",
    )
    base.update(overrides)
    return Card(**base)


@pytest.fixture
def db() -> Database:
    return Database(":memory:")
