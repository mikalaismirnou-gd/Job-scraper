from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

from connectors.common import REMOTE_HINT, Vacancy, cutoff_datetime, http_client

RSS_URL = "https://weworkremotely.com/remote-jobs.rss"


def _split_title(raw_title: str) -> tuple[str, str]:
    if ": " in raw_title:
        company, position = raw_title.split(": ", 1)
        return company.strip(), position.strip()
    return "", raw_title.strip()


def fetch(days: int = 3) -> list[Vacancy]:
    cutoff = cutoff_datetime(days)

    with http_client() as client:
        response = client.get(RSS_URL)
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)

    vacancies: list[Vacancy] = []
    for item in root.iter("item"):
        pub_date_text = item.findtext("pubDate")
        if not pub_date_text:
            continue
        posted_at = parsedate_to_datetime(pub_date_text)
        if posted_at < cutoff:
            continue

        link = item.findtext("link", "")
        guid = item.findtext("guid", link)
        raw_title = item.findtext("title", "")
        company, position = _split_title(raw_title)
        description = item.findtext("description", "")
        region = item.findtext("region", "")

        raw_payload = {
            "title": raw_title,
            "region": region,
            "category": item.findtext("category", ""),
            "type": item.findtext("type", ""),
            "description": description,
            "pubDate": pub_date_text,
            "link": link,
            "guid": guid,
        }

        vacancies.append(
            Vacancy(
                source="wwr",
                source_id=guid,
                title=position,
                company=company,
                location=region,
                salary=None,
                description=description,
                remote_flag=bool(REMOTE_HINT.search(raw_title + " " + region)),
                raw_payload=raw_payload,
            )
        )

    return vacancies


if __name__ == "__main__":
    results = fetch()
    print(f"WWR: {len(results)} vacancies in the last 3 days")
    if results:
        print(results[0]["title"], "@", results[0]["company"])
