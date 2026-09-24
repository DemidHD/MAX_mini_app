"""Конфигурация приложения. Единственный источник значений — environment variables."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# .env лежит в корне репозитория и читается по абсолютному пути: иначе значения
# подхватывались бы только при запуске из корня, а из backend/ (pytest, uvicorn)
# молча брались бы значения по умолчанию. В Docker файла нет — там env vars.
_REPO_ROOT = Path(__file__).resolve().parents[3]
_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Более поздний файл переопределяет более ранний
        env_file=(_REPO_ROOT / ".env", _BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Приложение ---
    app_env: str = "development"
    app_url: str = "http://localhost:8000"
    log_level: str = "INFO"

    # --- База данных ---
    database_url: str = "postgres://max_hiring:change_me@postgres:5432/max_hiring"
    # DSN для pytest. database_url указывает на хост `postgres` из сети Docker,
    # с машины разработчика это имя не резолвится — тесты ходят на localhost.
    test_database_url: str = ""

    # --- MAX ---
    # Проверка подписи initData и Bot API. Секрет живёт только на backend.
    max_bot_token: str = ""
    # Секрет webhook'а — отдельный от токена бота (раздел 41 тех-доки).
    max_webhook_secret: str = ""
    # Публичное имя бота (без @) — нужно кнопке "открыть приложение"
    # (`OpenAppButton.web_app`, `maxapi`), не для проверки подписи.
    max_bot_username: str = ""

    # --- Сессии ---
    session_secret: str = ""
    session_ttl_hours: int = 720
    session_cookie_name: str = "max_hiring_session"
    auth_date_max_age_seconds: int = 86400
    auth_rate_limit_requests: int = 120
    auth_rate_limit_window_seconds: int = 60
    session_cleanup_interval_seconds: int = 300
    # Раздел 78: отклик — одна из операций, которым нужна защита.
    # Ключ — пользователь сессии, а не адрес: отклик доступен только
    # авторизованному кандидату.
    apply_rate_limit_requests: int = 30
    apply_rate_limit_window_seconds: int = 60
    # Раздел 78 называет бронирование второй операцией, которой нужна защита
    book_rate_limit_requests: int = 30
    book_rate_limit_window_seconds: int = 60

    # --- Вакансии ---
    # Ограничение не из тех-доки — продуктовое решение против засорения
    # кабинета брошенными черновиками. Считаются только `status = draft`;
    # публикация освобождает место.
    vacancy_draft_limit: int = 5

    # --- Фото вакансии (не из тех-доки) ---
    # Openverse — открытый каталог Creative Commons изображений, поиск
    # без API-ключа (docs.openverse.org). Тема — `vacancy.title`.
    vacancy_image_search_enabled: bool = True
    openverse_api_url: str = "https://api.openverse.org/v1/images/"
    vacancy_image_candidate_count: int = 20
    vacancy_image_search_timeout_seconds: float = 5.0
    # Проверка "жива ли ссылка" выполняется синхронно при каждом открытии
    # карточки вакансии — короткий таймаут, чтобы битый хостинг не подвешивал запрос
    vacancy_image_liveness_timeout_seconds: float = 3.0

    # --- Интервью ---
    # Границы длительности слота тех-дока не задаёт (раздел 22 описывает
    # только начало и конец). Ограничения нужны, чтобы работодатель не завёл
    # слот на одну секунду или на месяц, и вынесены в конфигурацию.
    interview_slot_min_duration_minutes: int = 5
    interview_slot_max_duration_hours: int = 8

    # --- Уведомления и бот (разделы 44-51) ---
    # Канал уведомлений можно выключить, не трогая остальной backend:
    # без бота P0-маршрут работает целиком, теряются только сообщения в MAX.
    bot_enabled: bool = True
    max_webhook_path: str = "/webhook/max"
    # Адрес, который регистрируется в MAX. Пусто — берётся APP_URL + путь выше.
    max_webhook_url: str = ""
    notification_max_attempts: int = 3
    notification_retry_delay_seconds: float = 0.5
    # Часовой пояс, в котором пользователю показывается время собеседования
    notification_timezone: str = "Europe/Moscow"

    # --- Локальное файловое хранилище ---
    storage_root: Path = Path("/app/storage")
    avatar_max_size_bytes: int = 5 * 1024 * 1024
    # NoDecode: значение приходит списком через запятую, а не JSON
    avatar_allowed_mime_types: Annotated[list[str], NoDecode] = [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]

    # --- AI (P1, раздел 58) ---
    # Общие переменные раздела 71 тех-доки — историческая заглушка под один
    # провайдер. Реальная интеграция сделана двумя провайдерами ниже, чтобы
    # отказ или перегрузка одного не переключали сценарий на ручной ввод
    # (раздел 57), пока жив другой.
    ai_api_url: str = ""
    ai_api_key: str = ""
    ai_request_timeout_seconds: float = 15.0
    # Порядок провайдеров текстовой генерации (`parse-vacancy`): первый
    # доступный побеждает, остальные — резерв на случай отказа/перегрузки.
    # Значение можно поменять без деплоя кода — только переменной окружения.
    ai_provider_order: Annotated[list[str], NoDecode] = ["gigachat", "yandexgpt"]

    # GigaChat (https://developers.sber.ru/docs/ru/gigachat/api/overview)
    gigachat_auth_key: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_oauth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    gigachat_api_url: str = "https://gigachat.devices.sberbank.ru/api/v1"
    gigachat_model: str = "GigaChat"
    # GigaChat отдаёт сертификат, подписанный CA Минцифры, которого нет в
    # системном хранилище доверенных сертификатов. Файл — публичный корневой
    # сертификат (не секрет), лежит в репозитории и коммитится в git;
    # относительный путь резолвится от backend/ через свойство ниже — работает
    # одинаково локально, в Docker (`COPY . .` в Dockerfile) и на сервере,
    # независимо от текущей рабочей директории процесса.
    gigachat_ca_bundle_file: str = "certs/russian_trusted_root_ca.crt"
    # Отключать проверку — на свой риск и только для отладки без CA-бандла.
    gigachat_verify_ssl: bool = True

    # YandexGPT и SpeechKit — через официальный `yandex-ai-studio-sdk` (gRPC),
    # поэтому REST-адреса не нужны: эндпоинт SDK резолвит сам по `folder_id`.
    yandex_api_key: str = ""
    yandex_folder_id: str = ""
    yandex_gpt_model: str = "yandexgpt"

    # Yandex SpeechKit — голосовой ввод вакансии (`transcribe-vacancy`).
    # Отдельный ключ, потому что в Yandex Cloud это часто отдельный сервисный
    # аккаунт; если не задан, используется `yandex_api_key`.
    yandex_speechkit_api_key: str = ""
    yandex_speechkit_lang: str = "ru-RU"

    @field_validator("avatar_allowed_mime_types", "ai_provider_order", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def yandex_speechkit_key(self) -> str:
        return self.yandex_speechkit_api_key or self.yandex_api_key

    @property
    def gigachat_ca_bundle_path(self) -> str:
        """Абсолютный путь к CA-бандлу GigaChat, независимо от рабочей директории.

        `httpx`/`ssl` открывают относительный путь относительно CWD процесса,
        а она отличается между pytest, `uvicorn` из `backend/` и Docker
        (`WORKDIR /app`). Абсолютный путь от `backend/` устраняет разницу.
        """
        if not self.gigachat_ca_bundle_file:
            return ""
        path = Path(self.gigachat_ca_bundle_file)
        if not path.is_absolute():
            path = _BACKEND_ROOT / path
        return str(path)

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"production", "prod"}

    @property
    def avatars_dir(self) -> Path:
        return self.storage_root / "avatars"

    @property
    def resumes_dir(self) -> Path:
        return self.storage_root / "resumes"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
