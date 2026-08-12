"""Download a reproducible Arabic Wikipedia text corpus for external evaluation.

The corpus is evaluation data, not a bundled runtime fixture. Every JSONL row
preserves page id, title, source URL, revision metadata, and retrieval time.
Search pagination is explicit because the public MediaWiki API may cap one
search response below the requested limit.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

API = "https://ar.wikipedia.org/w/api.php"
UA = "arafix-evaluation-corpus/1.0 (research; contact via repository)"
SEARCH_QUERIES = (
    "اللغة العربية",
    "التاريخ",
    "العلوم",
    "الجغرافيا",
    "الفلسفة",
    "الفيزياء",
    "الكيمياء",
    "مصر",
    "العراق",
    "الإسلام",
)


def api(session: requests.Session, params: dict[str, Any]) -> dict[str, Any]:
    request_params = {**params, "format": "json", "formatversion": "2"}
    for attempt in range(5):
        response = session.get(API, params=request_params, timeout=40)
        if response.status_code != 429 and response.status_code < 500:
            response.raise_for_status()
            return response.json()
        retry_after = response.headers.get("Retry-After")
        delay = float(retry_after) if retry_after else min(2 ** attempt, 16)
        time.sleep(delay)
    response.raise_for_status()
    return response.json()


def collect_candidates(session: requests.Session, wanted: int) -> list[dict[str, Any]]:
    """Collect deterministic, de-duplicated search candidates using continuation."""
    candidates: list[dict[str, Any]] = []
    seen: set[int] = set()
    target = max(wanted * 3, 100)
    for query in SEARCH_QUERIES:
        params: dict[str, Any] = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "srnamespace": 0,
            "srlimit": 20,
            "srprop": "size|timestamp|wordcount",
        }
        for _ in range(20):
            result = api(session, params)
            for item in result.get("query", {}).get("search", []):
                pageid = int(item["pageid"])
                if pageid not in seen:
                    seen.add(pageid)
                    candidates.append(item)
            if len(candidates) >= target:
                return candidates
            continuation = result.get("continue")
            if not continuation:
                break
            params.update(continuation)
            time.sleep(1.0)
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--min-chars", type=int, default=1000)
    args = parser.parse_args()
    if args.n <= 0:
        raise SystemExit("--n must be positive")
    if args.min_chars <= 0:
        raise SystemExit("--min-chars must be positive")

    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Language": "ar"})
    candidates = [
        item for item in collect_candidates(session, args.n)
        if int(item.get("size", 0) or 0) >= args.min_chars
    ]
    if len(candidates) < args.n:
        raise SystemExit(
            f"only {len(candidates)} real search candidates met min_chars={args.min_chars}; "
            f"refusing to fabricate {args.n}"
        )

    retrieved_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict[str, Any]] = []
    # A whole-article extracts request is deliberately limited to one page by
    # MediaWiki, so fetch each selected page explicitly rather than silently
    # accepting a partial batch.
    for candidate in candidates:
        if len(rows) >= args.n:
            break
        pages = api(session, {
            "action": "query",
            "pageids": str(candidate["pageid"]),
            "prop": "extracts|revisions",
            "explaintext": 1,
            "exsectionformat": "plain",
            "exlimit": 1,
            "rvprop": "ids|timestamp",
            "rvslots": "main",
        }).get("query", {}).get("pages", [])
        if not pages:
            continue
        page = pages[0]
        text = (page.get("extract") or "").strip()
        if len(text) < args.min_chars:
            continue
        revisions = page.get("revisions") or []
        revision = revisions[0] if revisions else {}
        rows.append({
            "id": f"arwiki-{int(page['pageid'])}",
            "pageid": int(page["pageid"]),
            "title": page["title"],
            "source": "Arabic Wikipedia",
            "url": f"https://ar.wikipedia.org/wiki/{requests.utils.quote(page['title'].replace(' ', '_'))}",
            "api": API,
            "revision_id": revision.get("revid"),
            "revision_timestamp": revision.get("timestamp"),
            "retrieved_at": retrieved_at,
            "text": text,
        })
        time.sleep(0.4)

    if len(rows) < args.n:
        raise SystemExit(
            f"API returned only {len(rows)} usable pages; refusing to fabricate {args.n}"
        )
    rows = rows[: args.n]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(json.dumps({"output": str(args.output), "documents": len(rows), "retrieved_at": retrieved_at}, ensure_ascii=False))


if __name__ == "__main__":
    main()
