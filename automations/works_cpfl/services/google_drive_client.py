from io import BytesIO
import re
from typing import Any

from config import (
    GOOGLE_DRIVE_FOLDER_ID,
    GOOGLE_DRIVE_SHARE_DOMAIN,
    GOOGLE_DRIVE_SHARE_ROLE,
    GOOGLE_DRIVE_SHARE_TYPE,
)
from automations.works_cpfl.services.google_credentials import GoogleCredentials


class GoogleDriveClient:
    def __init__(
        self,
        service: Any | None = None,
        folder_id: str = GOOGLE_DRIVE_FOLDER_ID,
        share_type: str = GOOGLE_DRIVE_SHARE_TYPE,
        share_role: str = GOOGLE_DRIVE_SHARE_ROLE,
        share_domain: str = GOOGLE_DRIVE_SHARE_DOMAIN,
    ):
        self._service = service
        self.folder_id = folder_id
        self.share_type = share_type
        self.share_role = share_role
        self.share_domain = share_domain

    def upload_pdf(self, filename: str, content: bytes, tes_number: str) -> str:
        del filename
        drive_filename = self._drive_filename(tes_number)
        existing_file = self._find_file(drive_filename)
        media = self._media_upload(content)

        if existing_file:
            file_data = self.service.files().update(
                fileId=existing_file["id"],
                media_body=media,
                fields="id, webViewLink, webContentLink",
            ).execute()
            self._sync_share(existing_file["id"])
            return self._file_url(file_data)

        metadata = {"name": drive_filename}
        if self.folder_id:
            metadata["parents"] = [self.folder_id]

        file_data = (
            self.service.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id, webViewLink, webContentLink",
            )
            .execute()
        )
        file_id = file_data["id"]
        self._share(file_id)
        return self._file_url(file_data)

    @property
    def service(self):
        if self._service is None:
            self._service = self._build_service()
        return self._service

    def _build_service(self):
        from googleapiclient.discovery import build

        credentials = GoogleCredentials().load()
        return build(
            "drive",
            "v3",
            credentials=credentials,
            cache_discovery=False,
        )

    def _media_upload(self, content: bytes):
        from googleapiclient.http import MediaIoBaseUpload

        return MediaIoBaseUpload(BytesIO(content), mimetype="application/pdf")

    def _find_file(self, filename: str) -> dict | None:
        query_parts = [
            f"name = '{self._escape_query_value(filename)}'",
            "trashed = false",
        ]
        if self.folder_id:
            query_parts.append(
                f"'{self._escape_query_value(self.folder_id)}' in parents"
            )
        response = (
            self.service.files()
            .list(
                q=" and ".join(query_parts),
                spaces="drive",
                fields="files(id, webViewLink, webContentLink)",
                pageSize=1,
            )
            .execute()
        )
        files = response.get("files", [])
        return files[0] if files else None

    def _share(self, file_id: str) -> None:
        if not self.share_type:
            return
        body = self._share_permission_body()
        (
            self.service.permissions()
            .create(
                fileId=file_id,
                body=body,
                fields="id",
            )
            .execute()
        )

    def _sync_share(self, file_id: str) -> None:
        permissions = (
            self.service.permissions()
            .list(fileId=file_id, fields="permissions(id, type, role, domain)")
            .execute()
            .get("permissions", [])
        )
        desired_permission = self._share_permission_body() if self.share_type else None

        has_desired_permission = False
        for permission in permissions:
            if self._permission_matches(permission, desired_permission):
                has_desired_permission = True
                continue
            if permission.get("type") in {"anyone", "domain"}:
                (
                    self.service.permissions()
                    .delete(fileId=file_id, permissionId=permission["id"])
                    .execute()
                )

        if desired_permission and not has_desired_permission:
            self._share(file_id)

    def _share_permission_body(self) -> dict:
        if self.share_type not in {"anyone", "domain"}:
            raise ValueError(
                "GOOGLE_DRIVE_SHARE_TYPE deve ser 'anyone', 'domain' ou vazio"
            )
        if self.share_role not in {"reader", "commenter"}:
            raise ValueError(
                "GOOGLE_DRIVE_SHARE_ROLE deve ser 'reader' ou 'commenter'"
            )

        body = {"type": self.share_type, "role": self.share_role}
        if self.share_type == "domain":
            if not self.share_domain:
                raise ValueError(
                    "Configure GOOGLE_DRIVE_SHARE_DOMAIN para compartilhar por dominio"
                )
            body["domain"] = self.share_domain
        return body

    def _permission_matches(self, permission: dict, desired_permission: dict | None) -> bool:
        if not desired_permission:
            return False
        if permission.get("type") != desired_permission["type"]:
            return False
        if permission.get("role") != desired_permission["role"]:
            return False
        if desired_permission["type"] == "domain":
            return permission.get("domain") == desired_permission["domain"]
        return True

    def _drive_filename(self, tes_number: str) -> str:
        safe_tes_number = re.sub(r"[^A-Za-z0-9_-]", "_", tes_number).strip("_")
        return f"TES-{safe_tes_number or 'documento'}.pdf"

    def _file_url(self, file_data: dict) -> str:
        return (
            file_data.get("webViewLink")
            or file_data.get("webContentLink")
            or self._download_url(file_data["id"])
        )

    def _escape_query_value(self, value: str) -> str:
        return value.replace("\\", "\\\\").replace("'", "\\'")

    def _download_url(self, file_id: str) -> str:
        return f"https://drive.google.com/uc?export=download&id={file_id}"
