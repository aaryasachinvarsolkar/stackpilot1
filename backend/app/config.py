from typing import List, Union
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
import os


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PORT: int = 8000
    # Loopback only: there is no authentication yet. Never default to 0.0.0.0.
    HOST: str = "127.0.0.1"
    
    # CORS Origins (comma-separated or list)
    CORS_ORIGINS: Union[str, List[str]] = "http://localhost:3000,http://127.0.0.1:3000"
    
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./stackpilot.db"

    # Workspaces: directory that holds one folder per project. Empty = <backend>/workspaces.
    WORKSPACES_ROOT: str = ""
    # Largest file the file API will read or write (bytes).
    MAX_FILE_SIZE_BYTES: int = 2 * 1024 * 1024

    # AI Providers
    LLM_PROVIDER: str = "mock"
    LLM_API_KEY: str = "mock-key"
    LLM_MODEL: str = "gpt-4o"
    
    EMBEDDING_PROVIDER: str = "mock"
    EMBEDDING_API_KEY: str = "mock-key"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    
    # Auth
    JWT_SECRET: str = "dev-secret-stackpilot-jwt-token-change-in-production-min-32-chars"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    
    # Sandbox
    DOCKER_SANDBOX_ENABLED: bool = False
    DOCKER_SANDBOX_TIMEOUT_SECONDS: int = 60
    
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @field_validator("CORS_ORIGINS", mode="after")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [i.strip() for i in v.split(",") if i.strip()]
        return v


settings = Settings()
