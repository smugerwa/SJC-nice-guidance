from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin


DATE_FORMATS = ("%d %B %Y", "%d %b %Y")


@dataclass
class MhraItem:
    title: str
    reference: str
    url: str
    alert_type: str = ""
    medical_specialisms: list[str] | None = None
    issued: str = ""
    summary: str = ""
    source_pages: list[dict] | None = None
    source_incomplete: bool = False
    notes: list[str] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class MhraClient:
    def __init__(self, config: dict):
        try:
            import requests
        except ImportError as exc:
            raise ImportError("Live MHRA retrieval requires the packages in requirements.txt.") from exc
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MHRA weekly primary care safety monitor (+internal clinical governance use)"
        })

    def items_for_period(self, start: date, end: date) -> tuple[list[dict], list[str]]:
        failures: list[str] = []
        selected: list[MhraItem] = []
        seen: set[str] = set()
        max_pages = int(self.config.get("max_pages", 8))

        try:
            for page in range(1, max_pages + 1):
                items = self._listing_page(page)
                if not items:
                    break
                older_than_period = False
                for item in items:
                    issued = _parse_date(item.issued)
                    if issued and issued < start:
                        older_than_period = True
                    if not _in_range(issued, start, end):
                        continue
                    key = item.url or item.title
                    if key in seen:
                        continue
                    seen.add(key)
                    try:
                        selected.append(self.enrich_item(item))
                    except Exception as exc:
                        item.source_incomplete = True
                        item.notes = [f"Source enrichment failed: {exc}"]
                        selected.append(item)
                if older_than_period:
                    break
        except Exception as exc:
            failures.append(f"MHRA alerts listing failed: {exc}")

        return [item.to_dict() for item in selected], failures

    def _listing_page(self, page: int) -> list[MhraItem]:
        from bs4 import BeautifulSoup

        params = {}
        if page > 1:
            params["page"] = page
        response = self.session.get(
            self.config.get("alerts_url", "https://www.gov.uk/drug-device-alerts"),
            params=params,
            timeout=self.config.get("request_timeout_seconds", 45),
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        main = soup.find("main") or soup
        candidates = main.select("li")
        items: list[MhraItem] = []
        for node in candidates:
            link = node.find("a", href=True)
            text = node.get_text("\n", strip=True)
            if not link or "Issued:" not in text or "Alert type:" not in text:
                continue
            title = link.get_text(" ", strip=True)
            if not title or title.lower() in {"get emails", "subscribe to feed"}:
                continue
            issued = _field_from_text(text, "Issued")
            alert_type = _field_from_text(text, "Alert type")
            specialism_text = _field_from_text(text, "Medical specialism")
            summary = _summary_from_listing(text, title)
            items.append(MhraItem(
                title=title,
                reference=_reference_from_title(title),
                url=urljoin(response.url, link["href"]),
                alert_type=alert_type,
                medical_specialisms=_split_specialisms(specialism_text),
                issued=issued,
                summary=summary,
            ))
        return items

    def enrich_item(self, item: MhraItem) -> MhraItem:
        page = self._fetch_page(item.url)
        item.source_pages = [page]
        if not item.reference:
            item.reference = _reference_from_title(page.get("title", "")) or Path(item.url.rstrip("/")).name
        if not item.alert_type:
            item.alert_type = page.get("alert_type", "")
        if not item.issued:
            item.issued = page.get("issued", "")
        if not item.medical_specialisms:
            item.medical_specialisms = page.get("medical_specialisms", [])
        return item

    def _fetch_page(self, url: str) -> dict:
        from bs4 import BeautifulSoup

        response = self.session.get(url, timeout=self.config.get("request_timeout_seconds", 45))
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        main = soup.find("main") or soup
        title = soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else ""
        text = _clean_text(main.get_text("\n", strip=True))
        return {
            "url": response.url,
            "kind": "html",
            "title": title,
            "alert_type": _field_from_text(text, "Alert type"),
            "issued": _field_from_text(text, "Issued"),
            "medical_specialisms": _split_specialisms(_field_from_text(text, "Medical specialism")),
            "text": text,
            "html": response.text,
        }


def load_sample_items(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = re.sub(r"\s+", " ", value.strip())
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _in_range(value: date | None, start: date, end: date) -> bool:
    return value is not None and start <= value <= end


def _field_from_text(text: str, field: str) -> str:
    pattern = re.compile(rf"{re.escape(field)}:\s*([^\n]+)", re.IGNORECASE)
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def _summary_from_listing(text: str, title: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    summary_lines = []
    seen_title = False
    for line in lines:
        if line == title:
            seen_title = True
            continue
        if not seen_title:
            continue
        if line.startswith(("Alert type:", "Medical specialism:", "Issued:")):
            break
        summary_lines.append(line)
    return " ".join(summary_lines)


def _split_specialisms(value: str) -> list[str]:
    if not value:
        return []
    cleaned = re.sub(r"\s+and\s+\d+\s+others?$", "", value).strip()
    parts = re.split(r",|\band\b", cleaned)
    return [part.strip() for part in parts if part.strip()]


def _reference_from_title(title: str) -> str:
    patterns = (
        r"\bEL\(\d{2}\)A/\d+\b",
        r"\bNatPSA/\d{4}/\d+/[A-Z]+\b",
        r"\bDSI/\d{4}/\d+\b",
        r"\bMDA/\d{4}/\d+\b",
    )
    for pattern in patterns:
        match = re.search(pattern, title)
        if match:
            return match.group(0)
    return ""


def _clean_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()
