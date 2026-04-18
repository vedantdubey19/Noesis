from typing import Any
from typing import Optional

import requests

from app.core.config import settings


class NotionService:
    base_url = "https://api.notion.com/v1"
    version = "2022-06-28"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.notion_api_key

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Notion-Version": self.version,
            "Content-Type": "application/json",
        }

    def search_pages(self, limit: int = 5) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        payload = {"page_size": limit, "filter": {"value": "page", "property": "object"}}
        response = requests.post(
            f"{self.base_url}/search", headers=self.headers, json=payload, timeout=20
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def search_databases(self, limit: int = 5) -> list[dict[str, Any]]:
        if not self.api_key:
            return []
        payload = {"page_size": limit, "filter": {"value": "database", "property": "object"}}
        response = requests.post(
            f"{self.base_url}/search", headers=self.headers, json=payload, timeout=20
        )
        response.raise_for_status()
        return response.json().get("results", [])

    def get_page_blocks(self, page_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if not self.api_key or not page_id:
            return []
        response = requests.get(
            f"{self.base_url}/blocks/{page_id}/children",
            headers=self.headers,
            params={"page_size": limit},
            timeout=20,
        )
        response.raise_for_status()
        return response.json().get("results", [])
