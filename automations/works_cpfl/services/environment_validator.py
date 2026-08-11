from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

from config import (
    EVO_API_KEY,
    EVO_URL,
    GMAIL_LABEL,
    GMAIL_MAX_RESULTS,
    GMAIL_QUERY,
    GMAIL_SENDER,
    GMAIL_USER_ID,
    GOOGLE_CREDENTIALS_FILE,
    GOOGLE_DRIVE_FOLDER_ID,
    GOOGLE_DRIVE_SHARE_DOMAIN,
    GOOGLE_DRIVE_SHARE_ROLE,
    GOOGLE_DRIVE_SHARE_TYPE,
    GOOGLE_OAUTH_INTERACTIVE,
    GOOGLE_TOKEN_FILE,
    INSTANCE,
    SEND_NUMBERS,
)
from automations.works_cpfl.services.google_credentials import GoogleCredentials


DRIVE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
PLACEHOLDER_PATTERNS = (
    re.compile(r"^COLE_AQUI", re.IGNORECASE),
    re.compile(r"^CHANGE_ME$", re.IGNORECASE),
    re.compile(r"^YOUR[_-]", re.IGNORECASE),
    re.compile(r"TODO", re.IGNORECASE),
    re.compile(r"^<.+>$"),
)
DRIVE_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass(frozen=True)
class EnvironmentValidationConfig:
    google_drive_folder_id: str


@dataclass
class EnvironmentValidationReport:
    successes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def ok(self, message: str) -> None:
        self.successes.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def fail(self, title: str, reason: str) -> None:
        self.errors.append(f"{title}\nMotivo: {reason}")

    def has_errors(self) -> bool:
        return bool(self.errors)

    def render(self) -> str:
        lines = [*[f"✓ {message}" for message in self.successes]]
        lines.extend(f"! {message}" for message in self.warnings)
        lines.extend(f"✗ {message}" for message in self.errors)
        return "\n".join(lines)


class EnvironmentValidationError(RuntimeError):
    def __init__(self, report: EnvironmentValidationReport):
        super().__init__("Environment validation failed")
        self.report = report


