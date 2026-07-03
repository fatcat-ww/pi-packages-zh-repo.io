"""Merge data/en/*.json + data/zh/*.json into a single dist/packages.json.

Output schema per package:
  {
    "name", "path", "url", "types", "type_list",
    "downloads", "date_ms", "description_en", "description_zh"
  }

Sorted by downloads desc (matches the default "Most downloads" sort on the site).

Usage:
  python scripts/merge.py
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_EN_DIR = REPO_ROOT / 'data' / 'en'
DATA_ZH_DIR = REPO_ROOT / 'data' / 'zh'
DIST_DIR = REPO_ROOT / 'dist'
OUT_FILE = DIST_DIR / 'packages.json'


def load_translation(slug):
    zh_path = DATA_ZH_DIR / f"{slug}.json"
    if not zh_path.exists():
        raise ValueError(f"ZH file missing for slug={slug}")
    zh_data = json.loads(zh_path.read_text(encoding='utf-8'))
    zh = zh_data.get('description_zh', '').strip()
    if not zh:
        raise ValueError(f"ZH translation empty for slug={slug}")
    return zh


def package_record(en_path):
    en = json.loads(en_path.read_text(encoding='utf-8'))
    slug = en_path.stem
    return {
        'name': en['name'],
        'path': en.get('path', ''),
        'url': en.get('url', 'https://pi.dev' + en.get('path', '')),
        'types': en.get('types', ''),
        'type_list': en.get('type_list', []),
        'downloads': en.get('downloads', 0),
        'date_ms': en.get('date_ms', 0),
        'description_en': en.get('description_en', ''),
        'description_zh': load_translation(slug),
    }


def build_packages():
    en_files = sorted(p for p in DATA_EN_DIR.glob('*.json')
                      if not p.name.startswith('_'))
    print(f"Reading {len(en_files)} EN files...")
    packages = [package_record(en_path) for en_path in en_files]
    packages.sort(key=lambda x: -x.get('downloads', 0))
    return packages


def main():
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    try:
        packages = build_packages()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(packages, f, ensure_ascii=False, indent=2)
        f.write('\n')

    size = OUT_FILE.stat().st_size
    print(f"\nWrote {len(packages)} packages to {OUT_FILE}")
    print(f"Size: {size:,} bytes ({size / 1024:.1f} KB)")

    print("\nTop 5 by downloads:")
    for p in packages[:5]:
        print(f"  {p['downloads']:>7}  {p['name']}")


if __name__ == '__main__':
    main()
