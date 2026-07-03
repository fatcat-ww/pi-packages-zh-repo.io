"""Translate packages listed as added/modified in data/_diff_report.json."""
import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from zai import ZhipuAiClient
except ImportError:
    ZhipuAiClient = None

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_EN_DIR = REPO_ROOT / 'data' / 'en'
DATA_ZH_DIR = REPO_ROOT / 'data' / 'zh'
DIFF_REPORT_FILE = REPO_ROOT / 'data' / '_diff_report.json'
META_FILE = REPO_ROOT / 'data' / '_meta.json'

BATCH_SIZE = 50
LLM_TIMEOUT = 180  # seconds per call
DEFAULT_LLM_BASE_URL = 'https://open.bigmodel.cn/api/paas/v4'
DEFAULT_LLM_MODEL = 'glm-4.7-flash'
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 3
BATCH_DELAY_SECONDS = 1.0


def call_llm(prompt, system_prompt, timeout=LLM_TIMEOUT):
    """Call BigModel through the official Python SDK."""
    client = create_llm_client(timeout)
    try:
        response = client.chat.completions.create(**build_llm_payload(
            prompt, system_prompt))
    except Exception as exc:
        return None, format_llm_exception(exc)
    return extract_llm_content(response)


def create_llm_client(timeout):
    if ZhipuAiClient is None:
        raise RuntimeError("zai-sdk is required. Install with: pip install zai-sdk")
    kwargs = {
        'api_key': get_api_key(),
        'timeout': timeout,
    }
    base_url = (
        os.environ.get('ZAI_BASE_URL', '').strip()
        or os.environ.get('LLM_BASE_URL', '').strip()
        or DEFAULT_LLM_BASE_URL
    )
    kwargs['base_url'] = base_url.rstrip('/') + '/'
    return ZhipuAiClient(**kwargs)


def get_api_key():
    value = (
        os.environ.get('ZAI_API_KEY', '').strip()
        or os.environ.get('LLM_API_KEY', '').strip()
    )
    if not value:
        raise RuntimeError("ZAI_API_KEY or LLM_API_KEY is required")
    return value


def build_llm_payload(prompt, system_prompt):
    return {
        'model': get_model_name(),
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': prompt},
        ],
        'temperature': 0.2,
        'thinking': {'type': os.environ.get('LLM_THINKING', 'disabled')},
    }


def get_model_name():
    return (
        os.environ.get('ZAI_MODEL', '').strip()
        or os.environ.get('LLM_MODEL', '').strip()
        or DEFAULT_LLM_MODEL
    )


def extract_llm_content(response):
    choices = getattr(response, 'choices', None)
    if not choices:
        return None, "LLM response missing choices"
    content = getattr(getattr(choices[0], 'message', None), 'content', '')
    if not content:
        return None, "LLM response missing message content"
    return content, None


def format_llm_exception(exc):
    text = str(exc)
    if is_cloudflare_challenge_text(text):
        return (
            "FATAL: LLM endpoint returned a Cloudflare challenge page. "
            "Use an API endpoint that accepts non-browser POST requests, or "
            "disable Cloudflare challenge/WAF rules for /v1/chat/completions."
        )
    return f"LLM request failed: {text[:300]}"


def is_cloudflare_challenge_text(text):
    return 'just a moment' in text.lower()


