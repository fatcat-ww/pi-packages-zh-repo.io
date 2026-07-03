"""Scrape all packages from pi.dev/packages into a staging directory.

This is a pure HTTP scraper — no browser needed. pi.dev server-renders
the package list, so direct requests with ?page=N work fine.

Usage:
  python scripts/scrape.py                  # scrape all pages, write to data/_scraped/en/
  python scripts/scrape.py --max-pages 5    # limit for testing
  python scripts/scrape.py --dry-run        # don't write, just print stats

Output:
  - data/_scraped/en/<slug>.json for each package
  - data/_meta.json updated with last_scraped_at

Exit codes:
  0 = success
  1 = fatal error
"""
import argparse
import json
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: requests not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / 'data'
SCRAPED_EN_DIR = DATA_DIR / '_scraped' / 'en'
META_FILE = REPO_ROOT / 'data' / '_meta.json'

BASE_URL = 'https://pi.dev/packages'
USER_AGENT = 'pi-packages-zh-bot/1.0 (+https://github.com/yourname/pi-packages-zh)'
DEFAULT_DELAY_SECONDS = 0.5
FETCH_TIMEOUT_SECONDS = 30

# Match each <article> with data-package-card="true"
ARTICLE_RE = re.compile(
    r'<article[^>]*data-package-card="true"[^>]*?(?:/>|>.*?</article>)',
    re.IGNORECASE | re.DOTALL,
)
ATTR_RE = re.compile(
    r'data-package-(name|search|types|downloads|date|sort-name)="([^"]*)"',
    re.IGNORECASE,
)
# Match the package link inside the article
LINK_RE = re.compile(r'<a[^>]*href="(/packages/[^"]+)"[^>]*>', re.IGNORECASE)
# Match <p>...</p> blocks
P_RE = re.compile(r'<p[^>]*>([\s\S]*?)</p>', re.IGNORECASE)


def slugify(name):
    s = name.lstrip('@')
    s = s.replace('/', '__')
    s = re.sub(r'[^A-Za-z0-9._\-+]', '_', s)
    return s


