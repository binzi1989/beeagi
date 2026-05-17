from fastapi import HTTPException, Request, status

from app.core.config import get_settings

settings = get_settings()


def require_control_plane_api_key(request: Request) -> None:
    expected_key = settings.control_plane_api_key
    if not expected_key:
        return

    provided_key = request.headers.get(settings.control_plane_api_key_header)
    if provided_key != expected_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or missing control-plane api key",
        )
