import base64
import binascii
from dataclasses import dataclass
import logging
import re
from typing import Any

from config import (
    GMAIL_MAX_RESULTS,
    GMAIL_LABEL,
    GMAIL_QUERY,
    GMAIL_SENDER,
    GMAIL_USER_ID,
)
from automations.works_cpfl.services.google_credentials import GoogleCredentials


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GmailPdfAttachment:
    filename: str
    content: bytes


class GmailClient:
    def __init__(
        self,
        service: Any | None = None,
        user_id: str = GMAIL_USER_ID,
        max_results: int = GMAIL_MAX_RESULTS,
        sender: str = GMAIL_SENDER,
        label: str = GMAIL_LABEL,
        base_query: str = GMAIL_QUERY,
    ):
        self._service = service
        self.user_id = user_id
        self.max_results = self._parse_max_results(max_results)
        self.sender = sender
        self.label = label
        self.base_query = base_query

    def _parse_max_results(self, value: int | str) -> int:
        try:
            return int(str(value).strip())
        except ValueError as exc:
            raise RuntimeError(
                "Variável de ambiente GMAIL_MAX_RESULTS deve ser um número inteiro."
            ) from exc

    def get_pdf_by_tes(self, tes_number: str) -> GmailPdfAttachment | None:
        tes_number = self._normalize_tes_number(tes_number)
        if not tes_number:
            logger.info("TES/TLE invalida para busca no Gmail")
            return None

        message = self._find_first_message(tes_number)
        if not message:
            logger.info("TES/TLE %s sem e-mail correspondente", tes_number)
            return None

        message_id = message["id"]
        payload = (
            self.service.users()
            .messages()
            .get(userId=self.user_id, id=message_id, format="full")
            .execute()
            .get("payload", {})
        )
        attachment = self._find_pdf_attachment(payload)
        if not attachment:
            logger.info("E-mail da TES/TLE %s sem anexo PDF", tes_number)
            return None

        return self._get_attachment(
            message_id=message_id,
            attachment_id=attachment["body"]["attachmentId"],
            filename=attachment["filename"],
        )

    @property
    def service(self):
        if self._service is None:
            self._service = self._build_service()
        return self._service

    def _build_service(self):
        from googleapiclient.discovery import build

        credentials = GoogleCredentials().load()
        return build(
            "gmail",
            "v1",
            credentials=credentials,
            cache_discovery=False,
        )

    def _build_query(self, tes_number: str) -> str:
        if not self.sender and not self.label:
            raise RuntimeError("Configure GMAIL_SENDER ou GMAIL_LABEL no .env")

        parts = [self.base_query.strip()]
        if not self._query_has("has:attachment"):
            parts.append("has:attachment")
        if not self._query_has("filename:pdf"):
            parts.append("filename:pdf")
        if self.sender:
            parts.append(f"from:{self.sender}")
        if self.label:
            parts.append(f"label:{self.label}")
        parts.append(f'"{tes_number}"')
        return " ".join(part for part in parts if part)

    def _normalize_tes_number(self, tes_number: str) -> str:
        tes_number = str(tes_number).strip()
        return tes_number if re.fullmatch(r"\d+", tes_number) else ""

    def _find_first_message(self, tes_number: str) -> dict | None:
        response = (
            self.service.users()
            .messages()
            .list(
                userId=self.user_id,
                q=self._build_query(tes_number),
                maxResults=self.max_results,
            )
            .execute()
        )
        messages = response.get("messages", [])
        return messages[0] if messages else None

    def _query_has(self, term: str) -> bool:
        return term.lower() in self.base_query.lower()

    def _find_pdf_attachment(self, payload: dict) -> dict | None:
        for part in self._walk_parts(payload):
            filename = part.get("filename", "")
            body = part.get("body", {})
            if filename.lower().endswith(".pdf") and body.get("attachmentId"):
                return part
        return None

    def _get_attachment(
        self, message_id: str, attachment_id: str, filename: str
    ) -> GmailPdfAttachment:
        response = (
            self.service.users()
            .messages()
            .attachments()
            .get(userId=self.user_id, messageId=message_id, id=attachment_id)
            .execute()
        )
        data = response.get("data", "")
        try:
            padded_data = data + "=" * (-len(data) % 4)
            content = base64.b64decode(
                padded_data.encode("utf-8"), altchars=b"-_", validate=True
            )
        except (binascii.Error, ValueError) as error:
            raise RuntimeError("Anexo PDF retornado pelo Gmail esta invalido") from error

        return GmailPdfAttachment(filename=filename, content=content)

    def _walk_parts(self, payload: dict):
        stack = [payload]
        while stack:
            part = stack.pop()
            yield part
            stack.extend(part.get("parts", []))
