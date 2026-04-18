from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.services.gmail import GmailService


def test_gmail_service_paths_exist_as_strings():
    service = GmailService()
    assert str(service.credentials_path)
    assert str(service.token_path)


def test_extract_text_prefers_plain_text():
    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText("plain body", "plain"))
    msg.attach(MIMEText("<p>html body</p>", "html"))

    body = GmailService._extract_text(msg)
    assert body == "plain body"


def test_extract_text_falls_back_to_html_when_plain_missing():
    msg = MIMEMultipart("alternative")
    msg.attach(MIMEText("<div>Hello <strong>World</strong></div>", "html"))

    body = GmailService._extract_text(msg)
    assert "Hello" in body
    assert "World" in body
