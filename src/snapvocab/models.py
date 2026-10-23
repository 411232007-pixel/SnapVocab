"""Vocabulary card model, validation of model output, and de-duplication keys."""

import re
import unicodedata
from dataclasses import asdict, dataclass, fields


class ValidationError(ValueError):
    pass


@dataclass(frozen=True)
class Card:
    zh_name: str
    en_word: str
    en_pos: str
    en_example: str
    en_example_zh: str
    ja_word: str
    ja_kana: str
    ja_romaji: str
    ja_example: str
    ja_example_zh: str
    note: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


CARD_FIELDS = [f.name for f in fields(Card)]

_MAX_LEN = {
    "zh_name": 30,
    "en_word": 60,
    "en_pos": 30,
    "en_example": 200,
    "en_example_zh": 200,
    "ja_word": 60,
    "ja_kana": 80,
    "ja_romaji": 80,
    "ja_example": 200,
    "ja_example_zh": 200,
    "note": 400,
}
_KANA = re.compile(r"^[぀-ヿー・\s]+$")
_ROMAJI = re.compile(r"^[A-Za-zĀ-ſ\s\-'・]+$")


def validate_card(data: object) -> Card:
    if not isinstance(data, dict):
        raise ValidationError("輸出不是物件")
    values: dict[str, str] = {}
    for name in CARD_FIELDS:
        value = data.get(name)
        if not isinstance(value, str):
            raise ValidationError(f"欄位 {name} 缺少或型別錯誤")
        value = " ".join(value.split())
        if not value and name != "note":
            raise ValidationError(f"欄位 {name} 為空")
        if len(value) > _MAX_LEN[name]:
            raise ValidationError(f"欄位 {name} 過長")
        values[name] = value
    if not _KANA.match(values["ja_kana"]):
        raise ValidationError("ja_kana 含有非假名字元")
    if not _ROMAJI.match(values["ja_romaji"]):
        raise ValidationError("ja_romaji 含有非羅馬字字元")
    return Card(**values)


def en_key(word: str) -> str:
    return " ".join(word.split()).lower()


def ja_key(word: str) -> str:
    return unicodedata.normalize("NFKC", word).strip()
