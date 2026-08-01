from pathlib import Path

import pandas as pd

from automation_errors import PublicAutomationError
from config import MAX_SPREADSHEET_ROWS
from upload_service import UploadValidationError, validate_xlsx_file


from .spreadsheet_schema import REQUIRED_COLUMNS


def read_backlog_spreadsheet(input_file: Path) -> pd.DataFrame:
    try:
        validate_xlsx_file(input_file)
        dataframe = pd.read_excel(
            input_file,
            nrows=MAX_SPREADSHEET_ROWS,
            usecols=lambda column: str(column).strip() in REQUIRED_COLUMNS,
        )
    except UploadValidationError as exc:
        raise PublicAutomationError(str(exc)) from exc
    except Exception as exc:
        raise PublicAutomationError("O arquivo enviado não é uma planilha .xlsx válida.") from exc

    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in dataframe.columns
    ]
    if missing_columns:
        raise PublicAutomationError("A planilha não contém as colunas obrigatórias.")

    empty_row = dataframe[dataframe["SERVICO"].isna()].index
    if not empty_row.empty:
        dataframe = dataframe.iloc[: empty_row[0]]

    dataframe = dataframe[REQUIRED_COLUMNS]
    if dataframe.empty:
        raise PublicAutomationError("A planilha não possui registros para processamento.")

    return dataframe
