"""Калибровка работодателя. Функция 25 UX-карты (экран E17), раздел 66 тех-доки.

UX-карта описывает поведение, но не алгоритм: «3-5 тестовых профилей с
разными компромиссами по желательным критериям», работодатель отмечает
«подходит»/«не подходит» по каждому, дальше — `calibration choices ->
weights for preferred criteria`. Явное требование: «не использовать реальные
персональные данные без необходимости» — профили ниже полностью синтетические
и не связаны ни с одним кандидатом.

Генерация — инженерное решение (в документах деталей нет): сбалансированный
план, где каждый желательный критерий «выполнен» примерно в половине карточек
и «не выполнен» в другой половине — так решения работодателя действительно
разделяют критерии по важности, а не просто повторяют один и тот же паттерн.

Карточки не сохраняются: `pattern_token` — не секрет и не ссылка на запись
в БД, а буквально сериализованный паттерн («какие типы критериев отмечены
как выполненные»), потому что калибровка работает только с собственной
вакансией работодателя и не раскрывает ничего постороннего.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.enums import CriterionType
from app.vacancies.models import VacancyCriterion

MIN_WEIGHT = Decimal("0.2")
MAX_WEIGHT = Decimal("2.0")
MIN_PROFILES = 3
MAX_PROFILES = 5


@dataclass(frozen=True)
class CalibrationCriterionView:
    type: CriterionType
    matches: bool
    value_label: str


@dataclass(frozen=True)
class CalibrationProfile:
    pattern_token: str
    criteria: list[CalibrationCriterionView]


def generate_test_profiles(criteria: list[VacancyCriterion]) -> list[CalibrationProfile]:
    """Синтетические тестовые карточки по желательным критериям вакансии.

    Пусто, если у вакансии нет желательных критериев — калибровать нечего
    (обязательные критерии калибровка не трогает: они решаются соответствием,
    не весом, раздел 62 тех-доки / `app.matching.ranking`).
    """
    desirable = _unique_desirable(criteria)
    if not desirable:
        return []

    profile_count = min(MAX_PROFILES, max(MIN_PROFILES, len(desirable)))
    profiles = []
    for index in range(profile_count):
        views = [
            _criterion_view(criterion, matches=(index + position) % 2 == 0)
            for position, criterion in enumerate(desirable)
        ]
        profiles.append(
            CalibrationProfile(
                pattern_token=_encode_pattern(views), criteria=views
            )
        )
    return profiles


def compute_weights(
    criteria: list[VacancyCriterion], votes: dict[str, bool]
) -> dict[CriterionType, Decimal]:
    """Веса из решений работодателя по тестовым карточкам.

    `votes` — `{pattern_token: fit}`, ровно то, что вернул
    `generate_test_profiles` этому же набору критериев. Токен, который не
    удалось разобрать (устарел/чужая вакансия), просто пропускается —
    работодатель мог обновить страницу между запросами.
    """
    desirable = _unique_desirable(criteria)
    if not desirable or not votes:
        return {}

    matched_fit = {criterion.type: 0 for criterion in desirable}
    matched_total = {criterion.type: 0 for criterion in desirable}
    unmatched_fit = {criterion.type: 0 for criterion in desirable}
    unmatched_total = {criterion.type: 0 for criterion in desirable}

    for token, fit in votes.items():
        matched_set = _decode_pattern(token)
        if matched_set is None:
            continue
        for criterion in desirable:
            matches = criterion.type in matched_set
            if matches:
                matched_total[criterion.type] += 1
                if fit:
                    matched_fit[criterion.type] += 1
            else:
                unmatched_total[criterion.type] += 1
                if fit:
                    unmatched_fit[criterion.type] += 1

    weights: dict[CriterionType, Decimal] = {}
    for criterion in desirable:
        matched_n = matched_total[criterion.type]
        unmatched_n = unmatched_total[criterion.type]
        if not matched_n or not unmatched_n:
            continue
        matched_rate = Decimal(matched_fit[criterion.type]) / matched_n
        unmatched_rate = Decimal(unmatched_fit[criterion.type]) / unmatched_n
        weight = Decimal("1") + (matched_rate - unmatched_rate)
        weights[criterion.type] = min(max(weight, MIN_WEIGHT), MAX_WEIGHT)
    return weights


def _unique_desirable(criteria: list[VacancyCriterion]) -> list[VacancyCriterion]:
    """Один критерий на тип: контракт не запрещает дубли, но калибровать
    отдельно две карточки одного типа нечем — берётся первая."""
    seen: set[CriterionType] = set()
    result = []
    for criterion in criteria:
        if criterion.required or criterion.type in seen:
            continue
        seen.add(criterion.type)
        result.append(criterion)
    return result


def _criterion_view(
    criterion: VacancyCriterion, *, matches: bool
) -> CalibrationCriterionView:
    value = criterion.value if isinstance(criterion.value, dict) else {}
    return CalibrationCriterionView(
        type=criterion.type,
        matches=matches,
        value_label=_value_label(criterion.type, value, matches),
    )


def _value_label(criterion_type: CriterionType, value: dict, matches: bool) -> str:
    match criterion_type:
        case CriterionType.LOCATION:
            city = _first_string(value, "city", "cities") or "нужный город"
            return city if matches else "другой город"
        case CriterionType.SCHEDULE:
            schedule = _first_string(value, "schedule", "schedules") or "нужный график"
            return schedule if matches else "другой график"
        case CriterionType.SALARY:
            limit = value.get("max")
            label = f"ожидания в пределах {limit} ₽" if limit else "ожидания в пределах вилки"
            return label if matches else "ожидания выше вилки"
        case CriterionType.AVAILABLE_FROM:
            return "готов выйти вовремя" if matches else "готов выйти позже срока"
        case CriterionType.EXPERIENCE:
            minimum = value.get("min_months")
            if minimum:
                return f"опыт {minimum}+ мес." if matches else f"опыт меньше {minimum} мес."
            return "опыт достаточный" if matches else "опыта недостаточно"
        case CriterionType.CERTIFICATE:
            name = value.get("name") or "документ"
            return f"есть «{name}»" if matches else f"нет «{name}»"
        case _:
            return "выполнен" if matches else "не выполнен"


def _first_string(value: dict, single_key: str, many_key: str) -> str | None:
    single = value.get(single_key)
    if isinstance(single, str) and single.strip():
        return single.strip()
    many = value.get(many_key)
    if isinstance(many, list):
        for item in many:
            if isinstance(item, str) and item.strip():
                return item.strip()
    return None


def _encode_pattern(views: list[CalibrationCriterionView]) -> str:
    """Типы, выполненные в этом профиле, через запятую — сортировка не
    важна, декодер читает это как множество."""
    matched = sorted(view.type.value for view in views if view.matches)
    return ",".join(matched) or "-"


def _decode_pattern(token: str) -> set[CriterionType] | None:
    """Множество типов, отмеченных как «выполненные» в этом профиле. Какие
    типы были «не выполнены», отдельно не кодируется — `compute_weights`
    знает это из текущего списка желательных критериев вакансии."""
    if not token:
        return None
    matched_values = set() if token == "-" else set(token.split(","))
    try:
        return {CriterionType(value) for value in matched_values}
    except ValueError:
        return None
