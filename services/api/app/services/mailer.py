"""SMTP mail transport.

Delivery is attempted for real through ``smtplib`` (run in a thread so the event
loop is never blocked). With no ``SMTP_HOST`` configured, sending reports the
failure instead of pretending the message went out.
"""

from __future__ import annotations

import asyncio
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Optional


def _settings() -> dict:
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "1025")),
        "username": os.getenv("SMTP_USERNAME", "").strip(),
        "password": os.getenv("SMTP_PASSWORD", ""),
        "sender": os.getenv("SMTP_FROM", "no-reply@advisorytrail.local").strip(),
        "sender_name": os.getenv("SMTP_FROM_NAME", "AdvisoryTrail").strip(),
        "mode": os.getenv("SMTP_SECURITY", "none").strip().lower(),  # none | starttls | ssl
        "timeout": float(os.getenv("SMTP_TIMEOUT", "10")),
    }


def transport_status() -> dict:
    config = _settings()
    return {
        "configured": bool(config["host"]),
        "host": config["host"] or None,
        "port": config["port"],
        "from_address": config["sender"],
        "security": config["mode"],
    }


def _send_sync(to: str, subject: str, body: str, config: dict) -> None:
    message = EmailMessage()
    message["From"] = formataddr((config["sender_name"], config["sender"]))
    message["To"] = to
    message["Subject"] = subject
    message["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    message["Message-ID"] = make_msgid(domain="advisorytrail.local")
    message.set_content(body)

    if config["mode"] == "ssl":
        client = smtplib.SMTP_SSL(config["host"], config["port"], timeout=config["timeout"], context=ssl.create_default_context())
    else:
        client = smtplib.SMTP(config["host"], config["port"], timeout=config["timeout"])

    with client:
        if config["mode"] == "starttls":
            client.starttls(context=ssl.create_default_context())
        if config["username"]:
            client.login(config["username"], config["password"])
        client.send_message(message)


async def send_email(to: str, subject: str, body: str) -> dict:
    """Returns ``{"delivered": bool, "detail": str}`` — never raises for transport errors."""
    config = _settings()
    if not config["host"]:
        return {
            "delivered": False,
            "detail": "SMTP is not configured (set SMTP_HOST, SMTP_PORT and SMTP_FROM).",
        }

    try:
        await asyncio.to_thread(_send_sync, to, subject, body, config)
    except Exception as error:  # surface the transport error, do not hide it
        return {"delivered": False, "detail": f"{type(error).__name__}: {error}"}

    return {"delivered": True, "detail": f"Accepted by {config['host']}:{config['port']}"}
