from datetime import datetime
import logging
import re


logger = logging.getLogger(__name__)


class CPFLWork(dict):
    @property
    def tes_number(self) -> str:
        document = str(self.get("Documento", "")).strip()
        match = re.search(r"\d+", document)
        return match.group(0) if match else document

    @property
    def pdf_url(self) -> str:
        return str(self.get("PDF", ""))

    @pdf_url.setter
    def pdf_url(self, value: str) -> None:
        self["PDF"] = value


def format_date(date: datetime) -> str:
    return date.strftime("%d/%m/%Y")


def parse_works_response(responses: list[dict]) -> list[CPFLWork] | None:
    works: list[CPFLWork] = []
    for response in responses:
        response = response.get("Data") or None
        if response:
            city = response[0].get("NomeMunicipio", "")
            datas = response[0].get("Datas") or None
            if datas:
                for data in datas:
                    date = data["Data"]
                    date_formated = ""
                    if "T" in date:
                        date = str(date).split("T")[0].split("-")
                    try:
                        date_formated = format_date(
                            datetime(
                                year=int(date[0]),
                                month=int(date[1]),
                                day=int(date[2]),
                            )
                        )
                    except Exception:
                        logger.exception("Erro ao formatar data")
                    documents = data.get("Documentos") or None
                    if documents:
                        for indice in range(0, len(documents)):
                            tes_document = documents[indice].get(
                                "DescricaoDocumento", ""
                            )
                            status = documents[indice].get("Estado", "")
                            bairros = documents[indice].get("Bairros") or []
                            bairros = bairros[0] if bairros else {}
                            bairro = bairros.get("NomeBairro") if bairros else ""
                            ruas = bairros.get("Ruas") or []
                            rua = ruas[0] if ruas else {}
                            rua = rua.get("NomeRua") or ""
                            hora_inicial = (
                                documents[indice].get("PeriodoExecucaoInicial")
                                or ""
                            )
                            if hora_inicial.strip():
                                if "T" in hora_inicial:
                                    hora_inicial = hora_inicial.split("T")[1]
                            hora_final = (
                                documents[indice].get("PeriodoExecucaoPeriodoFinal")
                                or ""
                            )
                            if hora_final.strip():
                                if "T" in hora_final:
                                    hora_final = hora_final.split("T")[1]
                            works.append(
                                CPFLWork(
                                    {
                                        "Cidade": city,
                                        "Data": date_formated,
                                        "Documento": tes_document,
                                        "Status": status,
                                        "Horario de início": hora_inicial,
                                        "Horario do final": hora_final,
                                        "Bairro": bairro,
                                        "Rua": rua,
                                    }
                                )
                            )
    return works if works else []


def complete_response(responses: list) -> list[CPFLWork]:
    return parse_works_response(responses=responses) or []


def format_response(
    list_works: list[CPFLWork], start_date: datetime, end_date: datetime
) -> str:
    messages = []
    for work in list_works:
        message: str = ""
        for key, value in work.items():
            message += f"{key}: {value}\n"
        messages.append(message)

    final_msg: str = (
        f"*OBRAS CPFL {format_date(start_date)} - {format_date(end_date)}* \n"
        + "-" * 60
        + "\n"
    )
    for msg in messages:
        final_msg += f"{msg}" + "-" * 60 + "\n"

    return final_msg
