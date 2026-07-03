import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import scripts.diff as diff_script
import scripts.llm_client as llm_client
import scripts.merge as merge_script
import scripts.pr_body as pr_body_script
import scripts.translate as translate_script


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n',
                    encoding='utf-8')


def en_record(slug, desc, downloads=1, scraped_at='old'):
    return {
        'name': slug,
        'path': f'/packages/{slug}',
        'url': f'https://pi.dev/packages/{slug}',
        'types': '',
        'type_list': [],
        'downloads': downloads,
        'date_ms': 0,
        'description_en': desc,
        'scraped_at': scraped_at,
    }


def zh_record(slug, desc, zh='中文'):
    return {
        'name': slug,
        'description_en': desc,
        'description_zh': zh,
        'translated_at': 'old',
    }


class DiffTests(unittest.TestCase):
    def test_classifies_and_applies_staged_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / 'data'
            old_en = data / 'en'
            new_en = data / '_scraped' / 'en'
            zh_dir = data / 'zh'

            write_json(old_en / 'same.json', en_record('same', 'same'))
            write_json(old_en / 'changed-desc.json',
                       en_record('changed-desc', 'old desc'))
            write_json(old_en / 'changed-meta.json',
                       en_record('changed-meta', 'meta desc', downloads=1))
            write_json(old_en / 'removed.json', en_record('removed', 'gone'))
            for slug, desc in (
                ('same', 'same'),
                ('changed-desc', 'old desc'),
                ('changed-meta', 'meta desc'),
                ('removed', 'gone'),
            ):
                write_json(zh_dir / f'{slug}.json', zh_record(slug, desc))

            write_json(new_en / 'same.json',
                       en_record('same', 'same', scraped_at='new'))
            write_json(new_en / 'changed-desc.json',
                       en_record('changed-desc', 'new desc', scraped_at='new'))
            write_json(new_en / 'changed-meta.json',
                       en_record('changed-meta', 'meta desc', downloads=2,
                                 scraped_at='new'))
            write_json(new_en / 'added.json',
                       en_record('added', 'added desc', scraped_at='new'))
            attrs = {
                'DATA_EN_DIR': old_en,
                'DATA_NEW_EN_DIR': new_en,
                'DATA_ZH_DIR': zh_dir,
                'REMOVED_EN_DIR': old_en / '_removed',
                'REMOVED_ZH_DIR': zh_dir / '_removed',
                'DIFF_REPORT_FILE': data / '_diff_report.json',
            }
            with patch.multiple(diff_script, **attrs), \
                    patch.object(sys, 'argv', ['diff.py']), \
                    contextlib.redirect_stdout(io.StringIO()):
                diff_script.main()

            report = json.loads((data / '_diff_report.json').read_text())
            self.assertEqual(report['summary']['added'], 1)
            self.assertEqual(report['summary']['modified'], 1)
            self.assertEqual(report['summary']['metadata_changed'], 1)
            self.assertEqual(report['summary']['removed'], 1)
            self.assertEqual(report['summary']['unchanged'], 1)
            self.assertTrue((old_en / 'added.json').exists())
            self.assertEqual(json.loads((old_en / 'changed-meta.json').read_text())['downloads'], 2)
            self.assertEqual(json.loads((old_en / 'same.json').read_text())['scraped_at'], 'old')
            self.assertTrue((old_en / '_removed' / 'removed.json').exists())
            self.assertTrue((zh_dir / '_removed' / 'removed.json').exists())


