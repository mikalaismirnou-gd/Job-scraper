from datetime import datetime
from xml.etree import ElementTree

from connectors.ats_common import html_to_text, load_companies, polite_sleep
from connectors.common import REMOTE_HINT, Vacancy, cutoff_datetime, http_client

XML_URL_TEMPLATES = [
    "https://{slug}.jobs.personio.com/xml",
    "https://{slug}.jobs.personio.de/xml",
]


def _field(position, tag: str) -> str:
    el = position.find(tag)
    return el.text or "" if el is not None else ""


def _description(position) -> str:
    parts = []
    for desc in position.findall("jobDescriptions/jobDescription"):
        value = desc.find("value")
        if value is not None and value.text:
            parts.append(html_to_text(value.text))
    return " ".join(parts)


def fetch(days: int = 3) -> list[Vacancy]:
    cutoff = cutoff_datetime(days)
    companies = load_companies("personio_companies.csv")

    vacancies: list[Vacancy] = []
    with http_client() as client:
        for i, row in enumerate(companies):
            if i > 0:
                polite_sleep()

            response = None
            for template in XML_URL_TEMPLATES:
                candidate = client.get(template.format(slug=row["slug"]))
                if candidate.status_code == 200:
                    response = candidate
                    break
            if response is None:
                continue
            root = ElementTree.fromstring(response.text)

            for position in root.findall("position"):
                created_at = _field(position, "createdAt")
                if not created_at:
                    continue
                posted_at = datetime.fromisoformat(created_at)
                if posted_at < cutoff:
                    continue

                title = _field(position, "name")
                office = _field(position, "office")

                vacancies.append(
                    Vacancy(
                        source="personio",
                        source_id=_field(position, "id"),
                        title=title,
                        company=row["company"],
                        location=office,
                        salary=None,
                        description=_description(position),
                        remote_flag=bool(REMOTE_HINT.search(f"{title} {office}")),
                        raw_payload={c.tag: c.text for c in position if c.tag != "jobDescriptions"},
                    )
                )

    return vacancies


if __name__ == "__main__":
    results = fetch()
    print(f"Personio: {len(results)} vacancies in the last 3 days")
    if results:
        print(results[0]["title"], "@", results[0]["company"])
