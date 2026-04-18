from app.services.notion import NotionService


def test_notion_service_initializes():
    service = NotionService(api_key="test-key")
    assert service.api_key == "test-key"


def test_search_pages_without_api_key_returns_empty():
    service = NotionService(api_key="")
    assert service.search_pages(limit=5) == []


def test_search_databases_without_api_key_returns_empty():
    service = NotionService(api_key="")
    assert service.search_databases(limit=5) == []
