import logging
from pandas import DataFrame
from config import DRIVE_UPDATE_SHEET_NAME, DRIVE_UPDATE_WORKSHEET_NAME

from .row_builder import compare_to_update
from .sheets_client import GoogleSheetsClient

logger = logging.getLogger(__name__)


def run(input_file: DataFrame) -> None:
    logger.info("Iniciando automação Atualização do Drive")

    if not DRIVE_UPDATE_SHEET_NAME:
        raise RuntimeError("Variável DRIVE_UPDATE_SHEET_NAME não configurada.")

    if not DRIVE_UPDATE_WORKSHEET_NAME:
        raise RuntimeError("Variável DRIVE_UPDATE_WORKSHEET_NAME não configurada.")

    logger.info("Registros lidos da planilha enviada: %s", len(input_file))

    sheets = GoogleSheetsClient(
        DRIVE_UPDATE_SHEET_NAME,
        DRIVE_UPDATE_WORKSHEET_NAME,
    )

    headers = sheets.get_headers()

    try:
        os_column = headers.index("OS") + 1
    except ValueError as exc:
        raise RuntimeError(
            f'Coluna "OS" não encontrada na aba "{DRIVE_UPDATE_WORKSHEET_NAME}".'
        ) from exc

    existing_protocols = sheets.get_existing_protocols(os_column)
    logger.info(
        "Protocolos existentes consultados: %s",
        len(existing_protocols),
    )

    rows_to_insert = compare_to_update(
        input_file,
        existing_protocols,
        headers,
    )

    if rows_to_insert:
        sheets.append_rows(rows_to_insert, os_column)
        logger.info(
            "Registros adicionados com sucesso: %s",
            len(rows_to_insert),
        )
    else:
        logger.info("Nenhum novo registro para adicionar")

    logger.info("Automação Atualização do Drive concluída")
