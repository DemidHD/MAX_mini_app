"""Проверка подписи initData. Раздел 6 тех-доки."""

from datetime import datetime, timedelta, timezone

import pytest

from app.auth.init_data import InitDataError, validate_init_data
from tests.factories import TEST_BOT_TOKEN, build_init_data, max_user_payload


def _validate(init_data: str, **kwargs):
    params = {"bot_token": TEST_BOT_TOKEN, "max_age_seconds": 86400} | kwargs
    return validate_init_data(init_data, **params)


def test_valid_init_data_returns_user() -> None:
    result = _validate(build_init_data())

    assert result.user.user_id == 100500
    assert result.user.first_name == "Иван"
    assert result.user.username == "ivan_petrov"
    assert result.user.language_code == "ru"


def test_tampered_hash_is_rejected() -> None:
    with pytest.raises(InitDataError):
        _validate(build_init_data(corrupt_hash=True))


def test_data_signed_by_another_token_is_rejected() -> None:
    with pytest.raises(InitDataError):
        _validate(build_init_data(bot_token="чужой-токен"))


def test_modified_user_breaks_signature() -> None:
    init_data = build_init_data()
    tampered = init_data.replace("100500", "999999")

    with pytest.raises(InitDataError):
        _validate(tampered)


def test_expired_auth_date_is_rejected() -> None:
    old = datetime.now(timezone.utc) - timedelta(days=2)

    with pytest.raises(InitDataError):
        _validate(build_init_data(auth_date=old))


def test_auth_date_from_future_is_rejected() -> None:
    future = datetime.now(timezone.utc) + timedelta(hours=2)

    with pytest.raises(InitDataError):
        _validate(build_init_data(auth_date=future))


def test_duplicated_hash_is_rejected() -> None:
    with pytest.raises(InitDataError):
        _validate(build_init_data() + "&hash=deadbeef")


def test_empty_init_data_is_rejected() -> None:
    with pytest.raises(InitDataError):
        _validate("")


def test_missing_bot_token_does_not_let_user_through() -> None:
    with pytest.raises(InitDataError):
        _validate(build_init_data(), bot_token="")


def test_user_without_id_is_rejected() -> None:
    payload = max_user_payload()
    del payload["id"]

    with pytest.raises(InitDataError):
        _validate(build_init_data(user=payload))


def test_optional_user_fields_may_be_missing() -> None:
    payload = max_user_payload(last_name=None, username=None, language_code=None)

    result = _validate(build_init_data(user=payload))

    assert result.user.last_name is None
    assert result.user.username is None
    assert result.user.language_code is None
