from decimal import Decimal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "FinPay"
    database_url: str = "sqlite:///./finpay.db"
    secret_key: str = "dev-only-secret-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Part B decisions: currency, precision and limits
    currency: str = "INR"
    min_payment: Decimal = Decimal("0.01")
    max_payment: Decimal = Decimal("100000.00")
    max_topup: Decimal = Decimal("100000.00")

    # NFR targets (seconds) - slow requests are logged
    auth_time_limit: float = 3.0
    payment_time_limit: float = 4.0

    admin_email: str = "admin@finpay.com"
    admin_password: str = "Admin@12345"


settings = Settings()
