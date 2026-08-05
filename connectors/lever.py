from datetime import datetime, timezone

from connectors.ats_common import load_companies, polite_sleep
from connectors.common import Vacancy, cutoff_datetime, http_client

API_URL_TEMPLATE = "https://api.lever.co/v0/postings/{slug}"


def fetch(days: int = 3) -> list[Vacancy]:
    cutoff = cutoff_datetime(days)
    companies = load_companies("lever_companies.csv")

    vacancies: list[Vacancy] = []
    with http_client() as client:
        for i, row in enumerate(companies):
            if i > 0:
                polite_sleep()

            response = client.get(
                API_URL_TEMPLATE.format(slug=row["slug"]),
                params={"mode": "json"},
            )
            if response.status_code != 200:
                continue
            jobs = response.json()

            for job in jobs:
                posted_at = datetime.fromtimestamp(job["createdAt"] / 1000, tz=timezone.utc)
                if posted_at < cutoff:
                    continue

                categories = job.get("categories", {})
                description = " ".join(
                    filter(None, [job.get("descriptionPlain"), job.get("descriptionBodyPlain")])
                )

                vacancies.append(
                    Vacancy(
                        source="lever",
                        source_id=job["id"],
                        title=job.get("text", ""),
                        company=row["company"],
                        location=categories.get("location", ""),
                        salary=None,
                        description=description,
                        remote_flag=job.get("workplaceType") == "remote",
                        raw_payload=job,
                    )
                )

    return vacancies


if __name__ == "__main__":
    results = fetch()
    print(f"Lever: {len(results)} vacancies in the last 3 days")
    if results:
        print(results[0]["title"], "@", results[0]["company"])
