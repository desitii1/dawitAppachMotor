from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://lottery:lottery@localhost:5432/dawit_lottery"
    admin_username: str = "owner"
    admin_password: str = ""
    session_secret: str = "development-only-change-me"
    telegram_bot_token: str = ""
    public_app_url: str = "http://localhost:3000"
    backend_cors_origins: str = "http://localhost:3000"
    attachment_root: str = "./data/attachments"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


settings = Settings()

