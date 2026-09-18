"""
Gmail Tool — Jarvis-style email integration.

Capabilities
────────────
  • list_unread()         — fetch recent unread messages with urgency scoring
  • get_message(id)       — full message detail
  • send_email(to, subject, body)  — compose and send
  • mark_read(id)         — mark a message read
  • can_handle(message)   — Tool interface for the ToolManager
  • execute(message)      — natural-language dispatch (read / send)

Urgency levels (returned on every message)
───────────────────────────────────────────
  CRITICAL  — keywords: urgent, critical, ASAP, immediately, emergency
  HIGH      — keywords: important, deadline, action required, follow up
  NORMAL    — default
  LOW       — newsletters, no-reply, notification@

Auth
────
  OAuth 2.0 — credentials.json + token.json (see GMAIL_CREDENTIALS_PATH /
  GMAIL_TOKEN_PATH in settings).  On first run a browser window opens for
  consent.  After that the token refreshes silently.

Dependencies
────────────
  pip install google-api-python-client google-auth-oauthlib google-auth-httplib2
"""

from __future__ import annotations

import base64
import email as _email_lib
import os
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional

from packages.common import logger
from packages.config import settings

from .base import Tool


# ---------------------------------------------------------------------------
# Urgency classification
# ---------------------------------------------------------------------------

_URGENCY_CRITICAL = re.compile(
    r"\b(urgent|critical|asap|immediately|emergency|time.sensitive)\b",
    re.IGNORECASE,
)
_URGENCY_HIGH = re.compile(
    r"\b(important|deadline|action.required|follow.?up|reminder|overdue|expires?|due.today|due.tomorrow)\b",
    re.IGNORECASE,
)
_URGENCY_LOW = re.compile(
    r"(no.?reply|noreply|newsletter|unsubscribe|notification|do.not.reply|alert@|info@|digest)",
    re.IGNORECASE,
)

_SEND_PATTERN = re.compile(
    r"(?:send|email|write|compose|draft)\s+(?:an?\s+)?(?:email|mail|message)?\s*"
    r"(?:to\s+)?(?P<to>[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})",
    re.IGNORECASE,
)
_READ_PATTERN = re.compile(
    r"(?:check|read|show|list|any|what|new|unread|open).{0,30}(?:email|mail|inbox|message)",
    re.IGNORECASE,
)


def classify_urgency(sender: str, subject: str, snippet: str) -> str:
    combined = f"{sender} {subject} {snippet}"
    if _URGENCY_CRITICAL.search(combined):
        return "critical"
    if _URGENCY_HIGH.search(combined):
        return "high"
    if _URGENCY_LOW.search(sender):
        return "low"
    return "normal"


def urgency_emoji(level: str) -> str:
    return {"critical": "🚨", "high": "⚠️", "normal": "📬", "low": "📩"}.get(level, "📬")


def _decode_part_data(encoded: str) -> str:
    if not encoded:
        return ""
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("utf-8"))
        return raw.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_bodies(payload: Dict[str, Any]) -> tuple[str, str]:
    text_chunks: List[str] = []
    html_chunks: List[str] = []

    def walk(part: Dict[str, Any]) -> None:
        mime = str(part.get("mimeType") or "")
        body = dict(part.get("body") or {})
        data = _decode_part_data(str(body.get("data") or ""))

        if mime == "text/plain" and data:
            text_chunks.append(data)
        elif mime == "text/html" and data:
            html_chunks.append(data)

        for child in part.get("parts", []) or []:
            if isinstance(child, dict):
                walk(child)

    if isinstance(payload, dict):
        walk(payload)

    return ("\n\n".join(text_chunks).strip(), "\n\n".join(html_chunks).strip())


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]


def _env_flag(name: str, default: bool = False) -> bool:
    from_settings = getattr(settings, name, None)
    if isinstance(from_settings, bool):
        return from_settings
    if isinstance(from_settings, str) and from_settings.strip():
        return from_settings.strip().lower() in {"1", "true", "yes", "on"}

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_ca_bundle() -> Optional[str]:
    settings_bundle = str(getattr(settings, "GMAIL_CA_BUNDLE_PATH", "") or "").strip()
    candidates = [
        settings_bundle,
        os.getenv("GMAIL_CA_BUNDLE_PATH", "").strip(),
        os.getenv("SSL_CERT_FILE", "").strip(),
        os.getenv("REQUESTS_CA_BUNDLE", "").strip(),
    ]

    for candidate in candidates:
        if not candidate:
            continue
        expanded = Path(candidate).expanduser()
        if expanded.exists():
            return str(expanded)

    try:
        import certifi

        certifi_path = Path(certifi.where())
        if certifi_path.exists():
            return str(certifi_path)
    except Exception:
        pass

    return None


