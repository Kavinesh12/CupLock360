from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CUPLOCK_", extra="ignore")

    env: str = "dev"  # dev | test | prod
    database_url: str = "postgresql+psycopg://cuplock:cuplock@localhost:5432/cuplock"

    # Signing secrets. Must be overridden in prod (checked at startup).
    jwt_secret: str = "dev-only-change-me"
    otp_secret: str = "dev-only-otp-pepper"

    access_token_minutes: int = 15
    refresh_token_days: int = 7

    # OTP rules (client deck, slide 8)
    otp_ttl_seconds: int = 300
    otp_max_attempts: int = 3
    otp_max_per_window: int = 5
    otp_window_minutes: int = 15
    otp_delivery: str = "console"  # console (dev only) | email | sms

    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:8100", "capacitor://localhost", "http://localhost"]

    # Company (GST: same state -> CGST+SGST, else IGST)
    company_name: str = "CUPLOCK 360 Rentals"
    company_gstin: str = ""
    company_state_code: str = "33"
    gst_rate: str = "18"  # percent, SAC 997319 rental of machinery/equipment

    # Bootstrap owner account created by `python -m app.seed`
    owner_username: str = "owner"
    owner_password: str = "Owner@12345"
    owner_phone: str = "9000000000"
    owner_email: str = "owner@example.com"

    @property
    def is_prod(self) -> bool:
        return self.env == "prod"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_prod:
        if s.jwt_secret.startswith("dev-") or s.otp_secret.startswith("dev-"):
            raise RuntimeError("Set CUPLOCK_JWT_SECRET and CUPLOCK_OTP_SECRET in production")
        if s.otp_delivery == "console":
            raise RuntimeError("Console OTP delivery is not allowed in production")
    return s
