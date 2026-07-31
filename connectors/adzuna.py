import os
import re
import time

from connectors.common import Vacancy, http_client

API_URL_TEMPLATE = "https://api.adzuna.com/v1/api/jobs/pl/search/{page}"
RESULTS_PER_PAGE = 50
MAX_PAGES = 100  # safety ceiling; loop stops early once a page is empty
REQUEST_DELAY_SECONDS = 2.5  # keeps us under Adzuna's 25 calls/minute limit

REMOTE_HINT = re.compile(r"remote|zdaln", re.IGNORECASE)


def fetch(days: int = 3) -> list[Vacancy]:
    app_id = os.environ["ADZUNA_APP_ID"]
    app_key = os.environ["ADZUNA_APP_KEY"]

    vacancies: list[Vacancy] = []
    with http_client() as client:
        for page in range(1, MAX_PAGES + 1):
            if page > 1:
                time.sleep(REQUEST_DELAY_SECONDS)

            response = client.get(
                API_URL_TEMPLATE.format(page=page),
                params={
                    "app_id": app_id,
                    "app_key": app_key,
                    "max_days_old": days,
                    "results_per_page": RESULTS_PER_PAGE,
                    "category": "it-jobs",
                },
            )
            response.raise_for_status()
            results = response.json().get("results", [])
            if not results:
                break

            for job in results:
                title = job.get("title", "")
                description = job.get("description", "")
                location = job.get("location", {}).get("display_name", "")

                salary_min = job.get("salary_min")
                salary_max = job.get("salary_max")
                salary = None
                if salary_min or salary_max:
                    salary = f"{salary_min:,.0f} - {salary_max:,.0f}"

                vacancies.append(
                    Vacancy(
                        source="adzuna",
                        source_id=str(job["id"]),
                        title=title,
                        company=job.get("company", {}).get("display_name", ""),
                        location=location,
                        salary=salary,
                        description=description,
                        remote_flag=bool(REMOTE_HINT.search(f"{title} {description} {location}")),
                        raw_payload=job,
                    )
                )

    return vacancies


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    results = fetch()
    print(f"Adzuna: {len(results)} vacancies in the last 3 days")
    if results:
        print(results[0]["title"], "@", results[0]["company"])
