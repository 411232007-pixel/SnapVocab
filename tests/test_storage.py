from snapvocab.storage import Database

from .conftest import make_card

ALICE, BOB = "111", "222"


def test_add_and_get_by_owner_only(db):
    saved = db.add_record(ALICE, make_card())
    assert db.get(ALICE, saved.record.id).card.en_word == "umbrella"
    assert db.get(BOB, saved.record.id) is None  # cannot read another user's id


def test_duplicate_word_counts_but_stays_distinct(db):
    first = db.add_record(ALICE, make_card())
    second = db.add_record(ALICE, make_card(en_word="Umbrella "))
    assert first.times_seen == 1
    assert second.times_seen == 2
    assert second.first_seen_at == first.record.created_at
    stats = db.stats(ALICE)
    assert (stats.total, stats.distinct) == (2, 1)


def test_different_word_increases_distinct(db):
    db.add_record(ALICE, make_card())
    db.add_record(ALICE, make_card(zh_name="馬克杯", en_word="mug", ja_word="マグカップ",
                                   ja_kana="マグカップ", ja_romaji="magukappu"))
    stats = db.stats(ALICE)
    assert (stats.total, stats.distinct) == (2, 2)


def test_users_are_isolated(db):
    db.add_record(ALICE, make_card())
    db.add_record(BOB, make_card(en_word="mug"))
    assert [r.card.en_word for r in db.recent(ALICE)] == ["umbrella"]
    assert [r.card.en_word for r in db.all_records(BOB)] == ["mug"]
    assert db.stats(BOB).total == 1
    # Bob saving the same word does not count towards Alice's times_seen
    assert db.add_record(BOB, make_card()).times_seen == 1


def test_recent_is_newest_first_and_limited(db):
    for i in range(12):
        db.add_record(ALICE, make_card(en_word=f"word{i}"))
    recent = db.recent(ALICE, 10)
    assert len(recent) == 10
    assert recent[0].card.en_word == "word11"


def test_empty_user(db):
    assert db.recent(ALICE) == []
    assert db.all_records(ALICE) == []
    stats = db.stats(ALICE)
    assert (stats.total, stats.distinct) == (0, 0)


def test_sql_injection_text_is_stored_literally(db):
    evil = "x'); DROP TABLE records;--"
    db.add_record(ALICE, make_card(note=evil))
    assert db.recent(ALICE)[0].card.note == evil
    assert db.stats(ALICE).total == 1


def test_persists_across_instances(tmp_path):
    path = tmp_path / "v.db"
    Database(path).add_record(ALICE, make_card())
    reopened = Database(path)  # simulates a bot restart
    assert reopened.stats(ALICE).total == 1
    assert reopened.recent(ALICE)[0].card.zh_name == "雨傘"
