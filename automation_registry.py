from automations.drive.deactivation_runner import run as run_drive_deactivations
from automations.drive.runner import run as run_drive_update
from automations.works_cpfl.runner import run as run_cpfl_works


AUTOMATIONS = {
    "cpfl-works": {
        "name": "Obras da CPFL",
        "description": "Consulta e processa documentos relacionados às obras da CPFL.",
        "runner": run_cpfl_works,
    },
    "drive-update": {
        "name": "Atualização do Drive",
        "description": "Atualiza os arquivos e dados armazenados no Google Drive.",
        "runner": run_drive_update,
        "requires_file": True,
    },
    "drive-deactivations": {
        "name": "OS de Desativação",
        "description": (
            "Atualiza a planilha de retiradas somente com novas OS de desativação."
        ),
        "runner": run_drive_deactivations,
        "requires_file": True,
    },
}
