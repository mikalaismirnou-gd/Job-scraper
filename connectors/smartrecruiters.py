from datetime import datetime, timezone

from connectors.ats_common import html_to_text, load_companies, polite_sleep
from connectors.common import REMOTE_HINT, Vacancy, cutoff_datetime, http_client

LIST_URL_TEMPLATE = "https://api.smartrecruiters.com/v1/companies/{slug}/postings"
DETAIL_URL_TEMPLATE = "https://api.smartrecruiters.com/v1/companies/{slug}/postings/{job_id}"


def _fetch_description(client, slug: str, job_id: str) -> str:
    response = client.get(DETAIL_URL_TEMPLATE.format(slug=slug, job_id=job_id))
    if response.status_code != 200:
        return ""
    sections = response.json().get("jobAd", {}).get("sections", {})
    parts = [s.get("text", "") for s in sections.values()]
    return html_to_text(" ".join(parts))


def fetch(days: int = 3) -> list[Vacancy]:
    cutoff = cutoff_datetime(days)
    companies = load_companies("smartrecruiters_companies.csv")

    vacancies: list[Vacancy] = []
    with http_client() as client:
        for i, row in enumerate(companies):
            if i > 0:
                polite_sleep()

            response = client.get(
                LIST_URL_TEMPLATE.format(slug=row["slug"]),
                params={"limit": 100},
            )
            if response.status_code != 200:
                continue
            jobs = response.json().get("content", [])

            for job in jobs:
                released = job.get("releasedDate")
                if not released:
                    continue
                posted_at = datetime.fromisoformat(released.replace("Z", "+00:00"))
                if posted_at < cutoff:
                    continue

                location = job.get("location", {})
                title = job.get("name", "")
                location_str = location.get("fullLocation", "")

                polite_sleep()
                description = _fetch_description(client, row["slug"], job["id"])

                vacancies.append(
                    Vacancy(
                        source="smartrecruiters",
                        source_id=job["id"],
                        title=title,
                        company=row["company"],
                        location=location_str,
                        salary=None,
                        description=description,
                        remote_flag=bool(location.get("remote"))
                        or bool(REMOTE_HINT.search(f"{title} {location_str}")),
                        raw_payload=job,
                    )
                )

    return vacancies


if __name__ == "__main__":
    results = fetch()
    print(f"SmartRecruiters: {len(results)} vacancies in the last 3 days")
    if results:
        print(results[0]["title"], "@", results[0]["company"])
