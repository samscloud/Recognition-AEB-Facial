from fastapi import Depends, HTTPException
from starlette import status

from src.config import api_key_header, settings


async def get_api_key(
    api_key: str = Depends(api_key_header),
):
    if api_key == settings.API_KEY:
        return api_key
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
