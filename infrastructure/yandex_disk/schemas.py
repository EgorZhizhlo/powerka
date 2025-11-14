from pydantic import BaseModel
from typing import Optional
from datetime import date


class OperationMetadata(BaseModel):
    """Метаданные для операций с файлами/папками."""
    company_name: Optional[str] = None
    employee_fio: Optional[str] = None
    verification_date: Optional[date] = None
    act_series: Optional[str] = None
    act_number: Optional[str] = None


class DocumentMetadata(BaseModel):
    """Метаданные для структурированного хранения документов."""
    company_name: str
    employee_fio: str
    verification_date: date
    act_series: str
    act_number: str


class FileInfo(BaseModel):
    """Информация о загруженном файле."""
    filename: str
    original_filename: str
    remote_path: str
    public_url: Optional[str]
    size_bytes: int
    compressed: bool = False
