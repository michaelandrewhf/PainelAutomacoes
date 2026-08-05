import logging
from time import sleep

from config import SEND_NUMBERS

from .services.cpfl_client import CPFLWorksClient
from .services.environment_validator import (
    EnvironmentValidationError,
    validate_environment,
)
from .services.evolution_client import EvolutionClient
from .services.gmail_client import GmailClient
from .services.google_drive_client import GoogleDriveClient
from .utils.parse_workes_response import CPFLWork

logger = logging.getLogger(__name__)


def attach_pdf_links_to_works(
    works: list[CPFLWork],
    gmail_client: GmailClient,
    drive_client: GoogleDriveClient,
) -> None:
    for work in works:
        tes_number = work.tes_number
        if not tes_number:
            continue

        try:
            attachment = gmail_client.get_pdf_by_tes(tes_number)
            if not attachment:
                continue

            work.pdf_url = drive_client.upload_pdf(
                filename=attachment.filename,
                content=attachment.content,
                tes_number=tes_number,
            )
            logger.info("PDF da TES/TLE %s publicado com sucesso", tes_number)
        except Exception:
            logger.exception("Erro ao processar PDF da TES/TLE %s", tes_number)


def run():
    logger.info("Iniciando automação Obras da CPFL")

    try:
        validation_config = validate_environment()
    except EnvironmentValidationError as error:
        message = error.report.render()
        logger.error("Validação de ambiente da CPFL falhou:\n%s", message)
        raise RuntimeError(
            "Configuração obrigatória da automação CPFL ausente ou inválida. "
            "Verifique os logs do container."
        ) from error

    cpfl_client = CPFLWorksClient()
    gmail_client = GmailClient()
    drive_client = GoogleDriveClient(folder_id=validation_config.google_drive_folder_id)
    evolution_client = EvolutionClient()

    works = cpfl_client.works_week()
    logger.info("Obras obtidas da CPFL: %s", len(works))

    attach_pdf_links_to_works(works, gmail_client, drive_client)
    message = cpfl_client.build_message(works)

    send_numbers = [
        number.strip() for number in str(SEND_NUMBERS).split(",") if number.strip()
    ]
    if not send_numbers:
        raise RuntimeError("Variável de ambiente SEND_NUMBERS não configurada.")

    for index, number in enumerate(send_numbers):
        response = evolution_client.notification(number, message)
        logger.info(
            "Mensagem CPFL enviada para número %s com status HTTP %s",
            index + 1,
            response.status_code,
        )
        if len(send_numbers) > 1 and index < len(send_numbers) - 1:
            sleep(6)

    logger.info("Automação Obras da CPFL concluída")


if __name__ == "__main__":
    run()
