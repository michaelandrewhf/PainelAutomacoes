import logging
from pathlib import Path
from tempfile import TemporaryDirectory
import pandas as pd

from werkzeug.datastructures import FileStorage

from automations.drive.row_builder import REQUIRED_COLUMNS

logger = logging.getLogger(__name__)
ALLOWED_EXTENSION = ".xlsx"


class UploadValidationError(ValueError):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


def validate_file(file: FileStorage) -> bool:
    if not file.filename.endswith(ALLOWED_EXTENSION):
        raise UploadValidationError(
            f"Arquivo inválido. Apenas arquivos {ALLOWED_EXTENSION} são permitidos.",
            status_code=400,
        )

    return True

def prepare_xlsx_upload(file: FileStorage) -> Path:
    validate_file(file)
    df = pd.read_excel(file.stream)
    empty_row = df[df["SERVICO"].isna()].index
    if not empty_row.empty:
        df = df.iloc[:empty_row[0]]
    df_format = df[REQUIRED_COLUMNS]
    return df_format