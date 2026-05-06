from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse


DATE_FORMATS = ("%d %B %Y", "%d %b %Y")


@dataclass
class NiceItem:
    title: str
    reference: str
    url: str
    guidance_type: str = ""
    published: str = ""
    last_updated: str = ""
    status: str = "other"
    source_pages: list[dict] | None = None
    source_incomplete: bool = False
    notes: list[str] | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class NiceClient:
    def __init__(self, config: dict):
        try:
            import requests
        except ImportError as exc:
            raise ImportError("Live NICE retrieval requires the packages in requirements.txt.") from exc
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "NICE monthly guidance governance monitor (+internal clinical governance use)"
        })

    def items_for_month(self, start: date, end: date) -> tuple[list[dict], list[str]]:
        failures: list[str] = []
        try:
            candidates = self._published_index()
        except Exception as exc:
            failures.append(f"NICE published index failed: {exc}")
            return [], failures

        selected = []
        seen = set()
        for item in candidates:
            if item.reference in seen:
                continue
            published = _parse_date(item.published)
            updated = _parse_date(item.last_updated)
            if _in_range(published, start, end) or _in_range(updated, start, end):
                seen.add(item.reference)
                try:
                    selected.append(self.enrich_item(item).to_dict())
                except Exception as exc:
                    item.source_incomplete = True
                    item.notes = [f"Source enrichment failed: {exc}"]
                    selected.append(item.to_dict())
        return selected, failures

    def _published_index(self) -> list[NiceItem]:
        params = [("ndt", "Guidance"), ("ps", str(self.config.get("page_size", 2500))), ("sp", "on")]
        for guidance_type in self.config.get("include_guidance_types", []):
            params.append(("ngt", guidance_type))

        items = self._published_index_request(params)

        # Quality standards are a separate document type on NICE and are hidden if
        # the guidance-type filter is also sent.
        quality_params = [("ndt", "Quality standard"), ("ps", str(self.config.get("page_size", 2500))), ("sp", "on")]
        items.extend(self._published_index_request(quality_params))

        deduped = {}
        for item in items:
            deduped[item.reference] = item
        return list(deduped.values())

    def _published_index_request(self, params: list[tuple[str, str]]) -> list[NiceItem]:
        from bs4 import BeautifulSoup

        response = self.session.get(
            self.config.get("published_url", "https://www.nice.org.uk/guidance/published"),
            params=params,
            timeout=self.config.get("request_timeout_seconds", 45),
        )
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        items: list[NiceItem] = []
        for row in soup.select("table tbody tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
            if len(cells) < 4:
                continue
            link = row.find("a", href=True)
            if not link:
                continue
            items.append(NiceItem(
                title=cells[0],
                reference=cells[1],
                url=urljoin(response.url, link["href"]),
                published=cells[2],
                last_updated=cells[3],
            ))
        if not items:
            # NICE occasionally renders a simplified table; this catches the markdown-like text fallback.
            text = soup.get_text("\n", strip=True)
            pattern = re.compile(r"(.+?)\s*\|\s*([A-Z]+[0-9]+)\s*\|\s*(\d{1,2} \w+ \d{4})\s*\|\s*(\d{1,2} \w+ \d{4})")
            for match in pattern.finditer(text):
                ref = match.group(2)
                items.append(NiceItem(
                    title=match.group(1).strip(),
                    reference=ref,
                    url=f"https://www.nice.org.uk/guidance/{ref.lower()}",
                    published=match.group(3),
                    last_updated=match.group(4),
                ))
        return items

    def enrich_item(self, item: NiceItem) -> NiceItem:
        from bs4 import BeautifulSoup

        pages: list[dict] = []
        overview = self._fetch_page(item.url)
        item.guidance_type = overview.get("guidance_type") or item.guidance_type
        item.status = _status_from_text(item.title + " " + overview.get("text", ""))
        pages.append(overview)

        soup = BeautifulSoup(overview["html"], "html.parser")
        useful_links = self._guidance_source_links(soup, item)

        # Fallback for older NICE pages where the overview navigation is sparse.
        for link in soup.find_all("a", href=True):
            label = link.get_text(" ", strip=True).lower()
            href = urljoin(item.url, link["href"])
            if any(key in label for key in ("recommend", "evidence", "history", "update information", "rationale", "implementation", "advice")):
                useful_links.append(href)
            if _looks_like_pdf_resource(href, item.reference):
                useful_links.append(href)

        max_links = int(self.config.get("max_source_links_per_item", 40))
        for href in list(dict.fromkeys(useful_links))[:max_links]:
            try:
                if _looks_like_pdf_resource(href, item.reference):
                    pages.append(self._fetch_pdf(href))
                else:
                    pages.append(self._fetch_page(href))
            except Exception as exc:
                item.source_incomplete = True
                item.notes = (item.notes or []) + [f"Could not access {href}: {exc}"]

        item.source_pages = pages
        return item

    def _guidance_source_links(self, soup, item: NiceItem) -> list[str]:
        """Return same-guidance NICE links that may contain recommendations, definitions or evidence.

        NICE quality standards often put the clinically important material in separate
        quality-statement pages or the generated PDF, so we follow all same-reference
        chapter, evidence, history, information-for-public and resource links instead
        of relying on link text alone.
        """
        ref = item.reference.lower()
        links: list[str] = []
        for link in soup.find_all("a", href=True):
            href = urljoin(item.url, link["href"]).split("#", 1)[0]
            parsed = urlparse(href)
            path = parsed.path.lower().rstrip("/")
            same_guidance = path == f"/guidance/{ref}" or path.startswith(f"/guidance/{ref}/")
            if not same_guidance:
                continue
            if any(part in path for part in (
                "/chapter/",
                "/evidence",
                "/history",
                "/informationforpublic",
                "/resources",
                "/tools-and-resources",
            )):
                links.append(href)
        return links

    def _fetch_page(self, url: str) -> dict:
        from bs4 import BeautifulSoup

        response = self.session.get(url, timeout=self.config.get("request_timeout_seconds", 45))
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        guidance_type = ""
        for li in soup.select("li"):
            text = li.get_text(" ", strip=True)
            if "guideline" in text.lower() or "guidance" in text.lower() or "quality standard" in text.lower() or "technology appraisal" in text.lower():
                guidance_type = text.replace("Reference number:", "").strip()
                break
        main = soup.find("main") or soup
        table_text = _extract_tables(main)
        body_text = main.get_text("\n", strip=True)
        if table_text:
            body_text = f"{body_text}\n\nExtracted tables:\n{table_text}"
        return {
            "url": response.url,
            "kind": "html",
            "title": (soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else ""),
            "guidance_type": guidance_type,
            "text": _clean_text(body_text),
            "html": response.text,
        }

    def _fetch_pdf(self, url: str) -> dict:
        from pypdf import PdfReader
        from bs4 import BeautifulSoup

        response = self.session.get(url, timeout=self.config.get("request_timeout_seconds", 45))
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        if "pdf" not in content_type and not response.content.startswith(b"%PDF"):
            soup = BeautifulSoup(response.text, "html.parser")
            main = soup.find("main") or soup
            table_text = _extract_tables(main)
            body_text = main.get_text("\n", strip=True)
            if table_text:
                body_text = f"{body_text}\n\nExtracted tables:\n{table_text}"
            return {
                "url": response.url,
                "kind": "html-resource",
                "title": (soup.find("h1").get_text(" ", strip=True) if soup.find("h1") else Path(url).name),
                "text": _clean_text(body_text),
                "html": response.text,
            }
        max_bytes = int(self.config.get("max_pdf_mb", 12)) * 1024 * 1024
        if len(response.content) > max_bytes:
            raise ValueError("PDF exceeded configured size limit")
        tmp = Path(".nice_tmp.pdf")
        tmp.write_bytes(response.content)
        try:
            reader = PdfReader(str(tmp))
            text = "\n".join(page.extract_text() or "" for page in reader.pages[:80])
        finally:
            tmp.unlink(missing_ok=True)
        return {"url": response.url, "kind": "pdf", "title": Path(url).name, "text": _clean_text(text), "html": ""}


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


def _status_from_text(text: str) -> str:
    lower = text.lower()
    if "terminated appraisal" in lower or "unable to make a recommendation" in lower:
        return "terminated"
    if "withdrawn" in lower:
        return "withdrawn"
    if "updates and replaces" in lower or "updated and replaces" in lower:
        return "replaced"
    if "last updated" in lower or "updated" in lower:
        return "updated"
    if "published:" in lower:
        return "new"
    return "other"


def _clean_text(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


def _extract_tables(root) -> str:
    tables = []
    for table in root.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
            if cells:
                rows.append(" | ".join(cells))
        if rows:
            tables.append("\n".join(rows))
    return "\n\n".join(tables)


def _looks_like_pdf_resource(url: str, reference: str) -> bool:
    lower = url.lower().split("?", 1)[0].rstrip("/")
    ref = reference.lower()
    if lower.endswith(".pdf"):
        return True
    if f"/guidance/{ref}/resources/" in lower:
        return True
    return False