def _build_service():
    """Build and return an authenticated Gmail service object."""
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        import requests
    except ImportError as exc:
        raise RuntimeError(
            "Gmail packages missing. Run: "
            "pip install google-api-python-client google-auth-oauthlib google-auth-httplib2"
        ) from exc

    creds_path = Path(settings.GMAIL_CREDENTIALS_PATH).expanduser()
    token_path = Path(settings.GMAIL_TOKEN_PATH).expanduser()
    ca_bundle = _resolve_ca_bundle()
    insecure_ssl = _env_flag("GMAIL_INSECURE_SSL", default=False)

    if insecure_ssl:
        logger.warning("GmailTool: GMAIL_INSECURE_SSL=true, SSL verification is disabled")

    creds: Optional[Credentials] = None
    req_session = requests.Session()
    if insecure_ssl:
        req_session.verify = False
    elif ca_bundle:
        req_session.verify = ca_bundle
    req_adapter = Request(session=req_session)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(req_adapter)
        else:
            if not creds_path.exists():
                raise FileNotFoundError(
                    f"Gmail credentials not found at {creds_path}. "
                    "Download credentials.json from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), _SCOPES)
            # run_local_server() forwards kwargs to authorization_url, not fetch_token.
            # Set verify on the underlying OAuth2Session so token exchange uses it.
            if insecure_ssl:
                flow.oauth2session.verify = False
            elif ca_bundle:
                flow.oauth2session.verify = ca_bundle
            creds = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(creds.to_json())

    if insecure_ssl or ca_bundle:
        try:
            import httplib2
            import google_auth_httplib2

            http = httplib2.Http(
                ca_certs=ca_bundle if ca_bundle else None,
                disable_ssl_certificate_validation=insecure_ssl,
            )
            authed_http = google_auth_httplib2.AuthorizedHttp(creds, http=http)
            return build("gmail", "v1", http=authed_http, cache_discovery=False)
        except Exception as ex:
            logger.warning(f"GmailTool: custom HTTPS transport unavailable, using default transport: {ex}")

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


# ---------------------------------------------------------------------------
# GmailTool
# ---------------------------------------------------------------------------

class GmailTool(Tool):
    """
    Jarvis-style Gmail tool — reads, classifies, and sends email.
    """

    _service = None   # shared cached service

    def __init__(self):
        self._available: Optional[bool] = None

    # ------------------------------------------------------------------
    # Tool interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "gmail"

    def can_handle(self, message: str) -> bool:
        text = message.lower()
        return bool(
            _READ_PATTERN.search(text)
            or _SEND_PATTERN.search(text)
            or any(kw in text for kw in (
                "gmail", "inbox", "send email", "compose email",
                "email to", "mail to", "write to", "message to",
                "check mail", "any emails", "new emails",
            ))
        )

    def execute(self, message: str) -> Dict[str, Any]:
        send_match = _SEND_PATTERN.search(message)
        if send_match:
            return self._handle_send_intent(message, send_match.group("to"))
        return self._handle_read_intent(message)

    # ------------------------------------------------------------------
    # Send intent
    # ------------------------------------------------------------------

    def _handle_send_intent(self, message: str, to_address: str) -> Dict[str, Any]:
        # Extract subject and body heuristically from the utterance.
        subject_match = re.search(r"subject[:\s]+(.+?)(?:body|saying|that|$)", message, re.IGNORECASE)
        body_match = re.search(
            r"(?:body|saying|that|tell\s+(?:him|her|them))[:\s]+(.+)$", message, re.IGNORECASE
        )
        subject = subject_match.group(1).strip() if subject_match else "Message from NOVA"
        body = body_match.group(1).strip() if body_match else message

        result = self.send_email(to=to_address, subject=subject, body=body)
        if result.get("success"):
            return {
                "action": "gmail_send",
                "intent": "send_email",
                "success": True,
                "to": to_address,
                "subject": subject,
                "response": f"Done. Email sent to {to_address} with subject '{subject}'.",
            }
        return {
            "action": "gmail_send",
            "intent": "send_email",
            "success": False,
            "response": f"I couldn't send the email: {result.get('error')}",
        }

    # ------------------------------------------------------------------
    # Read intent
    # ------------------------------------------------------------------

    def _handle_read_intent(self, message: str) -> Dict[str, Any]:
        msgs = self.list_unread(max_results=settings.GMAIL_MAX_RESULTS)
        if not msgs:
            return {
                "action": "gmail_read",
                "intent": "list_unread",
                "count": 0,
                "messages": [],
                "response": "Your inbox is clear. No new messages.",
            }

        critical = [m for m in msgs if m["urgency"] == "critical"]
        high = [m for m in msgs if m["urgency"] == "high"]

        lines = [f"You have {len(msgs)} unread message{'s' if len(msgs) != 1 else ''}."]
        if critical:
            lines.append(f"🚨 {len(critical)} CRITICAL:")
            for m in critical[:3]:
                lines.append(f"  • From {m['from']}: {m['subject']}")
        if high:
            lines.append(f"⚠️  {len(high)} high priority:")
            for m in high[:3]:
                lines.append(f"  • From {m['from']}: {m['subject']}")
        if not critical and not high:
            for m in msgs[:3]:
                lines.append(f"  {urgency_emoji(m['urgency'])} From {m['from']}: {m['subject']}")

        return {
            "action": "gmail_read",
            "intent": "list_unread",
            "count": len(msgs),
            "messages": msgs,
            "critical_count": len(critical),
            "high_count": len(high),
            "response": "\n".join(lines),
        }

    # ------------------------------------------------------------------
    # Gmail API methods
    # ------------------------------------------------------------------

    def _get_service(self):
        if GmailTool._service is None:
            GmailTool._service = _build_service()
        return GmailTool._service

    def list_unread(self, max_results: int = 10, labels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        label_ids = labels or [l.strip() for l in settings.GMAIL_LABELS.split(",") if l.strip()] or ["INBOX"]
        try:
            svc = self._get_service()
            result = svc.users().messages().list(
                userId="me",
                labelIds=label_ids + ["UNREAD"],
                maxResults=max_results,
            ).execute()
            messages = result.get("messages", [])
            return [self.get_message(m["id"]) for m in messages]
        except Exception as ex:
            logger.error(f"GmailTool.list_unread failed: {ex}")
            return []

    def get_message(self, message_id: str, full: bool = False) -> Dict[str, Any]:
        try:
            svc = self._get_service()
            fmt = "full" if full else "metadata"
            raw = svc.users().messages().get(
                userId="me", id=message_id, format=fmt,
                metadataHeaders=["From", "To", "Subject", "Date"],
            ).execute()

            payload = dict(raw.get("payload", {}) or {})
            headers = {h["name"]: h["value"] for h in payload.get("headers", [])}
            sender = headers.get("From", "unknown")
            subject = headers.get("Subject", "(no subject)")
            date = headers.get("Date", "")
            snippet = raw.get("snippet", "")
            urgency = classify_urgency(sender, subject, snippet)

            body_text = ""
            body_html = ""
            if full:
                body_text, body_html = _extract_bodies(payload)

            return {
                "id": message_id,
                "from": sender,
                "to": headers.get("To", ""),
                "subject": subject,
                "date": date,
                "snippet": snippet,
                "urgency": urgency,
                "urgency_emoji": urgency_emoji(urgency),
                "thread_id": raw.get("threadId"),
                "labels": list(raw.get("labelIds", []) or []),
                "internal_date": raw.get("internalDate"),
                "size_estimate": raw.get("sizeEstimate"),
                "body_text": body_text,
                "body_html": body_html,
            }
        except Exception as ex:
            logger.error(f"GmailTool.get_message({message_id}) failed: {ex}")
            return {"id": message_id, "error": str(ex)}

    def send_email(self, to: str, subject: str, body: str, html: bool = False) -> Dict[str, Any]:
        try:
            svc = self._get_service()
            mime = MIMEMultipart("alternative")
            mime["to"] = to
            mime["subject"] = subject
            mime.attach(MIMEText(body, "html" if html else "plain"))
            raw_b64 = base64.urlsafe_b64encode(mime.as_bytes()).decode()
            svc.users().messages().send(
                userId="me", body={"raw": raw_b64}
            ).execute()
            logger.info(f"GmailTool: sent email to {to!r} subject={subject!r}")
            return {"success": True, "to": to, "subject": subject}
        except Exception as ex:
            logger.error(f"GmailTool.send_email failed: {ex}")
            return {"success": False, "error": str(ex)}

    def mark_read(self, message_id: str) -> bool:
        try:
            svc = self._get_service()
            svc.users().messages().modify(
                userId="me",
                id=message_id,
                body={"removeLabelIds": ["UNREAD"]},
            ).execute()
            return True
        except Exception as ex:
            logger.error(f"GmailTool.mark_read({message_id}) failed: {ex}")
            return False

    def is_available(self) -> bool:
        """Returns True if the Gmail service can be reached."""
        if self._available is not None:
            return self._available
        try:
            self._get_service()
            self._available = True
        except Exception:
            self._available = False
        return self._available
