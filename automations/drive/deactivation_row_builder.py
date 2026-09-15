import logging
import unicodedata

from pandas import DataFrame

from .row_builder import normalize_protocol, sanitize_value

logger = logging.getLogger(__name__)

DESTINATION_HEADERS = [
    "STATUS",
    "OS",
    "CLIENTE",
    "CPF",
    "ENDERECO",
    "BAIRRO",
    "DATA DE ABERTURA",
    "DATA DE RETIRADA",
    "TECNICO",
    "OBSERVACOES",
]

SOURCE_CANDIDATES = {
    "STATUS": ("AGENDAMENTO", "STATUS"),
    "OS": ("PROTOCOLO", "OS"),
    "CLIENTE": ("CLIENTE", "NOME"),
    "CPF": ("CPF", "CPF/CNPJ", "CPFCNPJ", "DOCUMENTO"),
    "ENDERECO": ("ENDERECO", "ENDEREÇO"),
    "BAIRRO": ("BAIRRO",),
    "DATA DE ABERTURA": (
        "CTDTSOLICITACAO",
        "DATA DE ABERTURA",
        "ABERTO EM",
    ),
    "DATA DE RETIRADA": (
        "CTDTDATAAGENDA",
        "DATA DE RETIRADA",
        "DATA RETIRADA",
    ),
    "TECNICO": (
        "TECNICO",
        "TÉCNICO",
        "CTNOMETECNICO",
        "CTNOMETECNICOEXECUTOR",
        "TECNICO EXECUTOR",
    ),
    "OBSERVACOES": (
        "OBSERVACOES",
        "OBSERVAÇÕES",
        "OBSERVACAO",
        "OBSERVAÇÃO",
        "CTNOMESLOT",
    ),
}


def normalize_label(value) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    without_accents = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return " ".join(
        without_accents.replace("_", " ").strip().upper().split()
    )


def is_deactivation(service) -> bool:
    return normalize_label(service).startswith("DESATIVACAO")


def _source_lookup(dataframe: DataFrame) -> dict[str, str]:
    return {
        normalize_label(column): column
        for column in dataframe.columns
        if normalize_label(column)
    }


def resolve_source_columns(dataframe: DataFrame) -> dict[str, str | None]:
    lookup = _source_lookup(dataframe)
    resolved = {}

    for destination, candidates in SOURCE_CANDIDATES.items():
        source = next(
            (
                lookup.get(normalize_label(candidate))
                for candidate in candidates
                if lookup.get(normalize_label(candidate)) is not None
            ),
            None,
        )
        resolved[destination] = source

        if source is None:
            logger.warning(
                'Nenhuma coluna de origem encontrada para "%s"; '
                "o campo será gravado vazio.",
                destination,
            )

    return resolved


def validate_destination_headers(headers: list[str]) -> None:
    normalized_headers = {normalize_label(header) for header in headers}
    missing = [
        header
        for header in DESTINATION_HEADERS
        if normalize_label(header) not in normalized_headers
    ]

    if missing:
        raise RuntimeError(
            "Colunas obrigatórias ausentes na planilha de desativações: "
            + ", ".join(missing)
        )


def find_destination_column(headers: list[str], target: str) -> int:
    normalized_target = normalize_label(target)

    for index, header in enumerate(headers, start=1):
        if normalize_label(header) == normalized_target:
            return index

    raise RuntimeError(
        f'Coluna "{target}" não encontrada na planilha de desativações.'
    )


def build_row(
    row,
    headers: list[str],
    source_columns: dict[str, str | None],
) -> list:
    result = []

    for header in headers:
        destination = normalize_label(header)
        source = source_columns.get(destination)

        if source is None:
            result.append("")
            continue

        value = sanitize_value(row[source])

        if destination == "OS":
            value = normalize_protocol(value)

        result.append(value)

    return result


def compare_deactivations_to_update(
    dataframe: DataFrame,
    existing_protocols: set[str],
    headers: list[str],
) -> list[list]:
    source_columns = resolve_source_columns(dataframe)
    rows = []

    for _, row in dataframe.iterrows():
        service = row.get("SERVICO", "")

        if not is_deactivation(service):
            logger.info(
                'OS %s ignorada: serviço "%s" não é desativação.',
                normalize_protocol(row.get("PROTOCOLO", "")) or "sem protocolo",
                sanitize_value(service) or "vazio",
            )
            continue

        protocol = normalize_protocol(row.get("PROTOCOLO", ""))

        if not protocol:
            logger.info("Registro de desativação ignorado: protocolo vazio.")
            continue

        if protocol in existing_protocols:
            logger.info("OS %s ignorada: já existe na planilha.", protocol)
            continue

        rows.append(build_row(row, headers, source_columns))
        existing_protocols.add(protocol)

    return rows
