"""Денежные суммы в API.

Зарплаты хранятся в NUMERIC(12, 2). Одно и то же число может прийти в API
в разном виде: из тела запроса, из свежесозданного объекта Tortoise (он
нормализует значение) или из БД. Чтобы frontend не получал то `70000.00`,
то `7E+4`, все суммы приводятся к масштабу колонки.
"""

from decimal import Decimal
from typing import Annotated

from pydantic import AfterValidator

MONEY_MAX_DIGITS = 12
MONEY_DECIMAL_PLACES = 2

_QUANTUM = Decimal(1).scaleb(-MONEY_DECIMAL_PLACES)


def quantize_money(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return value.quantize(_QUANTUM)


# Сумма, уже проверенная на допустимое число знаков, в едином формате
Money = Annotated[Decimal, AfterValidator(quantize_money)]
