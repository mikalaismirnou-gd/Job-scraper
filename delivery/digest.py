import os
from datetime import date
from html import escape

import httpx
import psycopg

FROM_ADDRESS = "Job Scraper <onboarding@resend.dev>"

_APPLY_URL_FIELDS = {
    "remoteok": ("url", "apply_url"),
    "wwr": ("link",),
    "adzuna": ("redirect_url",),
    "greenhouse": ("absolute_url",),
    "lever": ("hostedUrl", "applyUrl"),
    "ashby": ("jobUrl", "applyUrl"),
    "smartrecruiters": ("postingUrl", "applyUrl"),
    "personio": ("url",),
}


def apply_url(vacancy: dict) -> str:
    for field in _APPLY_URL_FIELDS.get(vacancy["source"], ()):
        url = vacancy["raw_payload"].get(field)
        if url:
            return url
    return ""


def build_subject(matches: list[dict]) -> str:
    return f"Job digest — {len(matches)} matches — {date.today().isoformat()}"


def build_html(client_name: str, matches: list[dict]) -> str:
    items = []
    for m in matches:
        location = "Remote" if m["remote_flag"] else (m["location"] or "")
        salary = f" &middot; {escape(m['salary'])}" if m["salary"] else ""
        items.append(
            f"""
            <li style="margin-bottom: 16px;">
              <a href="{escape(apply_url(m))}"><strong>{escape(m['title'])}</strong></a>
              &mdash; {escape(m['company'] or '')} &middot; {escape(location)}{salary}<br/>
              <span style="color: #666; font-size: 13px;">{escape(m['reasoning'])}</span>
            </li>
            """
        )
    body = "".join(items) or "<p>No new matches today.</p>"
    remoteok_note = (
        '<p style="color: #999; font-size: 12px;">Some listings sourced from '
        '<a href="https://remoteok.com">Remote OK</a>.</p>'
        if any(m["source"] == "remoteok" for m in matches)
        else ""
    )
    return f"""
    <html><body>
      <p>Hi {escape(client_name)},</p>
      <p>Here are today's matches:</p>
      <ul>{body}</ul>
      <p style="color: #999; font-size: 12px;">Reply to this email if any of these are off-target.</p>
      {remoteok_note}
    </body></html>
    """


def send_digest(to_email: str, client_name: str, matches: list[dict]) -> str | None:
    if not matches:
        return None

    response = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}"},
        json={
            "from": FROM_ADDRESS,
            "to": [to_email],
            "subject": build_subject(matches),
            "html": build_html(client_name, matches),
        },
        timeout=20,
    )
    response.raise_for_status()
    return response.json()["id"]


def log_delivery(conn: psycopg.Connection, client_id: int, matches: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO delivery (client_id, vacancy_id, status) VALUES (%s, %s, 'sent');",
            [(client_id, m["id"]) for m in matches],
        )
