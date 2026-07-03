# Pi 包目录 · 中文翻译版

[![Daily update](https://github.com/{{OWNER}}/pi-packages-zh/actions/workflows/update.yml/badge.svg)](https://github.com/{{OWNER}}/pi-packages-zh/actions/workflows/update.yml)
[![Deploy](https://github.com/{{OWNER}}/pi-packages-zh/actions/workflows/deploy.yml/badge.svg)](https://github.com/{{OWNER}}/pi-packages-zh/actions/workflows/deploy.yml)

将 [pi.dev/packages](https://pi.dev/packages) 上所有 Pi Coding Agent 包的英文简介翻译为中文，提供可搜索、可筛选、可排序的交互式目录页面。

> 🌐 在线访问：<https://{{OWNER}}.github.io/pi-packages-zh/>

## 特性

- **全覆盖**：抓取 pi.dev/packages 全部 96 页（约 4759+ 个包）
- **中文翻译**：每个包简介由 LLM 翻译为简体中文，技术名词保留原文
- **增量更新**：每天自动检测新增/变更/删除的包，只翻译变化部分
- **自动 PR**：检测到变化时自动开 Pull Request，你 review 后合并即部署
- **软删除**：pi.dev 上被删除的包不直接消失，移至 `_removed/` 留痕便于审计
- **交互式页面**：搜索、按类型筛选、按下载量/时间/名称排序、虚拟滚动、深浅色主题

## 工作流架构

```
┌──────────────────────────────────────────────────────────────┐
│  每天 02:00 UTC (10:00 北京时间)                              │
│  GitHub Actions update.yml 触发                                │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  scrape.py           │  HTTP 抓取 pi.dev/packages?page=N
              │  写入 data/_scraped/ │  临时 staging，不覆盖现有数据
              └──────────┬───────────┘
                         │
                         ▼
              ┌──────────────────────┐
              │  diff.py             │  对比 staged EN + 现有 en/zh
              │  生成 _diff_report   │  分类：新增 / 重译 / 元数据 / 删除
              └──────────┬───────────┘
                         │
              ┌──────────┴───────────┐
              │ 无变化？             │
              └────┬─────────────────┘
                   │
        ┌─────YES──┴──NO─────┐
        ▼                    ▼
   退出（不开 PR）   ┌────────────────┐
                    │ translate.py   │  只翻译新增+需重译的包（批量 50 个/次）
                    │ 调用 LLM HTTP API │
                    └────────┬───────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ merge.py       │  合并 en + zh → dist/packages.json
                    └────────┬───────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ build_html.py  │  生成 dist/index.html（嵌入数据）
                    └────────┬───────┘
                             │
                             ▼
                    ┌────────────────┐
                    │ git commit +   │
                    │ push 分支       │
                    │ 开 PR           │
                    └────────┬───────┘
                             │
                  ┌──────────┴──────────┐
                  │ 你 review + 合并    │
                  └──────────┬──────────┘
                             │
                             ▼
                    ┌────────────────────┐
                    │ deploy.yml 触发     │
                    │ 部署到 GitHub Pages │
                    └────────────────────┘
```

## 目录结构

```
pi-packages-zh/
├── .github/workflows/
│   ├── update.yml              # 每日定时 + 手动触发：抓取→翻译→开 PR
│   ├── ci.yml                  # Python 编译、单元测试、静态产物构建
│   └── deploy.yml              # PR 合并后部署 dist/ 到 GitHub Pages
│
├── data/
│   ├── en/                     # 每个包的英文源数据（一包一文件）
│   │   ├── hypabolic__pi-hypa.json
│   │   ├── pi-web-access.json
│   │   ├── _removed/           # pi.dev 上被删除的包归档于此
│   │   └── ... (4759 个文件)
│   ├── zh/                     # 每个包的中文翻译（与 en 一一对应）
│   │   ├── hypabolic__pi-hypa.json
│   │   ├── _removed/
│   │   └── ... (4759 个文件)
│   ├── _meta.json              # 元数据：上次抓取/翻译时间、总数等
│   ├── _scraped/               # 本次抓取 staging（临时，gitignored）
│   └── _diff_report.json       # 本次 diff 报告（临时，gitignored）
│
├── scripts/
│   ├── scrape.py               # HTTP 抓取 pi.dev 全部分页
│   ├── diff.py                 # 检测并应用 新增/重译/元数据/删除
│   ├── translate.py            # 调用 LLM 增量翻译
│   ├── merge.py                # 合并 en + zh → packages.json
│   └── build_html.py           # 生成 index.html
│
├── dist/                       # 部署产物（由 CI 生成，可手动重新生成）
│   ├── index.html              # 嵌入数据的单文件 HTML
│   └── packages.json           # 结构化数据，便于二次开发
│
├── requirements.txt            # Python 依赖
└── README.md
```

## 本地运行

### 一次性初始化（首次 clone 后）

```bash
pip install -r requirements.txt
export LLM_BASE_URL=https://api.astrdark.cyou/v1
export LLM_API_KEY=sk-your_key_here
export LLM_MODEL=glm-4.5-flash

# 抓取 + diff + 翻译 + 合并 + 生成 HTML（全套）
python scripts/scrape.py
python scripts/diff.py
python scripts/translate.py
python scripts/merge.py
python scripts/build_html.py

# 直接打开 dist/index.html 查看结果
```

### 仅重新生成 HTML（不抓取新数据）

如果你只改了 `build_html.py` 或想刷新 HTML：

```bash
python scripts/merge.py
python scripts/build_html.py
```

### 翻译单个包

```bash
python scripts/translate.py --slug hypabolic__pi-hypa
```

### 限制抓取页数（测试用）

```bash
python scripts/scrape.py --max-pages 2 --dry-run
```

## Slug 命名规则

包名 → 文件名转换：

| 包名 | Slug |
|---|---|
| `pi-web-access` | `pi-web-access` |
| `@hypabolic/pi-hypa` | `hypabolic__pi-hypa` |
| `@gotgenes/pi-subagents` | `gotgenes__pi-subagents` |

规则：去掉开头的 `@`，将 `/` 替换为 `__`（双下划线表示 scope 边界）。

## 数据文件格式

### `data/en/<slug>.json`

```json
{
  "name": "@hypabolic/pi-hypa",
  "path": "/packages/@hypabolic/pi-hypa",
  "url": "https://pi.dev/packages/@hypabolic/pi-hypa",
  "types": "",
  "type_list": [],
  "downloads": 204816,
  "date_ms": 1782089746134,
  "description_en": "Pi extension that keeps noisy tool output...",
  "scraped_at": "2026-07-03T16:04:28Z"
}
```

### `data/zh/<slug>.json`

```json
{
  "name": "@hypabolic/pi-hypa",
  "description_en": "Pi extension that keeps noisy tool output...",
  "description_zh": "Pi 扩展，将嘈杂的工具输出排除在上下文窗口之外...",
  "translated_at": "2026-07-03T16:04:28Z"
}
```

`description_en` 字段同时存在于 EN 和 ZH 文件中，作为翻译键——只有它变化时才会重新翻译。

## 配置 GitHub Actions

### 1. 设置 LLM Secrets

仓库 Settings → Secrets and variables → Actions → New repository secret：

- Name: `LLM_BASE_URL`
- Value: `https://api.astrdark.cyou/v1`

- Name: `LLM_API_KEY`
- Value: 你的 sk

### 2. 启用 GitHub Pages

仓库 Settings → Pages → Build and deployment → Source: **GitHub Actions**

（首次合并 PR 后 `deploy.yml` 会自动部署。）

### 3. 修改 cron 时间（可选）

编辑 `.github/workflows/update.yml`，修改 `cron: '0 2 * * *'` 为你期望的时间。
当前为每天 UTC 02:00（北京时间 10:00）。

### 4. 手动触发更新

Actions 标签页 → `Daily update` workflow → Run workflow 按钮。

## 增量更新机制详解

### 何为"变更"？

只有当包的 `description_en` 字段变化时，才算"变更"，需要重新翻译。

其他字段变化（如 `downloads`、`date_ms`、`types`）归为元数据更新：会更新 `data/en/` 和 `dist/`，但不会重新翻译。

### 何为"删除"？

如果某个 slug 在 pi.dev 上不存在了（不在本次 staged 抓取结果中），但 `data/en/<slug>.json` 仍然存在，则判定为删除。

删除的包会被移动到 `data/en/_removed/` 和 `data/zh/_removed/`，从生产数据中排除但保留历史。

### 何为"新增"？

slug 在本次 staged 抓取结果中，但 `data/en/<slug>.json` 不存在。

新增的包会自动调用 LLM 翻译。

## License

数据来源于 [pi.dev](https://pi.dev)，版权归原作者所有。翻译由 AI 生成，仅供参考。

本仓库的脚本和架构代码采用 MIT 协议。
