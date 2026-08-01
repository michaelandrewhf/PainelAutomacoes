import pandas as pd
from pandas import DataFrame


COLUMN_MAPPING = {
    "SERVICO": "TIPO OS",
    "AGENDAMENTO": "STATUS",
    "CTDTDATAAGENDA": "INSTALADO",
    "CTNOMESLOT": "OBSERVAÇÃO",
    "LOCALIDADE": "CIDADE",
    "PROTOCOLO": "OS",
    "CTDTSOLICITACAO": "ABERTO EM",
    "CLIENTE": "NOME",
    "ENDERECO": "ENDEREÇO",
    "BAIRRO": "BAIRRO",
}

SERVICE_MAPPING = {
    "IMPLANTACAO EM NOVO ENDERECO DADOS": "MUDANÇA",
    "IMPLANTACAO DADOS": "INSTALAÇÃO",
    "IMPLANTACAO VOZ": "TELEFONIA",
    "IMPLANTACAO SUPER WIFI": "CASA ON",
}

CITY_MAPPING = {
    "PAULINIA": "PAULÍNIA",
    "COSMOPOLIS": "COSMÓPOLIS",
}


def sanitize_value(value):
    if pd.isna(value):
        return ""

    if isinstance(value, pd.Timestamp):
        return value.strftime("%d/%m/%Y")

    value = str(value).strip()
    value = SERVICE_MAPPING.get(value, value)
    value = CITY_MAPPING.get(value, value)

    if value == "NÃO AGENDADO":
        return "AGENDAR"

    return value


def normalize_protocol(protocol) -> str:
    if pd.isna(protocol):
        return ""

    protocol = str(protocol).strip()
    if not protocol:
        return ""

    if protocol[:2] == "00":
        return protocol

    return f"00{protocol}"


def build_row(row, headers):
    final_row = []

    for header in headers:
        value = None

        for source, destination in COLUMN_MAPPING.items():
            if destination == header:
                value = sanitize_value(row[source])
                if destination == "OS":
                    value = normalize_protocol(value)
                break

        final_row.append(value)

    return final_row


def compare_to_update(xlsx_file: DataFrame, existing_protocols: set, headers: list) -> list:
    rows_to_insert = []
    for _, row in xlsx_file.iterrows():
        protocol = normalize_protocol(str(row["PROTOCOLO"]))

        if protocol not in existing_protocols:
            rows_to_insert.append(build_row(row, headers))

    return rows_to_insert
