import logging
from pathlib import Path

import gspread
from google.oauth2.service_account import Credentials

from config import DRIVE_UPDATE_GOOGLE_CREDENTIALS_FILE

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


class GoogleSheetsClient:
    def __init__(
        self,
        sheet_name: str,
        worksheet_name: str,
        credentials_file: str = DRIVE_UPDATE_GOOGLE_CREDENTIALS_FILE,
    ):
        if not credentials_file:
            raise RuntimeError(
                "Variável DRIVE_UPDATE_GOOGLE_CREDENTIALS_FILE não configurada."
            )

        credentials_path = Path(credentials_file).expanduser()
        if not credentials_path.is_file():
            raise RuntimeError(
                "Arquivo de credenciais da automação do Drive não encontrado."
            )

        credentials = Credentials.from_service_account_file(
            credentials_path,
            scopes=SCOPES,
        )

        client = gspread.authorize(credentials)
        self.worksheet = client.open(sheet_name).worksheet(worksheet_name)

    def get_headers(self) -> list[str]:
        return self.worksheet.row_values(1)

    def get_existing_protocols(self, os_column: int) -> set[str]:
        values = self.worksheet.col_values(os_column)
        return {str(value).strip() for value in values[1:][-100:] if value}

    def append_rows(self, rows: list[list], os_column: int) -> None:
        start_row = len(self.worksheet.col_values(os_column)) + 1
        end_row = start_row + len(rows) - 1

        if end_row > self.worksheet.row_count:
            self.worksheet.add_rows(end_row - self.worksheet.row_count)

        self.worksheet.update(
            range_name=f"A{start_row}",
            values=rows,
            value_input_option="RAW",
        )

        logger.info("Linhas adicionadas na planilha do Drive: %s", len(rows))