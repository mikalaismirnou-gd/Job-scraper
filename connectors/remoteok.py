from datetime import datetime, timezone

from connectors.common import Vacancy, cutoff_datetime, http_client

API_URL = "https://remoteok.com/api"


def fetch(days: int = 3) -> list[Vacancy]:
    cutoff = cutoff_datetime(days)

    with http_client() as client:
        response = client.get(API_URL)
        response.raise_for_status()
        jobs = response.json()

    vacancies: list[Vacancy] = []
    for job in jobs:
        if "id" not in job or "epoch" not in job:
            continue  # first element is a legal notice, not a job

        posted_at = datetime.fromtimestamp(job["epoch"], tz=timezone.utc)
        if posted_at < cutoff:
            continue

        salary_min = job.get("salary_min") or 0
        salary_max = job.get("salary_max") or 0
        salary = f"${salary_min:,} - ${salary_max:,}" if salary_min or salary_max else None

        vacancies.append(
            Vacancy(
                source="remoteok",
                source_id=str(job["id"]),
                title=job.get("position", ""),
                company=job.get("company", ""),
                location=job.get("location", ""),
                salary=salary,
                description=job.get("description", ""),
                remote_flag=True,
                raw_payload=job,
            )
        )

    return vacancies


if __name__ == "__main__":
    results = fetch()
    print(f"RemoteOK: {len(results)} vacancies in the last 3 days")
    if results:
        print(results[0]["title"], "@", results[0]["company"])
