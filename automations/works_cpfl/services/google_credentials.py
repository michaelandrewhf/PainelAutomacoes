from pathlib import Path
import os

from config import GOOGLE_CREDENTIALS_FILE, GOOGLE_TOKEN_FILE


GOOGLE_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.file",
)


class GoogleCredentials:
    def __init__(
        self,
        credentials_file: str = GOOGLE_CREDENTIALS_FILE,
        token_file: str = GOOGLE_TOKEN_FILE,
    ):
        self.credentials_file = credentials_file
        self.token_file = token_file

    def load(self):
        if not self.credentials_file:
            raise RuntimeError("Configure GOOGLE_CREDENTIALS_FILE no .env")
        if not self.token_file:
            raise RuntimeError("Configure GOOGLE_TOKEN_FILE no .env")
        self._validate_scopes()

        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow

        credentials = None
        credentials_path = Path(self.credentials_file).expanduser()
        self._reject_symlink_chain(credentials_path, "GOOGLE_CREDENTIALS_FILE")
        token_path = Path(self.token_file).expanduser()
        self._reject_symlink_chain(token_path, "GOOGLE_TOKEN_FILE")
        if token_path.exists():
            self._validate_token_permissions(token_path)
            credentials = Credentials.from_authorized_user_file(
                str(token_path), GOOGLE_SCOPES
            )

        has_scopes = credentials and credentials.has_scopes(GOOGLE_SCOPES)
        if not credentials or not credentials.valid or not has_scopes:
            if (
                credentials
                and credentials.expired
                and credentials.refresh_token
                and has_scopes
            ):
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_path), GOOGLE_SCOPES
                )
                credentials = flow.run_local_server(port=0)
            token_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_token(token_path, credentials.to_json())

        return credentials

    def _validate_scopes(self) -> None:
        for scope in GOOGLE_SCOPES:
            if not scope.startswith("https://www.googleapis.com/auth/"):
                raise RuntimeError(f"Scope Google invalido: {scope}")

    def _validate_token_permissions(self, token_path: Path) -> None:
        if token_path.stat().st_mode & 0o077:
            raise RuntimeError(
                f"Ajuste as permissoes de {token_path} para permitir acesso apenas ao usuario"
            )

    def _reject_symlink_chain(self, path: Path, variable: str) -> None:
        path = path if path.is_absolute() else Path.cwd() / path
        current = path
        checked_paths = [current]
        checked_paths.extend(current.parents)

        for candidate in checked_paths:
            try:
                if candidate.is_symlink():
                    raise RuntimeError(
                        f"{variable} nao pode apontar para link simbolico: {candidate}"
                    )
            except OSError as error:
                raise RuntimeError(
                    f"Nao foi possivel validar o caminho de {variable}: {candidate}"
                ) from error

    def _write_token(self, token_path: Path, token_json: str) -> None:
        self._reject_symlink_chain(token_path, "GOOGLE_TOKEN_FILE")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(token_path, flags, 0o600)
        except OSError as error:
            raise RuntimeError(
                f"Nao foi possivel gravar GOOGLE_TOKEN_FILE com seguranca: {token_path}"
            ) from error
        with os.fdopen(descriptor, "w", encoding="utf-8") as token_file:
            token_file.write(token_json)
        token_path.chmod(0o600)
