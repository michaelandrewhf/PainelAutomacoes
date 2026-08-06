import pandas as pd
from pandas import DataFrame

REQUIRED_COLUMNS = [
    "SERVICO",
    "AGENDAMENTO",
    "CTDTDATAAGENDA",
    "CTNOMESLOT",
    "LOCALIDADE",
    "PROTOCOLO",
    "CTDTSOLICITACAO",
    "CLIENTE",
    "ENDERECO",
    "BAIRRO",
]

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

SOURCE_BY_DESTINATION = {
    destination: source for source, destination in COLUMN_MAPPING.items()
}

VALUE_MAPPING = {
    "IMPLANTACAO EM NOVO ENDERECO DADOS": "MUDANÇA",
    "IMPLANTACAO DADOS": "INSTALAÇÃO",
    "IMPLANTACAO VOZ": "TELEFONIA",
    "IMPLANTACAO SUPER WIFI": "CASA ON",
    "PAULINIA": "PAULÍNIA",
    "COSMOPOLIS": "COSMÓPOLIS",
    "NÃO AGENDADO": "AGENDAR",
}


def sanitize_value(value):
    if pd.isna(value):
        return ""

    if isinstance(value, pd.Timestamp):
        return value.strftime("%d/%m/%Y")

    value = str(value).strip()
    return VALUE_MAPPING.get(value, value)


def normalize_protocol(protocol) -> str:
    if pd.isna(protocol):
        return ""

    protocol = str(protocol).strip()
    if not protocol:
        return ""

    return protocol if protocol.startswith("00") else f"00{protocol}"


def build_row(row, headers):
    result = []

    for header in headers:
        source = SOURCE_BY_DESTINATION.get(header)

        if source is None:
            result.append("")
            continue

        value = sanitize_value(row[source])

        if header == "OS":
            value = normalize_protocol(value)

        result.append(value)

    return result


def compare_to_update(
    dataframe: DataFrame,
    existing_protocols: set[str],
    headers: list[str],
) -> list[list]:
    rows = []

    for _, row in dataframe.iterrows():
        protocol = normalize_protocol(row["PROTOCOLO"])

        if not protocol or protocol in existing_protocols:
            continue

        rows.append(build_row(row, headers))
        existing_protocols.add(protocol)

    return rows
