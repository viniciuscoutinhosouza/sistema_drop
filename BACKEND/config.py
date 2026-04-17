from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Oracle ATP
    ORACLE_USER: str
    ORACLE_PASSWORD: str
    ORACLE_DSN: str                      # e.g. "(description=(address=(protocol=tcps)...)"
    ORACLE_WALLET_DIR: str = ""          # path to unzipped Oracle Cloud Wallet folder

    # JWT
    JWT_SECRET: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 480        # 8 hours
    JWT_REFRESH_EXPIRE_DAYS: int = 30

    # CORS / Frontend
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: str = "http://localhost:5173"

    # Mercado Livre
    ML_APP_ID: str = "6712718703908494"
    ML_CLIENT_SECRET: str = ""
    ML_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/ml/callback"

    # Shopee
    SHOPEE_PARTNER_ID: str = ""
    SHOPEE_PARTNER_KEY: str = ""
    SHOPEE_REDIRECT_URI: str = "http://localhost:8000/api/v1/integrations/shopee/callback"

    # Platform fee (R$) charged per order payment
    PLATFORM_FEE: float = 2.00

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