class EnvironmentValidator:
    required_variables = (
        "GOOGLE_CREDENTIALS_FILE",
        "GOOGLE_TOKEN_FILE",
        "GOOGLE_DRIVE_FOLDER_ID",
        "GMAIL_USER_ID",
        "GMAIL_QUERY",
        "SEND_NUMBERS",
        "EVO_API_KEY",
        "EVO_URL",
        "INSTANCE",
    )
    known_variables = (
        *required_variables,
        "GOOGLE_OAUTH_INTERACTIVE",
        "GMAIL_SENDER",
        "GMAIL_LABEL",
        "GMAIL_MAX_RESULTS",
        "GOOGLE_DRIVE_SHARE_TYPE",
        "GOOGLE_DRIVE_SHARE_ROLE",
        "GOOGLE_DRIVE_SHARE_DOMAIN",
    )

    def __init__(
        self,
        environ: Mapping[str, str] | None = None,
        credentials_loader: GoogleCredentials | None = None,
        gmail_service: Any | None = None,
        drive_service: Any | None = None,
    ):
        self.environ = self._config_environ() if environ is None else environ
        self.credentials_loader = credentials_loader
        self.gmail_service = gmail_service
        self.drive_service = drive_service
        self.report = EnvironmentValidationReport()

    def validate(self) -> EnvironmentValidationConfig:
        self._validate_required_variables()
        self._validate_placeholders()
        credentials_file = self._validate_file("GOOGLE_CREDENTIALS_FILE")
        token_file = self._validate_token_file()
        folder_id = self._validate_drive_folder_id()
        self._validate_gmail_filter()
        self._validate_gmail_max_results()
        self._validate_drive_share_config()

        if self.report.has_errors():
            raise EnvironmentValidationError(self.report)

        credentials = self._load_google_credentials(credentials_file, token_file)
        gmail_service = self._build_google_service("gmail", "v1", credentials)
        self._validate_gmail_auth(gmail_service)
        drive_service = self._build_google_service("drive", "v3", credentials)
        self._validate_drive_folder(drive_service, folder_id)

        if self.report.has_errors():
            raise EnvironmentValidationError(self.report)

        return EnvironmentValidationConfig(google_drive_folder_id=folder_id)

    def _config_environ(self) -> dict[str, str]:
        return {
            "GOOGLE_CREDENTIALS_FILE": GOOGLE_CREDENTIALS_FILE,
            "GOOGLE_TOKEN_FILE": GOOGLE_TOKEN_FILE,
            "GOOGLE_OAUTH_INTERACTIVE": GOOGLE_OAUTH_INTERACTIVE,
            "GOOGLE_DRIVE_FOLDER_ID": GOOGLE_DRIVE_FOLDER_ID,
            "GMAIL_USER_ID": GMAIL_USER_ID,
            "GMAIL_QUERY": GMAIL_QUERY,
            "GMAIL_MAX_RESULTS": GMAIL_MAX_RESULTS,
            "GMAIL_SENDER": GMAIL_SENDER,
            "GMAIL_LABEL": GMAIL_LABEL,
            "SEND_NUMBERS": SEND_NUMBERS,
            "EVO_API_KEY": EVO_API_KEY,
            "EVO_URL": EVO_URL,
            "INSTANCE": INSTANCE,
            "GOOGLE_DRIVE_SHARE_TYPE": GOOGLE_DRIVE_SHARE_TYPE,
            "GOOGLE_DRIVE_SHARE_ROLE": GOOGLE_DRIVE_SHARE_ROLE,
            "GOOGLE_DRIVE_SHARE_DOMAIN": GOOGLE_DRIVE_SHARE_DOMAIN,
        }

    def _validate_required_variables(self) -> None:
        for variable in self.required_variables:
            if not self._value(variable):
                self.report.fail(
                    f"{variable} ausente",
                    "variavel obrigatoria nao foi configurada ou esta vazia",
                )

    def _validate_placeholders(self) -> None:
        for variable in self.known_variables:
            value = self._value(variable)
            if value and self._is_placeholder(value):
                self.report.fail(
                    f"{variable} invalido",
                    "valor parece ser placeholder; substitua pelo valor real",
                )

    def _validate_file(self, variable: str) -> Path:
        path = Path(self._value(variable)).expanduser()
        if not path.exists():
            self.report.fail(variable, f"arquivo nao encontrado em {path}")
            return path
        if self._has_symlink_component(path):
            self.report.fail(
                variable,
                "caminho nao pode apontar para link simbolico",
            )
            return path
        if not path.is_file():
            self.report.fail(variable, f"caminho informado nao e um arquivo: {path}")
            return path

        label = (
            "Credentials encontradas"
            if variable == "GOOGLE_CREDENTIALS_FILE"
            else "Token encontrado"
        )
        self.report.ok(label)
        return path

    def _validate_token_file(self) -> Path:
        path = Path(self._value("GOOGLE_TOKEN_FILE")).expanduser()
        if self._has_symlink_component(path):
            self.report.fail(
                "GOOGLE_TOKEN_FILE",
                "caminho nao pode apontar para link simbolico",
            )
            return path
        if not path.exists():
            if self._oauth_interactive_enabled():
                self.report.warn(
                    "Token Google ausente; a autenticacao OAuth sera aberta no navegador"
                )
            else:
                self.report.warn(
                    "Token Google ausente; gere o token OAuth antes de executar a automacao"
                )
            return path
        if not path.is_file():
            self.report.fail(
                "GOOGLE_TOKEN_FILE",
                f"caminho informado nao e um arquivo: {path}",
            )
            return path

        self.report.ok("Token encontrado")
        return path

    def _validate_drive_folder_id(self) -> str:
        raw_folder_id = self._value("GOOGLE_DRIVE_FOLDER_ID").rstrip("/")
        folder_id, changed = sanitize_drive_folder_id(raw_folder_id)
        if changed:
            self.report.warn(
                "GOOGLE_DRIVE_FOLDER_ID continha URL ou parametros; usando apenas o ID da pasta"
            )
        if folder_id and self._is_placeholder(folder_id):
            self.report.fail(
                "GOOGLE_DRIVE_FOLDER_ID invalido",
                "valor parece ser placeholder; substitua pelo ID real da pasta",
            )
            return folder_id
        if not folder_id:
            self.report.fail(
                "GOOGLE_DRIVE_FOLDER_ID invalido",
                "informe apenas o ID da pasta do Google Drive",
            )
            return folder_id
        if not DRIVE_ID_PATTERN.fullmatch(folder_id):
            self.report.fail(
                "GOOGLE_DRIVE_FOLDER_ID invalido",
                "foi informado URL, parametros ou caracteres invalidos; use apenas o ID da pasta",
            )
        return folder_id

    def _validate_gmail_filter(self) -> None:
        if not self._value("GMAIL_SENDER") and not self._value("GMAIL_LABEL"):
            self.report.fail(
                "Filtro Gmail invalido",
                "configure GMAIL_SENDER ou GMAIL_LABEL para limitar a busca dos PDFs",
            )

    def _validate_gmail_max_results(self) -> None:
        value = self._value("GMAIL_MAX_RESULTS")
        try:
            max_results = int(value or "10")
        except ValueError:
            self.report.fail(
                "GMAIL_MAX_RESULTS invalido",
                "informe um numero inteiro",
            )
            return

        if max_results <= 0:
            self.report.fail(
                "GMAIL_MAX_RESULTS invalido",
                "informe um numero inteiro maior que zero",
            )

    def _validate_drive_share_config(self) -> None:
        share_type = self._value("GOOGLE_DRIVE_SHARE_TYPE")
        share_role = self._value("GOOGLE_DRIVE_SHARE_ROLE")
        if share_type and share_type not in {"anyone", "domain"}:
            self.report.fail(
                "GOOGLE_DRIVE_SHARE_TYPE invalido",
                "use 'anyone', 'domain' ou deixe vazio",
            )
        if share_role and share_role not in {"reader", "commenter"}:
            self.report.fail(
                "GOOGLE_DRIVE_SHARE_ROLE invalido",
                "use 'reader' ou 'commenter'",
            )
        if share_type == "domain" and not self._value("GOOGLE_DRIVE_SHARE_DOMAIN"):
            self.report.fail(
                "GOOGLE_DRIVE_SHARE_DOMAIN ausente",
                "obrigatorio quando GOOGLE_DRIVE_SHARE_TYPE=domain",
            )

    def _load_google_credentials(self, credentials_file: Path, token_file: Path):
        try:
            loader = self.credentials_loader or GoogleCredentials(
                credentials_file=str(credentials_file),
                token_file=str(token_file),
            )
            return loader.load(interactive=self._oauth_interactive_enabled())
        except Exception as error:
            self.report.fail(
                "Autenticacao Google invalida",
                self._friendly_google_error(error),
            )
            raise EnvironmentValidationError(self.report) from error

    def _build_google_service(self, service_name: str, version: str, credentials):
        if service_name == "gmail" and self.gmail_service is not None:
            return self.gmail_service
        if service_name == "drive" and self.drive_service is not None:
            return self.drive_service
        try:
            from googleapiclient.discovery import build

            return build(
                service_name,
                version,
                credentials=credentials,
                cache_discovery=False,
            )
        except Exception as error:
            self.report.fail(
                f"{service_name.capitalize()} nao autenticado",
                self._friendly_google_error(error),
            )
            raise EnvironmentValidationError(self.report) from error

    def _validate_gmail_auth(self, gmail_service: Any) -> None:
        try:
            gmail_service.users().getProfile(userId=self._value("GMAIL_USER_ID")).execute()
        except Exception as error:
            self.report.fail("Gmail nao autenticado", self._friendly_google_error(error))
            raise EnvironmentValidationError(self.report) from error
        self.report.ok("Gmail autenticado")

    def _validate_drive_folder(self, drive_service: Any, folder_id: str) -> None:
        try:
            folder = (
                drive_service.files()
                .get(
                    fileId=folder_id,
                    fields="id,name,mimeType,trashed,capabilities(canAddChildren)",
                    supportsAllDrives=True,
                )
                .execute()
            )
        except Exception as error:
            if self._google_status(error) in {403, 404}:
                if self._validate_drive_folder_by_write_probe(
                    drive_service,
                    folder_id,
                    metadata_error=error,
                ):
                    return
            self.report.fail(
                "Pasta do Drive nao encontrada",
                self._friendly_google_error(error),
            )
            raise EnvironmentValidationError(self.report) from error

        self.report.ok("Drive autenticado")
        folder_is_valid = False
        if folder.get("trashed"):
            self.report.fail("Pasta do Drive invalida", "a pasta esta na lixeira")
        elif folder.get("mimeType") != DRIVE_FOLDER_MIME_TYPE:
            self.report.fail(
                "GOOGLE_DRIVE_FOLDER_ID invalido",
                "o ID informado existe, mas nao aponta para uma pasta",
            )
        else:
            folder_is_valid = True
            self.report.ok("Pasta encontrada")

        capabilities = folder.get("capabilities", {})
        if folder_is_valid and capabilities.get("canAddChildren") is False:
            self.report.fail(
                "Permissao de escrita ausente",
                "a conta autenticada nao pode criar arquivos nessa pasta",
            )
        elif folder_is_valid:
            self.report.ok("Permissao de escrita OK")

    def _validate_drive_folder_by_write_probe(
        self,
        drive_service: Any,
        folder_id: str,
        metadata_error: Exception,
    ) -> bool:
        try:
            from googleapiclient.http import MediaIoBaseUpload

            media = MediaIoBaseUpload(
                BytesIO(b"environment validation"),
                mimetype="text/plain",
                resumable=False,
            )
            file_data = (
                drive_service.files()
                .create(
                    body={
                        "name": ".obras-cpfl-environment-validation.txt",
                        "parents": [folder_id],
                    },
                    media_body=media,
                    fields="id",
                    supportsAllDrives=True,
                )
                .execute()
            )
            file_id = file_data.get("id")
            if file_id:
                (
                    drive_service.files()
                    .delete(fileId=file_id, supportsAllDrives=True)
                    .execute()
                )
        except Exception as error:
            self.report.fail(
                "Pasta do Drive nao encontrada",
                (
                    "nao foi possivel ler os metadados da pasta nem criar arquivo "
                    f"de validacao: {self._friendly_google_error(error)}"
                ),
            )
            raise EnvironmentValidationError(self.report) from error

        self.report.ok("Drive autenticado")
        self.report.ok("Pasta encontrada")
        self.report.ok("Permissao de escrita OK")
        self.report.warn(
            "Metadados da pasta nao acessiveis com o escopo atual; validacao feita por escrita temporaria"
        )
        return True

    def _friendly_google_error(self, error: Exception) -> str:
        status = self._google_status(error)
        if status in {401, 403}:
            return "credenciais sem permissao ou token expirado/revogado"
        if status == 404:
            return "recurso nao encontrado ou sem acesso para a conta autenticada"
        message = str(error).strip()
        return message or error.__class__.__name__

    def _oauth_interactive_enabled(self) -> bool:
        value = self._value("GOOGLE_OAUTH_INTERACTIVE").lower()
        return value in {"1", "true", "yes", "sim"}

    def _google_status(self, error: Exception) -> int | None:
        return getattr(getattr(error, "resp", None), "status", None)

    def _value(self, variable: str) -> str:
        return str(self.environ.get(variable, "")).strip()

    def _is_placeholder(self, value: str) -> bool:
        return any(pattern.search(value.strip()) for pattern in PLACEHOLDER_PATTERNS)

    def _has_symlink_component(self, path: Path) -> bool:
        path = path if path.is_absolute() else Path.cwd() / path
        return any(candidate.is_symlink() for candidate in [path, *path.parents])


def sanitize_drive_folder_id(value: str) -> tuple[str, bool]:
    original = value.strip()
    sanitized = original.rstrip("/")
    parsed = urlparse(sanitized)

    if parsed.scheme and parsed.netloc:
        path_parts = [part for part in parsed.path.split("/") if part]
        if "folders" in path_parts:
            index = path_parts.index("folders")
            if len(path_parts) > index + 1:
                return path_parts[index + 1].strip().rstrip("/"), True
        query_id = parse_qs(parsed.query).get("id", [""])[0]
        if query_id:
            return query_id.strip().rstrip("/"), True
        return sanitized, False

    if "?" in sanitized:
        return sanitized.split("?", 1)[0].rstrip("/"), True

    if "/folders/" in sanitized:
        return sanitized.rsplit("/folders/", 1)[-1].split("/", 1)[0].strip(), True

    return sanitized, sanitized != original


def validate_environment() -> EnvironmentValidationConfig:
    validator = EnvironmentValidator()
    config = validator.validate()
    return config
