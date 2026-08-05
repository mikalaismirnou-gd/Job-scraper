import re
import time

import httpx

from connectors.ats_common import html_to_text, load_companies, polite_sleep
from connectors.common import REMOTE_HINT, USER_AGENT, Vacancy

LIST_URL_TEMPLATE = "https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs"
DETAIL_URL_TEMPLATE = "https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}{path}"
LIST_LIMIT = 100  # single page per company; older postings beyond this may be missed
MAX_ATTEMPTS = 4  # Workday's WAF intermittently returns HTTP 400 with no cause; retry with backoff

_DAYS_AGO_RE = re.compile(r"(\d+)\+?\s*Days? Ago", re.IGNORECASE)


def _request_with_retry(client, method: str, url: str, **kwargs):
    response = None
    for attempt in range(MAX_ATTEMPTS):
        if attempt > 0:
            time.sleep(3 * attempt)
        response = client.request(method, url, **kwargs)
        if response.status_code == 200:
            return response
    return response


def _posted_days_ago(posted_on: str) -> int | None:
    text = posted_on.strip().lower()
    if text == "posted today":
        return 0
    if text == "posted yesterday":
        return 1
    match = _DAYS_AGO_RE.search(posted_on)
    if match:
        return int(match.group(1))
    return None


def fetch(days: int = 3) -> list[Vacancy]:
    companies = load_companies("workday_companies.csv")

    vacancies: list[Vacancy] = []
    for i, row in enumerate(companies):
        if i > 0:
            polite_sleep()

        tenant, wd_host, site = row["tenant"], row["wd_host"], row["site"]
        tenant_origin = f"https://{tenant}.{wd_host}.myworkdayjobs.com"
        # Workday's WAF blocks requests when the same connection/client is reused
        # across different tenant subdomains, and also rejects requests without an
        # Origin/Referer matching the tenant's own domain (HTTP 400 either way) -
        # so each company gets its own short-lived client.
        tenant_headers = {
            "User-Agent": USER_AGENT,
            "Origin": tenant_origin,
            "Referer": f"{tenant_origin}/{site}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=20) as client:
            response = _request_with_retry(
                client,
                "POST",
                LIST_URL_TEMPLATE.format(tenant=tenant, wd_host=wd_host, site=site),
                json={"appliedFacets": {}, "limit": LIST_LIMIT, "offset": 0, "searchText": ""},
                headers=tenant_headers,
            )
            if response.status_code != 200:
                continue
            postings = response.json().get("jobPostings", [])

            for posting in postings:
                days_ago = _posted_days_ago(posting.get("postedOn", ""))
                if days_ago is None or days_ago > days:
                    continue

                title = posting.get("title", "")
                location = posting.get("locationsText", "")

                description = ""
                polite_sleep()
                detail_response = _request_with_retry(
                    client,
                    "GET",
                    DETAIL_URL_TEMPLATE.format(
                        tenant=tenant, wd_host=wd_host, site=site, path=posting["externalPath"]
                    ),
                    headers=tenant_headers,
                )
                if detail_response.status_code == 200:
                    info = detail_response.json().get("jobPostingInfo", {})
                    description = html_to_text(info.get("jobDescription"))

                vacancies.append(
                    Vacancy(
                        source="workday",
                        source_id=f"{tenant}:{posting['externalPath']}",
                        title=title,
                        company=row["company"],
                        location=location,
                        salary=None,
                        description=description,
                        remote_flag=bool(REMOTE_HINT.search(f"{title} {location}")),
                        raw_payload=posting,
                    )
                )

    return vacancies


if __name__ == "__main__":
    results = fetch()
    print(f"Workday: {len(results)} vacancies in the last 3 days")
    if results:
        print(results[0]["title"], "@", results[0]["company"])
