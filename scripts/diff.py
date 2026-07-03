"""Detect and apply package data changes from the staged scrape.

A package's "translation key" is its description_en field. If description_en
changes, or if the matching ZH file is missing/stale, we need to re-translate.
Other EN fields update without triggering re-translation.

Changes are categorized:
  - added:      new slug in scrape, not in data/en/
  - modified:   same slug, but description_en changed
  - removed:    slug in data/en/ but not in this scrape (soft-delete)
  - metadata_changed: same description_en, but non-translation EN fields changed
  - unchanged:  same slug, same description_en (only metadata may differ)

For added/modified/metadata_changed packages, we copy staged EN into data/en/.
For removed packages, we move data/en/<slug>.json → data/en/_removed/<slug>.json
(and similarly for data/zh/) so we keep history without showing them in production.

Usage:
  python scripts/diff.py
  python scripts/diff.py --report-only    # just print the diff, don't touch files

Exit codes:
  0 = success (regardless of whether changes were found)
  1 = fatal error

Outputs a JSON report at data/_diff_report.json for translate.py to consume.
"""
import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_EN_DIR = REPO_ROOT / 'data' / 'en'
DATA_NEW_EN_DIR = REPO_ROOT / 'data' / '_scraped' / 'en'
DATA_ZH_DIR = REPO_ROOT / 'data' / 'zh'
REMOVED_EN_DIR = REPO_ROOT / 'data' / 'en' / '_removed'
REMOVED_ZH_DIR = REPO_ROOT / 'data' / 'zh' / '_removed'
DIFF_REPORT_FILE = REPO_ROOT / 'data' / '_diff_report.json'


def slugify(name):
    import re
    s = name.lstrip('@')
    s = s.replace('/', '__')
    s = re.sub(r'[^A-Za-z0-9._\-+]', '_', s)
    return s


def load_existing_en_slugs():
    """Return set of slugs currently in data/en/ (excluding _removed/ subdir)."""
    if not DATA_EN_DIR.exists():
        return set()
    slugs = set()
    for p in DATA_EN_DIR.glob('*.json'):
        if p.name.startswith('_'):
            continue
        slugs.add(p.stem)
    return slugs


def load_new_en_slugs():
    if not DATA_NEW_EN_DIR.exists():
        return set()
    return {p.stem for p in DATA_NEW_EN_DIR.glob('*.json')
            if not p.name.startswith('_')}


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8')


def normalized_en(data):
    return {key: value for key, value in data.items() if key != 'scraped_at'}


def translation_is_current(slug, description_en):
    zh_path = DATA_ZH_DIR / f"{slug}.json"
    if not zh_path.exists():
        return False
    try:
        zh_data = read_json(zh_path)
    except Exception:
        return False
    return (zh_data.get('description_en', '') == description_en
            and bool(zh_data.get('description_zh', '').strip()))


def load_staged_slugs():
    """Return slugs from this scrape, based on staged EN files."""
    return load_new_en_slugs()


def validate_scrape_inputs(staged_slugs):
    if not DATA_NEW_EN_DIR.exists():
        print("FATAL: staged scrape directory missing. Run scrape.py first.",
              file=sys.stderr)
        sys.exit(1)
    if not staged_slugs:
        print("FATAL: no staged EN files found. Run scrape.py first.",
              file=sys.stderr)
        sys.exit(1)


def classify_common_slug(slug):
    old_en = read_json(DATA_EN_DIR / f"{slug}.json")
    new_en = read_json(DATA_NEW_EN_DIR / f"{slug}.json")
    old_desc = old_en.get('description_en', '')
    new_desc = new_en.get('description_en', '')
    if new_desc != old_desc:
        return 'modified'
    if not translation_is_current(slug, new_desc):
        return 'modified'
    if normalized_en(new_en) != normalized_en(old_en):
        return 'metadata_changed'
    return 'unchanged'


def classify_changes(staged_slugs, existing_slugs):
    report = {
        'added': sorted(staged_slugs - existing_slugs),
        'modified': [],
        'metadata_changed': [],
        'removed': sorted(existing_slugs - staged_slugs),
        'unchanged': [],
    }
    for slug in sorted(staged_slugs & existing_slugs):
        category = classify_common_slug(slug)
        report[category].append(slug)
    return report


def build_report(changes, generated_at, staged_slugs, existing_slugs):
    summary = {key: len(value) for key, value in changes.items()}
    summary['total_before'] = len(existing_slugs)
    summary['total_after'] = len(staged_slugs)
    summary['translation_needed'] = summary['added'] + summary['modified']
    summary['publishable_changes'] = (
        summary['added'] + summary['modified'] +
        summary['metadata_changed'] + summary['removed']
    )
    return {'generated_at': generated_at, **changes, 'summary': summary}


def replace_file(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    shutil.copy2(str(src), str(dst))


def move_if_exists(src, dst):
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    shutil.move(str(src), str(dst))


def apply_changes(report):
    for slug in report['added'] + report['modified'] + report['metadata_changed']:
        replace_file(DATA_NEW_EN_DIR / f"{slug}.json", DATA_EN_DIR / f"{slug}.json")

    for slug in report['removed']:
        move_if_exists(DATA_EN_DIR / f"{slug}.json",
                       REMOVED_EN_DIR / f"{slug}.json")
        move_if_exists(DATA_ZH_DIR / f"{slug}.json",
                       REMOVED_ZH_DIR / f"{slug}.json")
    if report['removed']:
        print(f"Soft-deleted {len(report['removed'])} packages (moved to _removed/)")


def print_report(report):
    summary = report['summary']
    print("=" * 60)
    print("DIFF REPORT")
    print("=" * 60)
    print(f"  Before: {summary['total_before']} packages")
    print(f"  After:  {summary['total_after']} packages")
    print(f"  Added:            {summary['added']}")
    print(f"  Modified:         {summary['modified']}")
    print(f"  Metadata changed: {summary['metadata_changed']}")
    print(f"  Removed:          {summary['removed']}")
    print(f"  Unchanged:        {summary['unchanged']}")
    print()
    for key in ('added', 'modified', 'metadata_changed', 'removed'):
        if report[key][:10]:
            print(f"  Sample {key}: {report[key][:10]}")
    print()
    print(f"Report saved to {DIFF_REPORT_FILE}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--report-only', action='store_true',
                    help="Don't modify files, just write the diff report")
    args = ap.parse_args()

    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    staged_slugs = set(load_staged_slugs())
    existing_slugs = load_existing_en_slugs()
    validate_scrape_inputs(staged_slugs)

    changes = classify_changes(staged_slugs, existing_slugs)
    report = build_report(changes, now, staged_slugs, existing_slugs)
    write_json(DIFF_REPORT_FILE, report)
    print_report(report)

    if args.report_only:
        print("--report-only: not modifying files")
        return

    apply_changes(report)


if __name__ == '__main__':
    main()
