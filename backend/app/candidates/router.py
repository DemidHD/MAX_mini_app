"""Эндпоинты профиля кандидата. Раздел 27 тех-доки."""

from fastapi import APIRouter, File, UploadFile, status
from fastapi.responses import FileResponse

from app.ai.schemas import ParseResumeResponse
from app.auth.dependencies import CandidateUser
from app.candidates import service
from app.candidates.schemas import CandidateProfileRead, CandidateProfileUpdateRequest
from app.core.config import settings
from app.core.storage import ensure_resume_size

router = APIRouter(prefix="/candidate", tags=["candidate"])


@router.get("/profile", response_model=CandidateProfileRead)
async def get_profile(user: CandidateUser) -> CandidateProfileRead:
    """Профиль текущего кандидата. Если профиля ещё нет — 404."""
    return CandidateProfileRead.from_profile(await service.get_profile(user))


@router.patch("/profile", response_model=CandidateProfileRead)
async def update_profile(
    payload: CandidateProfileUpdateRequest, user: CandidateUser
) -> CandidateProfileRead:
    """Создаёт профиль при первом обращении, затем меняет переданные поля."""
    return CandidateProfileRead.from_profile(await service.save_profile(user, payload))


@router.get("/resume", response_class=FileResponse)
async def get_resume(user: CandidateUser) -> FileResponse:
    """Отдаёт файл резюме текущего кандидата. Чужой файл получить нельзя."""
    profile = await service.get_profile(user)
    path = service.get_resume_file(profile)
    return FileResponse(path)


@router.patch("/resume", response_model=CandidateProfileRead)
async def set_resume(
    user: CandidateUser, file: UploadFile = File(...)
) -> CandidateProfileRead:
    """Загружает резюме (PDF/DOCX), а если оно уже есть — заменяет его."""
    if file.size is not None:
        ensure_resume_size(file.size)
    content = await file.read(settings.resume_max_size_bytes + 1)
    profile = await service.set_resume(user, content)
    return CandidateProfileRead.from_profile(profile)


@router.delete("/resume", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(user: CandidateUser) -> None:
    await service.delete_resume(user)


@router.post("/resume/parse", response_model=ParseResumeResponse)
async def parse_resume(user: CandidateUser) -> ParseResumeResponse:
    """Черновик полей профиля из текста резюме — ничего не сохраняет."""
    return await service.parse_resume(user)


@router.post("/resume/draft", response_model=ParseResumeResponse)
async def parse_resume_draft(
    _: CandidateUser, file: UploadFile = File(...)
) -> ParseResumeResponse:
    """Черновик полей профиля прямо из файла резюме, без сохранённого профиля
    и без сохранения файла (см. `service.parse_resume_draft`)."""
    if file.size is not None:
        ensure_resume_size(file.size)
    content = await file.read(settings.resume_max_size_bytes + 1)
    return await service.parse_resume_draft(content)