def parse_translation_array(content, expected_count):
    content = content.strip()
    content = re.sub(r'^```(?:json)?\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    arr_start = content.find('[')
    arr_end = content.rfind(']')
    if arr_start < 0 or arr_end <= arr_start:
        return None, "No JSON array found"
    try:
        arr = json.loads(content[arr_start:arr_end + 1])
    except json.JSONDecodeError as e:
        return None, f"JSON parse error: {e}"
    if not isinstance(arr, list):
        return None, "Not a list"
    if len(arr) != expected_count:
        return None, f"Expected {expected_count} translations, got {len(arr)}"
    return arr, None


def validate_translation_items(arr, expected_indexes):
    translations = {}
    expected = set(expected_indexes)
    for item in arr:
        if not isinstance(item, dict):
            return None, "Translation item is not an object"
        index = item.get('i')
        zh = str(item.get('zh', '')).strip()
        if index not in expected:
            return None, f"Unexpected translation index: {index}"
        if index in translations:
            return None, f"Duplicate translation index: {index}"
        if not zh:
            return None, f"Empty translation for index: {index}"
        translations[index] = zh
    missing = sorted(expected - set(translations))
    if missing:
        return None, f"Missing translation indexes: {missing}"
    return translations, None


def build_batch_prompt(items):
    return f"""请将下面 {len(items)} 个 Pi Coding Agent 包的英文简介翻译为简体中文。

要求：
1. 仅翻译 description 字段，不要翻译包名（name 保持原样）
2. 技术名词保留原文，例如：MCP (Model Context Protocol)、Claude Code、Gemini CLI、Pi、GitHub、YouTube、PDF、OpenAI、TTS、SDD/OpenSpec、TDD、FTS5、CLI、TUI、API、JSON、YAML、SVG、HTML、CSS 等专有名词不译
3. 命令行命令、代码、配置项、文件名保留原文，例如 /rewind、/btw、/skill、package.json、AGENTS.md 等
4. 译文要自然流畅、符合中文技术文档风格，准确传达原意；保持简洁，不要过度解释
5. 严格输出 JSON 数组，每个元素为 {{"i": <编号>, "zh": "<中文译文>"}}
6. 不要输出任何解释、Markdown 代码块标记(```)、前后缀说明，只输出纯 JSON 数组，第一个字符必须是 [

输入数据（JSON）：
{json.dumps(items, ensure_ascii=False, indent=2)}
"""


def load_diff():
    if not DIFF_REPORT_FILE.exists():
        print(f"ERROR: {DIFF_REPORT_FILE} not found. Run diff.py first.", file=sys.stderr)
        sys.exit(1)
    return json.loads(DIFF_REPORT_FILE.read_text(encoding='utf-8'))


def get_slugs_to_translate(args):
    if args.slug:
        print(f"Translating single slug: {args.slug}")
        return filter_untranslated_slugs([args.slug])
    diff = load_diff()
    slugs = list(diff.get('added', [])) + list(diff.get('modified', []))
    print(f"Diff: {len(diff.get('added', []))} added, "
          f"{len(diff.get('modified', []))} modified, "
          f"{len(diff.get('removed', []))} removed")
    return filter_untranslated_slugs(slugs)


def read_package_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def is_already_translated(slug):
    en_path = DATA_EN_DIR / f"{slug}.json"
    zh_path = DATA_ZH_DIR / f"{slug}.json"
    if not en_path.exists() or not zh_path.exists():
        return False
    try:
        en_data = read_package_json(en_path)
        zh_data = read_package_json(zh_path)
    except Exception:
        return False
    return (
        zh_data.get('description_en', '') == en_data.get('description_en', '')
        and bool(str(zh_data.get('description_zh', '')).strip())
    )


def filter_untranslated_slugs(slugs):
    skipped = [slug for slug in slugs if is_already_translated(slug)]
    skipped_set = set(skipped)
    pending = [slug for slug in slugs if slug not in skipped_set]
    if skipped:
        print(f"Already translated: {len(skipped)} packages skipped")
    print(f"To translate: {len(pending)} packages")
    return pending


def require_llm_config(slugs_to_translate):
    if not slugs_to_translate:
        return
    if not (os.environ.get('ZAI_API_KEY') or os.environ.get('LLM_API_KEY')):
        print("ERROR: ZAI_API_KEY or LLM_API_KEY required when translation is needed",
              file=sys.stderr)
        sys.exit(1)


def build_batches(slugs_to_translate, max_batches):
    batches = [slugs_to_translate[i:i + BATCH_SIZE]
               for i in range(0, len(slugs_to_translate), BATCH_SIZE)]
    if max_batches > 0:
        batches = batches[:max_batches]
        print(f"Limited to {len(batches)} batches")
    return batches


def build_batch_items(batch_slugs):
    items = []
    slug_to_en = {}
    for index, slug in enumerate(batch_slugs):
        en_path = DATA_EN_DIR / f"{slug}.json"
        if not en_path.exists():
            raise FileNotFoundError(f"EN file missing for slug={slug}")
        en_data = read_package_json(en_path)
        slug_to_en[slug] = en_data
        items.append({
            'i': index,
            'name': en_data['name'],
            'desc': en_data.get('description_en', ''),
        })
    return items, slug_to_en


def write_translations(batch_slugs, slug_to_en, translations, translated_at):
    DATA_ZH_DIR.mkdir(parents=True, exist_ok=True)
    for index, slug in enumerate(batch_slugs):
        en_data = slug_to_en[slug]
        zh_data = {
            'name': en_data['name'],
            'description_en': en_data.get('description_en', ''),
            'description_zh': translations[index],
            'translated_at': translated_at,
        }
        zh_path = DATA_ZH_DIR / f"{slug}.json"
        zh_path.write_text(
            json.dumps(zh_data, ensure_ascii=False, indent=2) + '\n',
            encoding='utf-8'
        )


def run_batch(batch_idx, batch_count, batch_slugs, translated_at, system_prompt):
    items, slug_to_en = build_batch_items(batch_slugs)
    prompt = build_batch_prompt(items)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        content, err = call_llm(prompt, system_prompt)
        if err:
            print(f"  Batch {batch_idx}/{batch_count} attempt {attempt} ERROR: {err}",
                  flush=True)
            if err.startswith('FATAL:'):
                raise RuntimeError(err)
        else:
            arr, perr = parse_translation_array(content, len(items))
            translations, verr = (None, perr)
            if arr is not None:
                translations, verr = validate_translation_items(
                    arr, range(len(items)))
            if translations is not None:
                write_translations(batch_slugs, slug_to_en, translations,
                                   translated_at)
                print(f"  Batch {batch_idx}/{batch_count} OK: saved {len(items)}/{len(items)}",
                      flush=True)
                return len(items)
            print(f"  Batch {batch_idx}/{batch_count} attempt {attempt} PARSE ERROR: {verr}",
                  flush=True)
            print(f"    First 300 chars: {content[:300]}", flush=True)
        if attempt < MAX_ATTEMPTS:
            time.sleep(RETRY_DELAY_SECONDS)
    raise RuntimeError(f"Batch {batch_idx}/{batch_count} failed after {MAX_ATTEMPTS} attempts")


def update_meta(translated_at):
    if META_FILE.exists():
        meta = json.loads(META_FILE.read_text(encoding='utf-8'))
    else:
        meta = {}
    meta['last_translated_at'] = translated_at
    meta['total_translated'] = sum(1 for _ in DATA_ZH_DIR.glob('*.json'))
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n',
                         encoding='utf-8')
    return meta['total_translated']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--max-batches', type=int, default=0, help='Limit batches (0=no limit)')
    ap.add_argument('--slug', help='Translate one specific slug (ignores diff report)')
    args = ap.parse_args()

    system_prompt = ("You are a professional technical translator. You translate English "
                     "software/package descriptions into fluent, accurate Simplified Chinese "
                     "suitable for developer documentation. You always follow output format "
                     "instructions exactly.")

    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    slugs_to_translate = get_slugs_to_translate(args)

    if not slugs_to_translate:
        print("Nothing to translate.")
        update_meta(now)
        return

    require_llm_config(slugs_to_translate)
    batches = build_batches(slugs_to_translate, args.max_batches)

    total_done = 0
    try:
        for batch_idx, batch_slugs in enumerate(batches, 1):
            total_done += run_batch(batch_idx, len(batches), batch_slugs,
                                    now, system_prompt)
            time.sleep(BATCH_DELAY_SECONDS)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

    translated_count = update_meta(now)

    print()
    print(f"Translation complete: {total_done} done, 0 failed")
    print(f"Total translated packages now: {translated_count}")


if __name__ == '__main__':
    main()
