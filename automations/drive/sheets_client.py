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
        credentials_file: str = DRIVE_UPDATE_GOOGLE_CREDENTIALS_FILE,
    ):
        if not credentials_file:
            raise RuntimeError(
                "Variável de ambiente DRIVE_UPDATE_GOOGLE_CREDENTIALS_FILE não configurada."
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
        self._client = gspread.authorize(credentials)
        self._sheet = self._client.open(sheet_name)

    def get_existing_protocols(self, worksheet_name: str) -> set:
        worksheet = self._sheet.worksheet(worksheet_name)
        headers = worksheet.row_values(1)
        os_column_index = headers.index("OS") + 1
        column_values = worksheet.col_values(os_column_index)
        records = column_values[1:][-100:]
        return set(str(record).strip() for record in records)

    def get_headers(self, worksheet_name: str) -> list:
        worksheet = self._sheet.worksheet(worksheet_name)
        return worksheet.row_values(1)

    def append_rows(self, worksheet_name: str, rows):
        worksheet = self._sheet.worksheet(worksheet_name)
        headers = worksheet.row_values(1)
        normalized_headers = [str(header).strip().casefold() for header in headers]

        try:
            os_index = normalized_headers.index("os")
        except ValueError as exc:
            raise RuntimeError(
                f'Coluna "OS" não encontrada na aba "{worksheet_name}".'
            ) from exc

        os_values = worksheet.col_values(os_index + 1)
        start_row = len(os_values) + 1
        end_row = start_row + len(rows) - 1

        if end_row > worksheet.row_count:
            worksheet.add_rows(end_row - worksheet.row_count)

        worksheet.update(
            range_name=f"A{start_row}",
            values=rows,
            value_input_option="RAW",
        )
        logger.info("Linhas adicionadas na planilha do Drive: %s", len(rows))
