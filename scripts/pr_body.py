"""Build the auto-update pull request body from data/_diff_report.json."""
import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DIFF_REPORT_FILE = REPO_ROOT / 'data' / '_diff_report.json'
PREVIEW_LIMIT = 20


def preview(names):
    if not names:
        return '-'
    return '`' + ', '.join(names[:PREVIEW_LIMIT]) + '`'


def format_pr_body(report):
    summary = report['summary']
    return f"""## Pi 包目录每日更新

| 类别 | 数量 |
|---|---:|
| 新增 | {summary['added']} |
| 需重译 | {summary['modified']} |
| 元数据变更 | {summary.get('metadata_changed', 0)} |
| 删除 | {summary['removed']} |
| 未变 | {summary['unchanged']} |

- 更新前: {summary['total_before']} 个包
- 更新后: {summary['total_after']} 个包
- 需调用翻译: {summary.get('translation_needed', 0)} 个包

### 详情
- 新增的包: {preview(report.get('added', []))}
- 需重译的包: {preview(report.get('modified', []))}
- 元数据变更的包: {preview(report.get('metadata_changed', []))}
- 删除的包: {preview(report.get('removed', []))}

完整 diff 报告见本次 workflow run 的 Actions Summary。

---
此 PR 由 GitHub Actions 自动生成。合并后会自动部署到 GitHub Pages。
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(DIFF_REPORT_FILE.read_text(encoding='utf-8'))
    args.output.write_text(format_pr_body(report), encoding='utf-8')


if __name__ == '__main__':
    main()
