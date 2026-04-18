from __future__ import annotations

import base64
from datetime import datetime, timedelta
from email import message_from_bytes
from email.message import Message
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.core.config import settings


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class GmailService:
    def __init__(self):
        self.credentials_path = Path(settings.gmail_credentials_path)
        self.token_path = Path(settings.gmail_token_path)

    def _get_credentials(self) -> Credentials:
        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
                creds = flow.run_local_server(port=0)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def fetch_recent_messages(self, days: int = 90, limit: int = 20) -> list[dict[str, Any]]:
        creds = self._get_credentials()
        service = build("gmail", "v1", credentials=creds)
        since = (datetime.utcnow() - timedelta(days=days)).strftime("%Y/%m/%d")
        query = f"after:{since}"
        results = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=limit)
            .execute()
            .get("messages", [])
        )

        messages: list[dict[str, Any]] = []
        for msg in results:
            raw = (
                service.users()
                .messages()
                .get(userId="me", id=msg["id"], format="raw")
                .execute()
                .get("raw")
            )
            if not raw:
                continue
            payload = base64.urlsafe_b64decode(raw.encode("UTF-8"))
            parsed = message_from_bytes(payload)
            body = self._extract_text(parsed)
            messages.append({"id": msg["id"], "subject": parsed.get("subject", ""), "body": body})
        return messages

    @staticmethod
    def _extract_text(message: Message) -> str:
        plain_parts: list[str] = []
        html_parts: list[str] = []

        for part in message.walk():
            content_type = part.get_content_type()
            content_disposition = part.get("Content-Disposition", "")
            if "attachment" in content_disposition.lower():
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            text = payload.decode(charset, errors="ignore")
            if content_type == "text/plain":
                plain_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(text)

        if plain_parts:
            return "\n".join(plain_parts).strip()

        if html_parts:
            merged_html = "\n".join(html_parts)
            soup = BeautifulSoup(merged_html, "html.parser")
            return soup.get_text(separator=" ", strip=True)

        return ""
