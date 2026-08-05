from datetime import datetime, timezone

from connectors.ats_common import html_to_text, load_companies, polite_sleep
from connectors.common import REMOTE_HINT, Vacancy, cutoff_datetime, http_client

API_URL_TEMPLATE = "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs"


def fetch(days: int = 3) -> list[Vacancy]:
    cutoff = cutoff_datetime(days)
    companies = load_companies("greenhouse_companies.csv")

    vacancies: list[Vacancy] = []
    with http_client() as client:
        for i, row in enumerate(companies):
            if i > 0:
                polite_sleep()

            response = client.get(
                API_URL_TEMPLATE.format(slug=row["slug"]),
                params={"content": "true"},
            )
            if response.status_code != 200:
                continue
            jobs = response.json().get("jobs", [])

            for job in jobs:
                published = job.get("first_published") or job.get("updated_at")
                if not published:
                    continue
                posted_at = datetime.fromisoformat(published)
                if posted_at.tzinfo is None:
                    posted_at = posted_at.replace(tzinfo=timezone.utc)
                if posted_at < cutoff:
                    continue

                title = job.get("title", "")
                location = job.get("location", {}).get("name", "")
                description = html_to_text(job.get("content"))

                vacancies.append(
                    Vacancy(
                        source="greenhouse",
                        source_id=str(job["id"]),
                        title=title,
                        company=row["company"],
                        location=location,
                        salary=None,
                        description=description,
                        remote_flag=bool(REMOTE_HINT.search(f"{title} {location}")),
                        raw_payload=job,
                    )
                )

    return vacancies


if __name__ == "__main__":
    results = fetch()
    print(f"Greenhouse: {len(results)} vacancies in the last 3 days")
    if results:
        print(results[0]["title"], "@", results[0]["company"])
