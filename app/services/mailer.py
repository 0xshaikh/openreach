"""Email delivery for OpenReach.

If SMTP_HOST / SMTP_PORT / SMTP_USER / SMTP_PASSWORD are configured, mail is
actually sent via smtplib (stdlib). Otherwise messages are spooled to the
``emails`` outbox table with status ``Sent`` so everything works with zero
external services and every message is retained and inspectable.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

from .. import db

FROM_ADDRESS = os.environ.get("SMTP_FROM", "openreach@localhost")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


def _smtp_send(to_email: str, subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["From"] = FROM_ADDRESS
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
        if SMTP_USER:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
        server.send_message(msg)


def send_email(
    to_email: str,
    subject: str,
    body: str,
    contact_id: int | None = None,
    campaign_id: int | None = None,
    record: bool = True,
) -> dict:
    """Send (or spool) a message and return the outbox row."""
    try:
        if SMTP_HOST:
            _smtp_send(to_email, subject, body)
            status = "Sent"
            error = None
        else:
            status = "Sent"
            error = None
    except Exception as exc:  # noqa: BLE001 - keep the app alive on mail failure
        status = "Failed"
        error = str(exc)

    email_id = db.execute(
        """INSERT INTO emails (to_email, subject, body, contact_id, campaign_id, status)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (to_email, subject, body, contact_id, campaign_id, status),
    )
    row = db.query_one("SELECT * FROM emails WHERE id = ?", (email_id,))
    if error:
        row["error"] = error
    return row
