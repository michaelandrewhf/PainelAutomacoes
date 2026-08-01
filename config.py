import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DATABASE_PATH = DATA_DIR / "automations.db"
DEFAULT_UPLOAD_TEMP_DIR = DATA_DIR / "uploads"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def raw_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def bool_env(name: str, default: str = "false") -> bool:
    return env(name, default).casefold() in {"1", "true", "yes", "on"}


def configured_path(name: str, default: str = "") -> Path:
    value = env(name, default)
    return Path(value).expanduser()


DATABASE_PATH = configured_path("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))
UPLOAD_TEMP_DIR = configured_path("UPLOAD_TEMP_DIR", str(DEFAULT_UPLOAD_TEMP_DIR))
AUTH_USER = env("USER_APP")
AUTH_PASSWORD = raw_env("PASSWORD")
SECRET_KEY = env("SECRET_KEY")
SESSION_COOKIE_SECURE = bool_env("SESSION_COOKIE_SECURE", "false")
SESSION_LIFETIME_HOURS = int(env("SESSION_LIFETIME_HOURS", "12"))
TRUST_PROXY = bool_env("TRUST_PROXY", "false")
LOGIN_RATE_LIMIT_ATTEMPTS = int(env("LOGIN_RATE_LIMIT_ATTEMPTS", "5"))
LOGIN_RATE_LIMIT_WINDOW_SECONDS = int(env("LOGIN_RATE_LIMIT_WINDOW_SECONDS", "900"))
LOGIN_RATE_LIMIT_BLOCK_SECONDS = int(env("LOGIN_RATE_LIMIT_BLOCK_SECONDS", "900"))
MAX_UPLOAD_SIZE_MB = int(env("MAX_UPLOAD_SIZE_MB", "20"))
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
MAX_XLSX_UNCOMPRESSED_SIZE_MB = int(env("MAX_XLSX_UNCOMPRESSED_SIZE_MB", "100"))
MAX_XLSX_UNCOMPRESSED_SIZE_BYTES = MAX_XLSX_UNCOMPRESSED_SIZE_MB * 1024 * 1024
MAX_SPREADSHEET_ROWS = int(env("MAX_SPREADSHEET_ROWS", "5000"))
MAX_SPREADSHEET_COLUMNS = int(env("MAX_SPREADSHEET_COLUMNS", "100"))
MAX_SPREADSHEET_CELLS = int(env("MAX_SPREADSHEET_CELLS", "100000"))

CPFL_API_URL = env(
    "CPFL_API_URL",
    "https://spir.cpfl.com.br/api/ConsultaDesligamentoProgramado/Pesquisar?",
)
CPFL_CITY_IDS = {
    "Cosmopolis": 59,
    "Paulinia": 116,
}

SEND_NUMBERS = env("SEND_NUMBERS")

EVO_API_KEY = env("EVO_API_KEY")
EVO_URL = env("EVO_URL")
INSTANCE = env("INSTANCE")

GMAIL_USER_ID = env("GMAIL_USER_ID", "me")
GMAIL_SENDER = env("GMAIL_SENDER")
GMAIL_LABEL = env("GMAIL_LABEL")
GMAIL_QUERY = env("GMAIL_QUERY")
GMAIL_MAX_RESULTS = env("GMAIL_MAX_RESULTS", "10")

GOOGLE_CREDENTIALS_FILE = env("GOOGLE_CREDENTIALS_FILE")
GOOGLE_TOKEN_FILE = env("GOOGLE_TOKEN_FILE")
GOOGLE_DRIVE_FOLDER_ID = env("GOOGLE_DRIVE_FOLDER_ID")
GOOGLE_DRIVE_SHARE_TYPE = env("GOOGLE_DRIVE_SHARE_TYPE")
GOOGLE_DRIVE_SHARE_ROLE = env("GOOGLE_DRIVE_SHARE_ROLE", "reader")
GOOGLE_DRIVE_SHARE_DOMAIN = env("GOOGLE_DRIVE_SHARE_DOMAIN")

DRIVE_UPDATE_GOOGLE_CREDENTIALS_FILE = env("DRIVE_UPDATE_GOOGLE_CREDENTIALS_FILE")
DRIVE_UPDATE_SHEET_NAME = env("DRIVE_UPDATE_SHEET_NAME")
DRIVE_UPDATE_WORKSHEET_NAME = env("DRIVE_UPDATE_WORKSHEET_NAME")