class TranslateTests(unittest.TestCase):
    def test_call_llm_uses_siliconflow_http_api(self):
        calls = []

        class FakeResponse:
            status_code = 200
            text = '{"ok": true}'
            headers = {'content-type': 'application/json'}

            def json(self):
                return {'choices': [{'message': {'content': '[{"i":0,"zh":"一"}]'}}]}

        def fake_post(url, headers, json, timeout):
            calls.append((url, headers, json, timeout))
            return FakeResponse()

        env = {'SILICONFLOW_API_KEY': 'sk-test'}
        with patch.dict(os.environ, env, clear=False), \
                patch.object(llm_client.requests, 'post', fake_post):
            content, err = llm_client.call_llm('prompt', 'system', timeout=12)

        self.assertIsNone(err)
        self.assertEqual(content, '[{"i":0,"zh":"一"}]')
        url, headers, payload, timeout = calls[0]
        self.assertEqual(url, 'https://api.siliconflow.cn/v1/chat/completions')
        self.assertEqual(headers['Authorization'], 'Bearer sk-test')
        self.assertEqual(payload['model'], 'deepseek-ai/DeepSeek-V4-Flash')
        self.assertEqual(payload['messages'][0]['content'], 'system')
        self.assertEqual(payload['messages'][1]['content'], 'prompt')
        self.assertIs(payload['enable_thinking'], False)
        self.assertEqual(timeout, 12)

    def test_call_llm_reports_cloudflare_challenge_as_fatal(self):
        class FakeResponse:
            status_code = 403
            text = '<!DOCTYPE html><title>Just a moment...</title>'
            headers = {'content-type': 'text/html; charset=UTF-8'}

        err = llm_client.format_http_error(FakeResponse())
        self.assertIn('FATAL: LLM endpoint returned a Cloudflare challenge', err)

    def test_rejects_partial_translation_array(self):
        arr, err = translate_script.parse_translation_array(
            '[{"i": 0, "zh": "一"}]', expected_count=2)
        self.assertIsNone(arr)
        self.assertIn('Expected 2 translations', err)

    def test_rejects_duplicate_translation_index(self):
        arr = [{'i': 0, 'zh': '一'}, {'i': 0, 'zh': '二'}]
        translations, err = translate_script.validate_translation_items(arr, range(2))
        self.assertIsNone(translations)
        self.assertIn('Duplicate translation index', err)

    def test_filters_already_translated_slugs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            en_dir = root / 'data' / 'en'
            zh_dir = root / 'data' / 'zh'
            write_json(en_dir / 'done.json', en_record('done', 'same desc'))
            write_json(zh_dir / 'done.json', zh_record('done', 'same desc'))
            write_json(en_dir / 'pending.json', en_record('pending', 'new desc'))
            write_json(zh_dir / 'pending.json', zh_record('pending', 'old desc'))

            attrs = {'DATA_EN_DIR': en_dir, 'DATA_ZH_DIR': zh_dir}
            with patch.multiple(translate_script, **attrs), \
                    contextlib.redirect_stdout(io.StringIO()):
                pending = translate_script.filter_untranslated_slugs(
                    ['done', 'pending', 'missing'])

            self.assertEqual(pending, ['pending', 'missing'])


class MergeTests(unittest.TestCase):
    def test_merge_fails_when_translation_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            en_dir = root / 'data' / 'en'
            zh_dir = root / 'data' / 'zh'
            write_json(en_dir / 'pkg.json', en_record('pkg', 'desc'))
            with patch.multiple(merge_script, DATA_EN_DIR=en_dir, DATA_ZH_DIR=zh_dir):
                with self.assertRaises(ValueError):
                    merge_script.build_packages()


class PrBodyTests(unittest.TestCase):
    def test_pr_body_uses_plain_markdown_backticks(self):
        report = {
            'added': ['a'],
            'modified': ['b'],
            'metadata_changed': ['c'],
            'removed': ['d'],
            'summary': {
                'added': 1,
                'modified': 1,
                'metadata_changed': 1,
                'removed': 1,
                'unchanged': 2,
                'total_before': 4,
                'total_after': 4,
                'translation_needed': 2,
            },
        }
        body = pr_body_script.format_pr_body(report)
        self.assertIn('- 新增的包: `a`', body)
        self.assertNotIn('\\`', body)
        self.assertNotIn("`'", body)


if __name__ == '__main__':
    unittest.main()
