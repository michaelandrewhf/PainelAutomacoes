from datetime import datetime, timedelta
import logging

import requests

from automation_errors import PublicAutomationError
from config import CPFL_API_URL, CPFL_CITY_IDS

from automations.works_cpfl.utils.parse_workes_response import (
    CPFLWork,
    complete_response,
    format_response,
)


logger = logging.getLogger(__name__)


class CPFLWorksClient:

    def __init__(self):
        self.__start_date: datetime = datetime.now().date()
        self.__end_date: datetime = self.__start_date + timedelta(days=7)
        self.__url = CPFL_API_URL
        self.__city: dict = CPFL_CITY_IDS

    def search_works(self) -> list[CPFLWork]:
        responses: list = []
        for key, value in self.__city.items():
            try:
                response = requests.get(
                    url=self.__url,
                    params={
                        "PeriodoDesligamentoInicial": self.__start_date,
                        "PeriodoDesligamentoFinal": self.__end_date,
                        "IdMunicipio": value,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                responses.append(response.json())
                logger.info("Consulta CPFL concluída para %s", key)
            except requests.RequestException as exc:
                raise PublicAutomationError(
                    f"Falha ao consultar obras da CPFL para {key}."
                ) from exc
        return complete_response(responses)

    def works_week(self) -> list[CPFLWork]:
        return self.search_works()

    def build_message(self, works: list[CPFLWork]) -> str:
        return format_response(
            list_works=works, start_date=self.__start_date, end_date=self.__end_date
        )
