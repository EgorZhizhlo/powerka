from itsdangerous import (
    URLSafeSerializer, URLSafeTimedSerializer,
    BadSignature, SignatureExpired
)

from core.config import settings
from core.exceptions.app.auth.token import (
    InvalidTokenError, TokenExpiredError
)
from access_control.tokens.jwt_versioning import bump_jwt_token_version


secret_key = settings.secret_key
salt = settings.salt
jwt_token_expiration = settings.jwt_token_expiration


async def create_token(data: dict) -> str:
    """
    Создаёт JWT-токен с таймаутом и полем версии.
    Версия берётся из Redis (инкрементируется).
    """
    user_id = data.get("id")
    version = await bump_jwt_token_version(f"user:{user_id}:auth_version")

    payload = {**data, "ver": version}
    serializer = URLSafeTimedSerializer(secret_key)
    return serializer.dumps(payload, salt=salt)


def verify_token(token: str) -> dict:
    """
    Проверяет JWT-токен с учётом max_age.
    При истечении выбрасывает TokenExpiredError,
    при неверной подписи — InvalidTokenError.
    """
    serializer = URLSafeTimedSerializer(secret_key)
    try:
        return serializer.loads(
            token,
            salt=salt,
            max_age=jwt_token_expiration
        )
    except SignatureExpired:
        raise TokenExpiredError
    except BadSignature:
        raise InvalidTokenError


async def create_untimed_token(data: dict) -> str:
    """
    Создаёт токен без таймаута (для списка компаний) с учётом версии.
    Версия берётся из Redis (инкрементируется).
    """
    user_id = data.get("id")
    version = await bump_jwt_token_version(f"user:{user_id}:company_version")

    payload = {**data, "ver": version}
    serializer = URLSafeSerializer(secret_key, salt=salt)
    return serializer.dumps(payload)


def verify_untimed_token(token: str) -> dict:
    """
    Проверяет токен без таймаута.
    При неверной подписи — InvalidTokenError.
    """
    serializer = URLSafeSerializer(secret_key, salt=salt)
    try:
        return serializer.loads(token)
    except BadSignature:
        raise InvalidTokenError
