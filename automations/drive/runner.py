import logging
from pandas import DataFrame
from automation_errors import PublicAutomationError
from config import DRIVE_UPDATE_SHEET_NAME, DRIVE_UPDATE_WORKSHEET_NAME

from .row_builder import compare_to_update
from .sheets_client import GoogleSheetsClient

logger = logging.getLogger(__name__)


def run(input_file: DataFrame) -> None:
    logger.info("Iniciando automação Atualização do Drive")

    if not DRIVE_UPDATE_SHEET_NAME:
        raise PublicAutomationError(
            "Variável de ambiente DRIVE_UPDATE_SHEET_NAME não configurada."
        )
    if not DRIVE_UPDATE_WORKSHEET_NAME:
        raise PublicAutomationError(
            "Variável de ambiente DRIVE_UPDATE_WORKSHEET_NAME não configurada."
        )

    dataframe = input_file
    logger.info("Registros lidos da planilha enviada: %s", len(dataframe))

    sheets_client = GoogleSheetsClient(DRIVE_UPDATE_SHEET_NAME)
    existing_protocols = sheets_client.get_existing_protocols(
        DRIVE_UPDATE_WORKSHEET_NAME
    )
    logger.info("Protocolos existentes consultados: %s", len(existing_protocols))

    headers = sheets_client.get_headers(DRIVE_UPDATE_WORKSHEET_NAME)
    rows_to_insert = compare_to_update(dataframe, existing_protocols, headers)

    if rows_to_insert:
        # sheets_client.append_rows(DRIVE_UPDATE_WORKSHEET_NAME, rows_to_insert)
        logger.info("Registros adicionados com sucesso: %s", len(rows_to_insert))
    else:
        logger.info("Nenhum novo registro para adicionar")

    logger.info("Automação Atualização do Drive concluída")
