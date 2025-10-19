import os
from dotenv import load_dotenv

load_dotenv()

# Database
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Anthropic API
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# App Settings
APP_HOST = os.getenv("HOST", "0.0.0.0")
APP_PORT = int(os.getenv("PORT", 8000))
DEBUG = os.getenv("DEBUG", "False").lower() == "true"

# Organization
ORG_NAME = "Халык банк"
ORG_LOGO = "/static/images/halyk_logo.png"
ORG_PRIMARY_COLOR = "#1DB584"

RECAPTCHA_SECRET_KEY = "6Lf-r-8rAAAAAI_2AAYKfUjF2uRqLzgljIaoEYYM"