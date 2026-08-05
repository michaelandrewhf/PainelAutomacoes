import logging

import pandas as pd
from werkzeug.datastructures import FileStorage

from automations.drive.row_builder import REQUIRED_COLUMNS

logger = logging.getLogger(__name__)

ALLOWED_EXTENSION = ".xlsx"


class UploadValidationError(ValueError):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def prepare_xlsx_upload(file: FileStorage | None) -> pd.DataFrame:
    if file is None or not file.filename:
        raise UploadValidationError("Nenhum arquivo enviado.")

    if not file.filename.lower().endswith(ALLOWED_EXTENSION):
        raise UploadValidationError(
            f"Arquivo inválido. Apenas arquivos {ALLOWED_EXTENSION} são permitidos."
        )

    try:
        dataframe = pd.read_excel(file.stream)
    except Exception as exc:
        logger.exception("Erro ao ler o arquivo Excel")
        raise UploadValidationError(
            "Erro ao ler o arquivo Excel. "
            "Certifique-se de que o arquivo está no formato correto.",
            status_code=422,
        ) from exc

    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in dataframe.columns
    ]
    if missing_columns:
        raise UploadValidationError(
            f"Colunas obrigatórias ausentes: {', '.join(missing_columns)}",
            status_code=422,
        )

    empty_rows = dataframe.index[dataframe["SERVICO"].isna()]
    if not empty_rows.empty:
        dataframe = dataframe.iloc[: empty_rows[0]]

    if dataframe.empty:
        raise UploadValidationError(
            "A planilha não possui registros para processamento.",
            status_code=422,
        )

    return dataframe.loc[:, REQUIRED_COLUMNS].copy()