def strip_html(s):
    s = re.sub(r'<[^>]+>', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return unescape(s)


def fetch_page(page_num, session, timeout=FETCH_TIMEOUT_SECONDS):
    """Fetch one page and return (status_code, html)."""
    url = f"{BASE_URL}?page={page_num}"
    r = session.get(url, timeout=timeout, headers={'User-Agent': USER_AGENT})
    return r.status_code, r.text


def parse_attrs(article_text):
    attrs = {}
    for match in ATTR_RE.finditer(article_text):
        key = match.group(1).replace('-', '_')
        if key != 'sort_name':
            attrs[key] = unescape(match.group(2))
    return attrs


def parse_int(value):
    try:
        return int(value or '0')
    except ValueError:
        return 0


def find_package_path(article_text):
    match = LINK_RE.search(article_text)
    if not match:
        return ''
    return match.group(1).split('?')[0]


def find_description(article_text):
    desc = ''
    for match in P_RE.finditer(article_text):
        text = strip_html(match.group(1))
        if len(text) > len(desc):
            desc = text
    return desc


def package_from_article(article_text):
    attrs = parse_attrs(article_text)
    name = attrs.get('name', '')
    if not name:
        return None

    path = find_package_path(article_text)
    types_raw = attrs.get('types', '') or ''
    return {
        'name': name,
        'path': path,
        'url': 'https://pi.dev' + path,
        'types': types_raw.strip(),
        'type_list': [t for t in types_raw.split() if t],
        'downloads': parse_int(attrs.get('downloads', '0')),
        'date_ms': parse_int(attrs.get('date', '0')),
        'description_en': find_description(article_text),
    }


def parse_page(html):
    """Extract all package cards from a page's HTML.

    Returns list of dicts with: name, path, types, type_list, downloads, date_ms, description_en.
    """
    packages = []
    for match in ARTICLE_RE.finditer(html):
        package = package_from_article(match.group(0))
        if package:
            packages.append(package)
    return packages


def find_total_pages(html):
    """Extract the last page number from pagination nav."""
    pages = re.findall(r'/packages\?page=(\d+)', html)
    if not pages:
        return None
    return max(int(p) for p in pages)


def utc_now():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def create_session():
    session = requests.Session()
    session.headers.update({
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    return session


def require_packages(page_num, packages):
    if packages:
        return
    print(f"FATAL: page {page_num} produced 0 packages", file=sys.stderr)
    sys.exit(1)


def fetch_all_packages(max_pages, delay):
    session = create_session()
    print("Fetching first page to discover total pages...")
    code, html = fetch_page(1, session)
    if code != 200:
        print(f"FATAL: page 1 returned HTTP {code}", file=sys.stderr)
        sys.exit(1)

    total_pages = find_total_pages(html)
    if total_pages is None:
        print("FATAL: could not discover total pages from pagination", file=sys.stderr)
        sys.exit(1)
    print(f"Total pages: {total_pages}")

    if max_pages > 0:
        total_pages = min(total_pages, max_pages)
        print(f"Limited to {total_pages} pages")

    all_pkgs = parse_page(html)
    require_packages(1, all_pkgs)
    print(f"Page 1: {len(all_pkgs)} packages")

    for page_num in range(2, total_pages + 1):
        time.sleep(delay)
        code, html = fetch_page(page_num, session)
        if code != 200:
            print(f"FATAL: page {page_num} returned HTTP {code}", file=sys.stderr)
            sys.exit(1)
        packages = parse_page(html)
        require_packages(page_num, packages)
        print(f"Page {page_num}: {len(packages)} packages")
        all_pkgs.extend(packages)

    return all_pkgs


def dedupe_packages(packages):
    seen = {}
    for package in packages:
        name = package['name']
        if name not in seen or package['downloads'] > seen[name]['downloads']:
            seen[name] = package
    return list(seen.values())


def package_record(package, scraped_at):
    return {
        'name': package['name'],
        'path': package['path'],
        'url': package['url'],
        'types': package['types'],
        'type_list': package['type_list'],
        'downloads': package['downloads'],
        'date_ms': package['date_ms'],
        'description_en': package['description_en'],
        'scraped_at': scraped_at,
    }


def reset_output_dir(output_dir):
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8')


def write_packages(packages, output_dir, scraped_at):
    reset_output_dir(output_dir)
    for package in packages:
        slug = slugify(package['name'])
        write_json(output_dir / f"{slug}.json", package_record(package, scraped_at))


def write_run_metadata(packages, scraped_at):
    meta = {}
    if META_FILE.exists():
        try:
            meta = json.loads(META_FILE.read_text(encoding='utf-8'))
        except Exception:
            meta = {}
    meta['last_scraped_at'] = scraped_at
    meta['total_packages'] = len(packages)
    meta['source_url'] = BASE_URL
    meta['scraper_version'] = '2.0'
    write_json(META_FILE, meta)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-pages', type=int, default=0, help='Limit pages (0=no limit)')
    ap.add_argument('--dry-run', action='store_true', help="Don't write files")
    ap.add_argument('--delay', type=float, default=DEFAULT_DELAY_SECONDS,
                    help='Delay between requests (s)')
    ap.add_argument('--output-dir', type=Path, default=SCRAPED_EN_DIR,
                    help='Directory for staged EN JSON files')
    args = ap.parse_args()

    all_pkgs = fetch_all_packages(args.max_pages, args.delay)
    unique = dedupe_packages(all_pkgs)
    print(f"\nTotal unique packages: {len(unique)}")

    if args.dry_run:
        print("--dry-run: not writing files")
        return

    now = utc_now()
    write_packages(unique, args.output_dir, now)
    write_run_metadata(unique, now)

    print(f"\nWrote {len(unique)} staged EN files to {args.output_dir}")
    print(f"Updated {META_FILE}")


if __name__ == '__main__':
    main()
