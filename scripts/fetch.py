#!/usr/bin/env python3
"""Discover and download the decision PDFs published on cassation.tn.

The site is a TYPO3 install with no sitemap and no directory listing, so the
PDFs have to be found by walking the public pages.  Everything discovered is
recorded in data/sources.json together with the page and link text it came
from, which is what later steps use to sanity-check the extracted case numbers.
"""

import argparse
import hashlib
import html
import json
import os
import queue
import re
import threading
import time
import urllib.parse as urlparse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "http://www.cassation.tn/"
PDF_DIR = os.path.join(ROOT, "downloads")
SOURCES = os.path.join(ROOT, "data", "sources.json")

USER_AGENT = "CourtDecisionsTN/1.0 (academic archival crawler)"
LINK_RE = re.compile(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S)
BASE_RE = re.compile(r'<base[^>]+href="([^"]+)"', re.I)
TAG_RE = re.compile(r"<[^>]+>")


def _opener():
    o = urllib.request.build_opener()
    o.addheaders = [("User-Agent", USER_AGENT)]
    return o


def _get(opener, url, binary=False, tries=4):
    for attempt in range(tries):
        try:
            with opener.open(url, timeout=60) as resp:
                data = resp.read()
            return data if binary else data.decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - network flakiness is expected
            if attempt == tries - 1:
                print(f"  !! {url}: {exc}")
                return None
            time.sleep(2 ** attempt)
    return None


def crawl(max_pages, workers):
    """Walk the site and collect every PDF link with its anchor text."""
    opener = _opener()
    lock = threading.Lock()
    seen = {BASE}
    pdfs = {}
    pending = queue.Queue()
    pending.put(BASE)
    counter = [0]

    def worker():
        while True:
            try:
                url = pending.get(timeout=30)
            except queue.Empty:
                return
            body = _get(opener, url) or ""
            # TYPO3 serves every page with <base href="/">, so relative links
            # must be resolved against that and not against the page path.
            base_tag = BASE_RE.search(body)
            page_base = urlparse.urljoin(url, base_tag.group(1)) if base_tag else url
            with lock:
                counter[0] += 1
                if counter[0] % 25 == 0:
                    print(f"  [{counter[0]}] pages={len(seen)} pdfs={len(pdfs)} "
                          f"queued={pending.qsize()}", flush=True)
            for match in LINK_RE.finditer(body):
                href = html.unescape(match.group(1)).strip()
                text = re.sub(r"\s+", " ", TAG_RE.sub("", match.group(2))).strip()
                if href.startswith(("#", "mailto:", "javascript:", "t3://")):
                    continue
                full = urlparse.urljoin(page_base, href).split("#")[0]
                if not full.startswith("http://www.cassation.tn"):
                    continue
                with lock:
                    if full.lower().split("?")[0].endswith(".pdf"):
                        entry = pdfs.setdefault(full, {"url": full, "links": []})
                        if text and text not in entry["links"]:
                            entry["links"].append(text)
                    elif full not in seen and len(seen) < max_pages:
                        seen.add(full)
                        pending.put(full)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"  crawled {len(seen)} pages, found {len(pdfs)} PDF links")
    return pdfs


def local_name(url):
    """Stable, filesystem-safe name derived from the URL path."""
    path = urlparse.unquote(urlparse.urlparse(url).path)
    name = os.path.basename(path)
    name = re.sub(r"[^\w.\-]+", "_", name, flags=re.UNICODE).strip("_")
    return name or hashlib.sha1(url.encode()).hexdigest()[:16] + ".pdf"


def download(pdfs, workers):
    os.makedirs(PDF_DIR, exist_ok=True)
    opener = _opener()
    lock = threading.Lock()
    items = list(pdfs.values())
    work = queue.Queue()
    for it in items:
        work.put(it)
    done = [0]

    def worker():
        while True:
            try:
                item = work.get(timeout=5)
            except queue.Empty:
                return
            name = local_name(item["url"])
            dest = os.path.join(PDF_DIR, name)
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                blob = open(dest, "rb").read()
            else:
                blob = _get(opener, item["url"], binary=True)
                if not blob or not blob.startswith(b"%PDF"):
                    item["error"] = "not a PDF" if blob else "download failed"
                    with lock:
                        done[0] += 1
                    continue
                with open(dest, "wb") as fh:
                    fh.write(blob)
            item["file"] = os.path.relpath(dest, ROOT)
            item["bytes"] = len(blob)
            item["sha256"] = hashlib.sha256(blob).hexdigest()
            with lock:
                done[0] += 1
                if done[0] % 25 == 0:
                    print(f"  downloaded {done[0]}/{len(items)}", flush=True)

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(workers)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return items


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-pages", type=int, default=2500)
    ap.add_argument("--workers", type=int, default=12)
    ap.add_argument("--reuse-crawl", action="store_true",
                    help="skip the crawl and re-download from data/sources.json")
    args = ap.parse_args()

    if args.reuse_crawl and os.path.exists(SOURCES):
        pdfs = {e["url"]: e for e in json.load(open(SOURCES, encoding="utf-8"))}
    else:
        print("crawling cassation.tn ...")
        pdfs = crawl(args.max_pages, args.workers)

    print("downloading ...")
    items = download(pdfs, args.workers)
    items.sort(key=lambda e: e["url"])
    os.makedirs(os.path.dirname(SOURCES), exist_ok=True)
    with open(SOURCES, "w", encoding="utf-8") as fh:
        json.dump(items, fh, ensure_ascii=False, indent=1)
    ok = sum(1 for e in items if e.get("file"))
    print(f"done: {ok}/{len(items)} PDFs in {os.path.relpath(PDF_DIR, ROOT)}")
    missing = [e for e in items if not e.get("file")]
    if missing:
        print(f"{len(missing)} links published by the court are dead:")
        for e in missing:
            print(f"  {e['url']} ({e.get('error')})")


if __name__ == "__main__":
    main()
