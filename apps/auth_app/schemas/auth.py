from pydantic import BaseModel, ConfigDict, field_validator


class LoginRequestSchema(BaseModel):
    username: str
    password: str

    model_config = ConfigDict(from_attributes=True)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        return v.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Пароль должен содержать не менее 8 символов")
        return v.strip()
