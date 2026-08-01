import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DEFAULT_DATABASE_PATH = DATA_DIR / "automations.db"


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def configured_path(name: str, default: str = "") -> Path:
    value = env(name, default)
    return Path(value).expanduser()


DATABASE_PATH = configured_path("DATABASE_PATH", str(DEFAULT_DATABASE_PATH))

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
