import logging
from pandas import DataFrame

from config import (
    DRIVE_DEACTIVATION_SHEET_NAME,
    DRIVE_DEACTIVATION_WORKSHEET_NAME,
)

from .deactivation_row_builder import (
    compare_deactivations_to_update,
    find_destination_column,
    validate_destination_headers,
)
from .sheets_client import GoogleSheetsClient

logger = logging.getLogger(__name__)


def run(input_file: DataFrame) -> None:
    logger.info("Iniciando automação de OS de desativação")

    if not DRIVE_DEACTIVATION_SHEET_NAME:
        raise RuntimeError(
            "Variável DRIVE_DEACTIVATION_SHEET_NAME não configurada."
        )

    if not DRIVE_DEACTIVATION_WORKSHEET_NAME:
        raise RuntimeError(
            "Variável DRIVE_DEACTIVATION_WORKSHEET_NAME não configurada."
        )

    logger.info("Registros lidos da planilha enviada: %s", len(input_file))

    sheets = GoogleSheetsClient(
        DRIVE_DEACTIVATION_SHEET_NAME,
        DRIVE_DEACTIVATION_WORKSHEET_NAME,
    )

    headers = sheets.get_headers()
    validate_destination_headers(headers)

    os_column = find_destination_column(headers, "OS")
    existing_protocols = sheets.get_existing_protocols(os_column)

    logger.info(
        "Últimos protocolos consultados na planilha de desativações: %s",
        len(existing_protocols),
    )

    rows_to_insert = compare_deactivations_to_update(
        input_file,
        existing_protocols,
        headers,
    )

    if rows_to_insert:
        sheets.append_rows_raw(rows_to_insert, os_column)
        logger.info(
            "OS de desativação adicionadas com sucesso: %s",
            len(rows_to_insert),
        )
    else:
        logger.info("Nenhuma nova OS de desativação para adicionar")

    logger.info("Automação de OS de desativação concluída")
