import os
from typing import Any

import certifi
from fastapi.security import APIKeyHeader
from pydantic import Field
from pydantic_settings import BaseSettings


os.environ['SSL_CERT_FILE'] = certifi.where()

class Config(BaseSettings):
    ORGANIZATION_ID: int = Field(..., env="ORGANIZATION_ID")
    ORGANIZATION_SLUG: str = Field(..., env="ORGANIZATION_SLUG")

    BACKEND_API_URL: str = Field("https://api.samscloud.io/api/v2", env="BACKEND_API_URL")
    BACKEND_API_KEY: str = Field(..., env="BACKEND_API_KEY")

    # AWS
    AWS_REGION: str = Field("us-west-2", env="AWS_REGION")
    AWS_ACCESS_KEY_ID: str = Field(..., env="AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY: str = Field(..., env="AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME: str = Field("user-faces-dataset", env="STORAGE_BUCKET_NAME")

    SHINOBI_URL: str = Field("https://127.0.0.1:8000", env="SHINOBI_URL")

    USER_NOTIFICATION_DELAY_SECONDS: int = Field(30, env="USER_NOTIFICATION_DELAY_SECONDS")

    API_KEY_NAME: str = Field("api-key", env="API_KEY_NAME")
    API_KEY: str = Field(..., env="API_KEY")

    class Config:
        env_prefix = ""
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = None


settings = Config()
api_key_header = APIKeyHeader(name=settings.API_KEY_NAME, auto_error=False)
app_configs: dict[str, Any] = {"title": "App API"}
