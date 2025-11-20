import filetype

from core.config import settings
from core.exceptions.api.common import BadRequestError


def validate_image(image: bytes):
    """Проверка формата изображения (JPEG/PNG)"""
    img_size_mb = settings.image_max_size_mb // (1024 * 1024)
    if len(image) > settings.image_max_size_mb:
        raise BadRequestError(
            detail=f"Размер изображения не более {img_size_mb} МБ!"
        )
    kind = filetype.guess(image)
    if not kind or kind.extension not in settings.allowed_photo_ext or \
            kind.mime not in settings.allowed_image_formats:
        raise BadRequestError(
            detail="Изображение должно быть в формате 'jpeg', 'jpg' или 'png'!"
        )


def validate_pdf(document: bytes):
    """Проверка PDF-файла"""
    doc_size_mb = settings.document_max_size_mb // (1024 * 1024)
    if len(document) > settings.document_max_size_mb:
        raise BadRequestError(
            detail=f"Размер PDF не более {doc_size_mb} МБ!"
        )
    if not document.startswith(b"%PDF"):
        raise BadRequestError(
            detail="Файл должен быть PDF!"
        )
