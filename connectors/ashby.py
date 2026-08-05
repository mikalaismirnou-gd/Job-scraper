from datetime import datetime, timezone

from connectors.ats_common import html_to_text, load_companies, polite_sleep
from connectors.common import Vacancy, cutoff_datetime, http_client

API_URL_TEMPLATE = "https://api.ashbyhq.com/posting-api/job-board/{slug}"


def fetch(days: int = 3) -> list[Vacancy]:
    cutoff = cutoff_datetime(days)
    companies = load_companies("ashby_companies.csv")

    vacancies: list[Vacancy] = []
    with http_client() as client:
        for i, row in enumerate(companies):
            if i > 0:
                polite_sleep()

            response = client.get(API_URL_TEMPLATE.format(slug=row["slug"]))
            if response.status_code != 200:
                continue
            jobs = response.json().get("jobs", [])

            for job in jobs:
                published = job.get("publishedAt")
                if not published:
                    continue
                posted_at = datetime.fromisoformat(published.replace("Z", "+00:00"))
                if posted_at < cutoff:
                    continue

                vacancies.append(
                    Vacancy(
                        source="ashby",
                        source_id=job["id"],
                        title=job.get("title", ""),
                        company=row["company"],
                        location=job.get("location", ""),
                        salary=None,
                        description=html_to_text(job.get("descriptionPlain") or job.get("descriptionHtml")),
                        remote_flag=bool(job.get("isRemote")),
                        raw_payload=job,
                    )
                )

    return vacancies


if __name__ == "__main__":
    results = fetch()
    print(f"Ashby: {len(results)} vacancies in the last 3 days")
    if results:
        print(results[0]["title"], "@", results[0]["company"])
