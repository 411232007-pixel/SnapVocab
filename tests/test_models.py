import pytest

from snapvocab.models import ValidationError, en_key, ja_key, validate_card

from .conftest import make_card


def test_valid_card_roundtrip():
    card = make_card()
    assert validate_card(card.as_dict()) == card


@pytest.mark.parametrize("bad", [None, [], "x"])
def test_non_object_rejected(bad):
    with pytest.raises(ValidationError):
        validate_card(bad)


def test_missing_and_empty_fields_rejected():
    data = make_card().as_dict()
    del data["en_word"]
    with pytest.raises(ValidationError):
        validate_card(data)
    data = make_card().as_dict()
    data["ja_word"] = "   "
    with pytest.raises(ValidationError):
        validate_card(data)


def test_wrong_type_and_too_long_rejected():
    data = make_card().as_dict()
    data["en_example"] = 5
    with pytest.raises(ValidationError):
        validate_card(data)
    data = make_card().as_dict()
    data["en_example"] = "x" * 201
    with pytest.raises(ValidationError):
        validate_card(data)


def test_note_may_be_empty():
    assert validate_card(make_card(note="").as_dict()).note == ""


def test_kana_and_romaji_must_match_script():
    with pytest.raises(ValidationError):
        validate_card(make_card(ja_kana="傘").as_dict())
    with pytest.raises(ValidationError):
        validate_card(make_card(ja_romaji="かさ").as_dict())
    assert validate_card(make_card(ja_kana="リュックサック", ja_romaji="ryukkusakku").as_dict())


def test_keys_normalise_case_and_width():
    assert en_key("  Umbrella ") == en_key("umbrella") == "umbrella"
    assert en_key("Coffee   Mug") == "coffee mug"
    assert ja_key(" ﾏｸﾞｶｯﾌﾟ ") == ja_key("マグカップ")
