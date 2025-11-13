from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import date


class DocumentMetadata(BaseModel):
    """Метаданные для структурированного хранения документов."""
    company_name: str = Field(
        ..., min_length=1, max_length=200,
        description="Название компании"
    )
    employee_fio: str = Field(
        ..., min_length=1, max_length=200,
        description="ФИО сотрудника"
    )
    document_date: date = Field(..., description="Дата документа")
    act_series: str = Field(
        ..., min_length=1, max_length=50,
        description="Серия акта"
    )
    act_number: str = Field(
        ..., min_length=1, max_length=50,
        description="Номер акта"
    )

    @field_validator('company_name', 'employee_fio', 'act_series', 'act_number')
    @classmethod
    def clean_path_component(cls, v: str) -> str:
        """Очистка строки от недопустимых символов для путей."""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            v = v.replace(char, '_')
        return v.strip()


class OperationMetadata(BaseModel):
    """Метаданные для операций с файлами/папками."""
    company_name: Optional[str] = Field(
        None, min_length=1, max_length=200,
        description="Название компании"
    )
    employee_fio: Optional[str] = Field(
        None, min_length=1, max_length=200,
        description="ФИО сотрудника"
    )
    document_date: Optional[date] = Field(None, description="Дата документа")
    act_series: Optional[str] = Field(
        None, min_length=1, max_length=50,
        description="Серия акта"
    )
    act_number: Optional[str] = Field(
        None, min_length=1, max_length=50,
        description="Номер акта"
    )

    @field_validator('company_name', 'employee_fio', 'act_series', 'act_number')
    @classmethod
    def clean_path_component(cls, v: Optional[str]) -> Optional[str]:
        """Очистка строки от недопустимых символов для путей."""
        if v is None:
            return None
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            v = v.replace(char, '_')
        return v.strip()


class FileInfo(BaseModel):
    """Информация о загруженном файле."""
    filename: str = Field(..., description="Имя файла")
    original_filename: str = Field(..., description="Оригинальное имя файла")
    remote_path: str = Field(..., description="Путь на Yandex Disk")
    public_url: Optional[str] = Field(None, description="Публичная ссылка")
    size_bytes: int = Field(..., description="Размер файла в байтах")
    compressed: bool = Field(False, description="Был ли файл сжат")


class BatchUploadResponse(BaseModel):
    """Ответ после пакетной загрузки файлов."""
    success: bool = Field(..., description="Успешность операции")
    uploaded_files: List[FileInfo] = Field(
        ...,
        description="Список загруженных файлов"
    )
    failed_files: List[dict] = Field(
        default_factory=list,
        description="Список файлов, которые не удалось загрузить"
    )
    total_files: int = Field(..., description="Общее количество файлов")
    successful_uploads: int = Field(..., description="Успешно загружено")
    folder_path: str = Field(..., description="Путь к папке на Yandex Disk")


class MoveFilesRequest(BaseModel):
    """Запрос на перенос файлов между актами."""
    source_metadata: OperationMetadata = Field(
        ...,
        description="Метаданные исходной папки"
    )
    destination_metadata: OperationMetadata = Field(
        ...,
        description="Метаданные папки назначения"
    )
    merge: bool = Field(
        False,
        description="Объединить с существующей папкой"
    )


class MoveFilesResponse(BaseModel):
    """Ответ на перенос файлов."""
    success: bool = Field(..., description="Успешность операции")
    source_path: str = Field(..., description="Исходный путь")
    destination_path: str = Field(..., description="Путь назначения")
    message: str = Field(..., description="Сообщение о результате")


class RenameRequest(BaseModel):
    """Запрос на переименование любого компонента пути."""
    metadata: OperationMetadata = Field(
        ...,
        description="Метаданные для идентификации ресурса"
    )
    new_company_name: Optional[str] = Field(
        None, description="Новое название компании"
    )
    new_employee_fio: Optional[str] = Field(
        None, description="Новое ФИО сотрудника"
    )
    new_document_date: Optional[date] = Field(
        None, description="Новая дата документа"
    )
    new_act_series: Optional[str] = Field(
        None, description="Новая серия акта"
    )
    new_act_number: Optional[str] = Field(
        None, description="Новый номер акта"
    )

    @field_validator('new_company_name', 'new_employee_fio', 'new_act_series', 'new_act_number')
    @classmethod
    def clean_path_component(cls, v: Optional[str]) -> Optional[str]:
        """Очистка строки от недопустимых символов для путей."""
        if v is None:
            return None
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            v = v.replace(char, '_')
        return v.strip()


class RenameResponse(BaseModel):
    """Ответ на переименование."""
    success: bool = Field(..., description="Успешность операции")
    old_path: str = Field(..., description="Старый путь")
    new_path: str = Field(..., description="Новый путь")


class DeleteRequest(BaseModel):
    """Запрос на удаление по метаданным."""
    metadata: OperationMetadata = Field(
        ...,
        description="Метаданные для идентификации ресурса"
    )
    permanently: bool = Field(
        True,
        description="Удалить навсегда или в корзину"
    )


class DeleteResponse(BaseModel):
    """Ответ на удаление."""
    success: bool = Field(..., description="Успешность операции")
    path: str = Field(..., description="Удаленный путь")
    permanently: bool = Field(..., description="Удалено навсегда")


class GetContentsRequest(BaseModel):
    """Запрос на получение содержимого."""
    metadata: OperationMetadata = Field(
        ...,
        description="Метаданные для идентификации папки"
    )


class FolderContentsResponse(BaseModel):
    """Содержимое папки."""
    path: str = Field(..., description="Путь к папке")
    items: List[dict] = Field(..., description="Содержимое папки")
    total_items: int = Field(..., description="Количество элементов")


class ErrorResponse(BaseModel):
    """Ошибка."""
    detail: str = Field(..., description="Описание ошибки")
