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

    # Host names the API answers to (the request's Host header). Loopback names only: with no authentication, a page on
    # another site could otherwise reach the API through DNS rebinding. Names only, no ports; "*" is refused.
    ALLOWED_HOSTS: Union[str, List[str]] = "127.0.0.1,localhost"

    # Database (always anchor default sqlite file to backend folder)
    DATABASE_URL: str = f"sqlite+aiosqlite:///{os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'stackpilot.db').replace('\\', '/')}"

    # Workspaces: directory that holds one folder per project. Empty = <backend>/workspaces.
    WORKSPACES_ROOT: str = ""
    # Largest file the file API will read or write (bytes).
    MAX_FILE_SIZE_BYTES: int = 2 * 1024 * 1024
    # Project imports (ZIP upload and GitHub download). All three are enforced on the bytes actually read or written,
    # never on what a header or an archive claims.
    MAX_UPLOAD_BYTES: int = 50 * 1024 * 1024  # largest ZIP accepted (uploaded or downloaded)
    MAX_ZIP_UNCOMPRESSED_BYTES: int = 200 * 1024 * 1024  # largest total size of the files extracted from it
    MAX_ZIP_ENTRIES: int = 5000  # most entries (files and folders) it may contain

    # Privacy switch for AI chat. While False, nothing a user typed or any project code is ever sent to an external AI
    # provider, even when LLM_PROVIDER and LLM_API_KEY are set. Environment only: there is deliberately no API, setting
    # in the database or UI toggle for it, so a page or a request can never turn it on.
    ALLOW_SENDING_CODE_TO_PROVIDER: bool = False

    # Safety switch for "Run the whole project". While False, no project code is ever started: no install step, no server.
    # Turning it on lets the Run tab execute the uploaded project's own commands on this computer (inside its own folder,
    # bound to 127.0.0.1, with a clean environment that does not include StackPilot's keys). Environment only, like the
    # switch above: there is deliberately no API, database setting or UI toggle, so a page or a request can never turn it on.
    ALLOW_RUNNING_PROJECT_CODE: bool = False
    # Where per-project virtual environments and install markers live. Empty = <backend>/runtime.
    RUNTIME_ROOT: str = ""

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

    @field_validator("ALLOWED_HOSTS", mode="after")
    @classmethod
    def assemble_allowed_hosts(cls, v: Union[str, List[str]]) -> List[str]:
        hosts = [i.strip().lower() for i in (v.split(",") if isinstance(v, str) else v) if i and i.strip()]
        if not hosts:
            raise ValueError("ALLOWED_HOSTS must name at least one host.")
        for host in hosts:
            if "*" in host or "/" in host or "@" in host or ":" in host or " " in host:
                raise ValueError(f"ALLOWED_HOSTS entry {host!r} must be a plain host name (no wildcard, scheme, port or path).")
        return hosts

    @field_validator("MAX_UPLOAD_BYTES", "MAX_ZIP_UNCOMPRESSED_BYTES", "MAX_ZIP_ENTRIES", mode="after")
    @classmethod
    def import_limits_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("Import limits must be at least 1.")
        return v

    @field_validator("DATABASE_URL", mode="after")
    @classmethod
    def assemble_database_url(cls, v: str) -> str:
        if v.startswith("sqlite+aiosqlite:///."):
            backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_file = os.path.join(backend_dir, "stackpilot.db").replace("\\", "/")
            return f"sqlite+aiosqlite:///{db_file}"
        return v


settings = Settings()
