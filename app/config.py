import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production-please")
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./collabhub.db")
GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
MAX_FILE_SIZE: int = int(os.getenv("MAX_FILE_SIZE", "10485760"))  # 10MB

ALGORITHM: str = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
