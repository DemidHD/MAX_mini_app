"""Локальное файловое хранилище.

Раздел 3: бинарное содержимое файлов в PostgreSQL не хранится, в БД лежит
только путь. Структура — `storage/avatars/{user_id}/avatar.{ext}`.
"""

import io
import logging
import os
import zipfile
from pathlib import Path
from uuid import uuid4

from app.core.config import settings
from app.core.errors import ValidationError

logger = logging.getLogger("app.storage")

# Расширение определяется по фактическому содержимому, а не по имени файла
MIME_TO_EXTENSION = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

# Сигнатуры начала файла для проверки, что содержимое соответствует типу
MAGIC_BYTES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/webp": (b"RIFF",),
}

# Функция 29 UX-карты (C11 «Импорт резюме»)
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
RESUME_MIME_TO_EXTENSION = {
    "application/pdf": "pdf",
    DOCX_MIME: "docx",
}


class FileTooLargeError(ValidationError):
    code = "file_too_large"
    message = "Файл слишком большой"


class UnsupportedFileTypeError(ValidationError):
    code = "unsupported_file_type"
    message = "Неподдерживаемый тип файла"


def detect_avatar_mime(content: bytes) -> str:
    """Определяет тип изображения по содержимому и сверяет его с белым списком."""
    for mime, signatures in MAGIC_BYTES.items():
        if not any(content.startswith(signature) for signature in signatures):
            continue
        if mime == "image/webp" and content[8:12] != b"WEBP":
            continue
        if mime not in settings.avatar_allowed_mime_types:
            raise UnsupportedFileTypeError(f"Тип {mime} не разрешён")
        return mime
    raise UnsupportedFileTypeError()


def ensure_avatar_size(size: int) -> None:
    if size == 0:
        raise ValidationError("Файл пустой", code="empty_file")
    if size > settings.avatar_max_size_bytes:
        raise FileTooLargeError(
            f"Максимальный размер аватарки — {settings.avatar_max_size_bytes} байт"
        )


def detect_resume_mime(content: bytes) -> str:
    """PDF определяется по сигнатуре `%PDF-`. DOCX — это ZIP-контейнер:
    общая сигнатура `PK\\x03\\x04` есть у любого OOXML/ZIP, поэтому
    дополнительно проверяется, что внутри есть `word/document.xml` — так же,
    как webp дополнительно проверяет подпись `WEBP` после `RIFF`."""
    if content.startswith(b"%PDF-"):
        return "application/pdf"
    if content.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if "word/document.xml" in archive.namelist():
                    return DOCX_MIME
        except zipfile.BadZipFile:
            pass
    raise UnsupportedFileTypeError()


def ensure_resume_size(size: int) -> None:
    if size == 0:
        raise ValidationError("Файл пустой", code="empty_file")
    if size > settings.resume_max_size_bytes:
        raise FileTooLargeError(
            f"Максимальный размер резюме — {settings.resume_max_size_bytes} байт"
        )


def save_resume(user_id: int, content: bytes, mime: str) -> Path:
    """Сохраняет резюме и возвращает путь для записи в БД. Тот же приём, что
    и `save_avatar`: каталог — по `user_id` из сессии, имя — по токену, а не
    по присланному имени файла."""
    directory = settings.resumes_dir / str(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    path = directory / f"resume-{token}.{RESUME_MIME_TO_EXTENSION[mime]}"
    temporary_path = directory / f".{token}.tmp"
    try:
        with temporary_path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    except BaseException:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Не удалось удалить временный файл: %s", temporary_path)
        raise
    return path


def extract_resume_text(content: bytes, mime: str) -> str | None:
    """Лучшее старание (раздел 57): повреждённый/нестандартный файл не должен
    ронять загрузку — кандидат просто не получит текст для разбора и
    заполнит профиль вручную (состояние «Ошибка -> ручное заполнение» C11)."""
    try:
        if mime == "application/pdf":
            return _extract_pdf_text(content)
        if mime == DOCX_MIME:
            return _extract_docx_text(content)
    except Exception:  # noqa: BLE001 — парсинг стороннего файла непредсказуем
        logger.warning("Не удалось извлечь текст резюме", exc_info=True)
    return None


def _extract_pdf_text(content: bytes) -> str | None:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    return text.strip() or None


def _extract_docx_text(content: bytes) -> str | None:
    from docx import Document

    document = Document(io.BytesIO(content))
    text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    return text.strip() or None


def save_avatar(user_id: int, content: bytes, mime: str) -> Path:
    """Сохраняет аватарку и возвращает путь для записи в БД.

    Каталог определяется по `user_id` из сессии, имя файла — по типу содержимого,
    поэтому данные пользователя в путь не попадают.
    """
    directory = settings.avatars_dir / str(user_id)
    directory.mkdir(parents=True, exist_ok=True)
    token = uuid4().hex
    path = directory / f"avatar-{token}.{MIME_TO_EXTENSION[mime]}"
    temporary_path = directory / f".{token}.tmp"
    try:
        with temporary_path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_path.replace(path)
    except BaseException:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            logger.exception("Не удалось удалить временный файл: %s", temporary_path)
        raise
    return path


def delete_file(path: str | Path | None) -> None:
    """Удаляет файл хранилища. Путь за пределами `storage/` игнорируется."""
    if not path:
        return
    target = Path(path)
    try:
        resolved = target.resolve()
        resolved.relative_to(settings.storage_root.resolve())
    except (ValueError, OSError):
        logger.warning("Попытка удалить файл вне хранилища")
        return
    try:
        resolved.unlink(missing_ok=True)
    except OSError:
        # После фиксации нового состояния в БД старый файл уже недоступен через
        # API. Ошибка очистки не должна откатывать успешную операцию БД.
        logger.exception("Не удалось удалить файл из хранилища: %s", resolved)


def resolve_stored_file(path: str | Path | None) -> Path | None:
    """Возвращает путь, только если файл лежит внутри хранилища и существует."""
    if not path:
        return None
    try:
        resolved = Path(path).resolve()
        resolved.relative_to(settings.storage_root.resolve())
    except (ValueError, OSError):
        logger.warning("Путь к файлу вне хранилища отклонён")
        return None
    return resolved if resolved.is_file() else None
