import unittest

import pandas as pd

from automations.drive.deactivation_row_builder import (
    compare_deactivations_to_update,
    validate_destination_headers,
)


TARGET_HEADERS = [
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


class DriveDeactivationRowBuilderTests(unittest.TestCase):
    def test_only_deactivations_are_inserted_and_other_services_are_ignored(self):
        dataframe = pd.DataFrame(
            [
                {
                    "SERVICO": "DESATIVAÇÃO",
                    "AGENDAMENTO": "NÃO AGENDADO",
                    "PROTOCOLO": "12345",
                    "CLIENTE": "Cliente A",
                    "CPF": "123.456.789-00",
                    "ENDERECO": "Rua A",
                    "BAIRRO": "Centro",
                    "CTDTSOLICITACAO": "01/09/2026",
                    "CTDTDATAAGENDA": "15/09/2026",
                    "TECNICO": "Técnico A",
                    "CTNOMESLOT": "Retirar equipamento",
                },
                {
                    "SERVICO": "IMPLANTACAO DADOS",
                    "AGENDAMENTO": "NÃO AGENDADO",
                    "PROTOCOLO": "99999",
                    "CLIENTE": "Cliente B",
                    "CPF": "999.999.999-99",
                    "ENDERECO": "Rua B",
                    "BAIRRO": "Centro",
                    "CTDTSOLICITACAO": "01/09/2026",
                    "CTDTDATAAGENDA": "15/09/2026",
                    "TECNICO": "Técnico B",
                    "CTNOMESLOT": "Não inserir",
                },
            ]
        )

        rows = compare_deactivations_to_update(
            dataframe,
            existing_protocols=set(),
            headers=TARGET_HEADERS,
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0],
            [
                "AGENDAR",
                "0012345",
                "Cliente A",
                "123.456.789-00",
                "Rua A",
                "Centro",
                "01/09/2026",
                "15/09/2026",
                "Técnico A",
                "Retirar equipamento",
            ],
        )

    def test_deactivation_variants_and_duplicate_protocol_are_supported(self):
        dataframe = pd.DataFrame(
            [
                {
                    "SERVICO": "DESATIVACAO DADOS",
                    "AGENDAMENTO": "AGENDADO",
                    "PROTOCOLO": "12345",
                    "CLIENTE": "Cliente",
                    "ENDERECO": "Rua",
                    "BAIRRO": "Centro",
                    "CTDTSOLICITACAO": "01/09/2026",
                    "CTDTDATAAGENDA": "15/09/2026",
                    "CTNOMESLOT": "Manhã",
                }
            ]
        )

        rows = compare_deactivations_to_update(
            dataframe,
            existing_protocols={"0012345"},
            headers=TARGET_HEADERS,
        )

        self.assertEqual(rows, [])

    def test_destination_headers_are_validated(self):
        with self.assertRaises(RuntimeError):
            validate_destination_headers(["STATUS", "OS", "CLIENTE"])


if __name__ == "__main__":
    unittest.main()
