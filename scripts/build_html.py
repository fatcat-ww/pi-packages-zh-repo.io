"""Generate dist/index.html with packages.json data embedded inline.

We embed the JSON directly into the HTML so the page works with file:// too.
Run after merge.py.

Usage:
  python scripts/build_html.py
"""
import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGES_JSON = REPO_ROOT / 'dist' / 'packages.json'
OUT_HTML = REPO_ROOT / 'dist' / 'index.html'

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pi 包目录 · 中文翻译版</title>
<meta name="description" content="Pi Coding Agent 全部包的中文翻译目录，支持按类型筛选和按下载量排序。">
<style>
  :root {
    --bg: #fafafa; --surface: #ffffff; --border: #e5e7eb;
    --text: #18181b; --text-2: #71717a;
    --accent: #6366f1; --accent-weak: rgba(99, 102, 241, 0.12);
    --shadow: 0 1px 2px rgba(0,0,0,0.04), 0 4px 12px rgba(0,0,0,0.04);
    --shadow-hover: 0 4px 8px rgba(0,0,0,0.06), 0 8px 24px rgba(0,0,0,0.08);
  }
  :root[data-theme="dark"] {
    --bg: #0a0a0a; --surface: #18181b; --border: #27272a;
    --text: #fafafa; --text-2: #a1a1aa;
    --accent: #818cf8; --accent-weak: rgba(129, 140, 248, 0.16);
    --shadow: 0 1px 2px rgba(0,0,0,0.4), 0 4px 12px rgba(0,0,0,0.3);
    --shadow-hover: 0 4px 8px rgba(0,0,0,0.5), 0 8px 24px rgba(0,0,0,0.4);
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
      "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 14px; line-height: 1.55; -webkit-font-smoothing: antialiased;
    min-height: 100vh;
  }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .container { max-width: 1400px; margin: 0 auto; padding: 0 20px; }
  .page-header { padding: 32px 0 20px; border-bottom: 1px solid var(--border); margin-bottom: 20px; }
  .page-header h1 { margin: 0 0 6px; font-size: 28px; font-weight: 700; letter-spacing: -0.01em; }
  .page-header .subtitle { color: var(--text-2); font-size: 14px; }
  .page-header .subtitle a { color: var(--text-2); }
  .page-header .subtitle a:hover { color: var(--accent); }
  .action-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 16px; }
  .action-bar .grow { flex: 1 1 280px; }
  .input, .select {
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    padding: 9px 12px; border-radius: 8px; font: inherit; font-size: 14px; width: 100%;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .input:focus, .select:focus {
    outline: none; border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-weak);
  }
  .select { cursor: pointer; padding-right: 30px; }
  .select-wrap { position: relative; flex: 0 0 auto; }
  .select-wrap::after {
    content: ""; position: absolute; right: 12px; top: 50%; transform: translateY(-50%);
    width: 0; height: 0; border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid var(--text-2); pointer-events: none;
  }
  .theme-toggle {
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    padding: 9px 14px; border-radius: 8px; cursor: pointer; font: inherit; flex: 0 0 auto;
  }
  .theme-toggle:hover { border-color: var(--accent); }
  .stats {
    color: var(--text-2); font-size: 13px; margin-bottom: 18px;
    display: flex; flex-wrap: wrap; gap: 14px;
  }
  .stats b { color: var(--text); font-weight: 600; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 14px; }
  @media (max-width: 640px) { .grid { grid-template-columns: 1fr; } }
  .card {
    background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px; display: flex; flex-direction: column; gap: 10px;
    transition: transform 0.15s, box-shadow 0.15s, border-color 0.15s;
    box-shadow: var(--shadow); text-decoration: none; color: inherit; height: 100%;
  }
  .card:hover {
    transform: translateY(-2px); box-shadow: var(--shadow-hover);
    border-color: var(--accent); text-decoration: none;
  }
  .card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
  .card-name {
    font-family: ui-monospace, "SF Mono", "Cascadia Mono", Menlo, Consolas, monospace;
    font-size: 14px; font-weight: 600; color: var(--accent);
    word-break: break-all; line-height: 1.4;
  }
  .card-name:hover { text-decoration: underline; }
  .card-badges { display: flex; flex-wrap: wrap; gap: 4px; flex: 0 0 auto; }
  .badge {
    font-size: 11px; padding: 2px 7px; border-radius: 999px;
    background: var(--accent-weak); color: var(--accent); white-space: nowrap; font-weight: 500;
  }
  .badge.uncat { background: rgba(113, 113, 122, 0.12); color: var(--text-2); }
  .card-meta { display: flex; gap: 12px; color: var(--text-2); font-size: 12px; align-items: center; }
  .card-meta .dl { color: var(--text); font-weight: 500; }
  .card-desc {
    color: var(--text); font-size: 13px; line-height: 1.55;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
  }
  .card-foot { margin-top: auto; font-size: 12px; color: var(--text-2); }
  .card-foot a { font-weight: 500; }
  .empty { text-align: center; padding: 60px 20px; color: var(--text-2); }
  .empty button {
    margin-top: 14px; padding: 8px 16px; background: var(--accent); color: white;
    border: none; border-radius: 8px; cursor: pointer; font: inherit;
  }
  .sentinel {
    height: 60px; display: flex; align-items: center; justify-content: center;
    color: var(--text-2); font-size: 13px; grid-column: 1 / -1; margin-top: 10px;
  }
  .sentinel.loading-more::before {
    content: ""; display: inline-block; width: 14px; height: 14px;
    border: 2px solid var(--border); border-top-color: var(--accent);
    border-radius: 50%; animation: spin 0.8s linear infinite; margin-right: 8px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .page-footer {
    margin-top: 40px; padding: 20px 0 30px; border-top: 1px solid var(--border);
    color: var(--text-2); font-size: 12px; text-align: center;
  }
  .page-footer a { color: var(--text-2); }
  .page-footer a:hover { color: var(--accent); }
</style>
</head>
<body>
<div class="container">
  <header class="page-header">
    <h1>Pi 包目录 · 中文翻译版</h1>
    <div class="subtitle" id="subtitle">数据来源 <a href="https://pi.dev/packages" target="_blank" rel="noopener noreferrer">pi.dev/packages</a></div>
  </header>
  <section class="action-bar" id="actionBar" style="visibility:hidden">
    <input id="search" class="input grow" type="search" placeholder="筛选包名或描述…" autocomplete="off" aria-label="筛选包名或描述">
    <div class="select-wrap">
      <select id="typeFilter" class="select" aria-label="按类型筛选">
        <option value="all">类型：所有类型</option>
        <option value="extension">类型：extension</option>
        <option value="skill">类型：skill</option>
        <option value="theme">类型：theme</option>
        <option value="prompt">类型：prompt</option>
        <option value="uncategorized">类型：未分类</option>
      </select>
    </div>
    <div class="select-wrap">
      <select id="sort" class="select" aria-label="排序方式">
        <option value="downloads">排序：最多下载</option>
        <option value="recent">排序：最近发布</option>
        <option value="name">排序：名称 A-Z</option>
      </select>
    </div>
    <button id="themeToggle" class="theme-toggle" type="button" aria-label="切换主题">🌙 深色</button>
  </section>
  <section class="stats" id="stats" style="visibility:hidden">
    <span>共 <b id="statTotal">—</b> 个包</span>
    <span>显示 <b id="statShown">—</b> 个</span>
    <span>总下载量 <b id="statDownloads">—</b></span>
  </section>
  <main id="main"></main>
  <footer class="page-footer">
    数据来源：<a href="https://pi.dev/packages" target="_blank" rel="noopener noreferrer">pi.dev/packages</a>
    · 中文翻译由 AI 生成，仅供参考
    · 点击包名或"查看原页详情"跳转至 pi.dev 原页面
  </footer>
</div>
<script>
//__PACKAGES_DATA__//
(function () {
  "use strict";
  var PACKAGES = window.__PACKAGES_DATA__ || [];
  var FILTERED = [];
  var RENDERED = 0;
  var PAGE_SIZE = 60;
  var searchTimer = null;
  var loadSentinel = null;

  var els = {
    subtitle:    document.getElementById("subtitle"),
    main:        document.getElementById("main"),
    actionBar:   document.getElementById("actionBar"),
    stats:       document.getElementById("stats"),
    search:      document.getElementById("search"),
    typeFilter:  document.getElementById("typeFilter"),
    sort:        document.getElementById("sort"),
    themeToggle: document.getElementById("themeToggle"),
    statTotal:   document.getElementById("statTotal"),
    statShown:   document.getElementById("statShown"),
    statDownloads: document.getElementById("statDownloads"),
  };

  function applyTheme(t) {
    document.documentElement.setAttribute("data-theme", t);
    try { localStorage.setItem("pi-pkg-theme", t); } catch (e) {}
    els.themeToggle.textContent = t === "dark" ? "☀️ 浅色" : "🌙 深色";
  }
  (function initTheme() {
    var stored = null;
    try { stored = localStorage.getItem("pi-pkg-theme"); } catch (e) {}
    var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    applyTheme(stored || (prefersDark ? "dark" : "light"));
    els.themeToggle.addEventListener("click", function () {
      var cur = document.documentElement.getAttribute("data-theme");
      applyTheme(cur === "dark" ? "light" : "dark");
    });
  })();

  function fmtNum(n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, ","); }
  function fmtDate(ms) {
    if (!ms) return "";
    var d = new Date(ms);
    return d.getUTCFullYear() + "-" +
      String(d.getUTCMonth() + 1).padStart(2, "0") + "-" +
      String(d.getUTCDate()).padStart(2, "0");
  }
  function escapeHtml(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function applyFilters() {
    var q = els.search.value.trim().toLowerCase();
    var typeF = els.typeFilter.value;
    var sortKey = els.sort.value;
    FILTERED = PACKAGES.filter(function (p) {
      if (typeF !== "all") {
        if (typeF === "uncategorized") { if (p.type_list.length > 0) return false; }
        else { if (p.type_list.indexOf(typeF) < 0) return false; }
      }
      if (q) {
        var hay = (p.name + " " + p.description_zh + " " + p.description_en).toLowerCase();
        if (hay.indexOf(q) < 0) return false;
      }
      return true;
    });
    if (sortKey === "downloads") FILTERED.sort(function (a, b) { return b.downloads - a.downloads; });
    else if (sortKey === "recent") FILTERED.sort(function (a, b) { return b.date_ms - a.date_ms; });
    else if (sortKey === "name") FILTERED.sort(function (a, b) {
      return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
    });
    RENDERED = 0;
    renderGrid(true);
    updateStats();
  }

  function renderGrid(isReset) {
    if (isReset) {
      var oldGrid = document.getElementById("grid"); if (oldGrid) oldGrid.remove();
      var oldSent = document.getElementById("sentinel"); if (oldSent) oldSent.remove();
      if (FILTERED.length === 0) {
        var empty = document.createElement("div");
        empty.className = "empty";
        empty.innerHTML = '<div style="font-size:18px;margin-bottom:8px;">没有匹配的包</div>' +
          '<div>试试调整筛选条件。</div>' +
          '<button type="button" id="resetBtn">重置筛选</button>';
        els.main.innerHTML = "";
        els.main.appendChild(empty);
        document.getElementById("resetBtn").addEventListener("click", function () {
          els.search.value = ""; els.typeFilter.value = "all"; els.sort.value = "downloads";
          applyFilters();
        });
        return;
      }
      var grid = document.createElement("section");
      grid.id = "grid"; grid.className = "grid"; grid.setAttribute("aria-label", "包列表");
      els.main.innerHTML = ""; els.main.appendChild(grid);
      var sent = document.createElement("div");
      sent.id = "sentinel"; sent.className = "sentinel"; sent.textContent = "";
      els.main.appendChild(sent); loadSentinel = sent;
      if (window.IntersectionObserver) {
        var io = new IntersectionObserver(function (entries) {
          for (var i = 0; i < entries.length; i++) {
            if (entries[i].isIntersecting) renderMore();
          }
        }, { rootMargin: "200px" });
        io.observe(sent);
      }
    }
    renderMore();
  }

  function renderMore() {
    if (RENDERED >= FILTERED.length) return;
    var grid = document.getElementById("grid"); if (!grid) return;
    var end = Math.min(RENDERED + PAGE_SIZE, FILTERED.length);
    var html = [];
    for (var i = RENDERED; i < end; i++) html.push(buildCardHtml(FILTERED[i]));
    grid.insertAdjacentHTML("beforeend", html.join(""));
    RENDERED = end;
    if (loadSentinel) {
      if (RENDERED >= FILTERED.length) {
        loadSentinel.className = "sentinel";
        loadSentinel.textContent = FILTERED.length > PAGE_SIZE
          ? "已显示全部 " + fmtNum(FILTERED.length) + " 个匹配结果" : "";
      } else {
        loadSentinel.className = "sentinel loading-more";
        loadSentinel.textContent = "加载更多…";
      }
    }
    updateStats();
  }

  function buildCardHtml(p) {
    var badges;
    if (p.type_list.length === 0) badges = '<span class="badge uncat">未分类</span>';
    else badges = p.type_list.map(function (t) {
      return '<span class="badge">' + escapeHtml(t) + "</span>";
    }).join("");
    return '<article class="card">' +
      '<div class="card-head">' +
        '<a class="card-name" href="' + escapeHtml(p.url) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(p.name) + "</a>" +
        '<div class="card-badges">' + badges + "</div>" +
      "</div>" +
      '<div class="card-meta">' +
        '<span class="dl">↓ ' + fmtNum(p.downloads) + "</span>" +
        (p.date_ms ? "<span>" + fmtDate(p.date_ms) + "</span>" : "") +
      "</div>" +
      '<div class="card-desc">' + escapeHtml(p.description_zh) + "</div>" +
      '<div class="card-foot">' +
        '<a href="' + escapeHtml(p.url) + '" target="_blank" rel="noopener noreferrer">查看原页详情 →</a>' +
      "</div>" +
    "</article>";
  }

  function updateStats() {
    els.statTotal.textContent = fmtNum(PACKAGES.length);
    els.statShown.textContent = fmtNum(RENDERED) + " / " + fmtNum(FILTERED.length);
    var totalDl = 0;
    for (var i = 0; i < PACKAGES.length; i++) totalDl += PACKAGES[i].downloads;
    els.statDownloads.textContent = fmtNum(totalDl);
  }

  // Init
  els.actionBar.style.visibility = "visible";
  els.stats.style.visibility = "visible";
  els.subtitle.innerHTML = '共 <b>' + fmtNum(PACKAGES.length) + '</b> 个包 · 数据来源 <a href="https://pi.dev/packages" target="_blank" rel="noopener noreferrer">pi.dev/packages</a>';
  applyFilters();
  els.search.addEventListener("input", function () {
    clearTimeout(searchTimer); searchTimer = setTimeout(applyFilters, 200);
  });
  els.typeFilter.addEventListener("change", applyFilters);
  els.sort.addEventListener("change", applyFilters);
  document.addEventListener("keydown", function (e) {
    if (e.key === "/" && document.activeElement !== els.search) {
      e.preventDefault(); els.search.focus();
    }
  });
})();
</script>
</body>
</html>
"""


def main():
    if not PACKAGES_JSON.exists():
        print(f"ERROR: {PACKAGES_JSON} not found. Run merge.py first.", file=__import__('sys').stderr)
        __import__('sys').exit(1)

    packages_json = PACKAGES_JSON.read_text(encoding='utf-8')

    # Inject data inline: replace //__PACKAGES_DATA__// marker
    inject = 'window.__PACKAGES_DATA__ = ' + packages_json + ';'
    html = HTML_TEMPLATE.replace('//__PACKAGES_DATA__//', inject)

    OUT_HTML.write_text(html, encoding='utf-8')
    size = OUT_HTML.stat().st_size
    print(f"Wrote {OUT_HTML}")
    print(f"Size: {size:,} bytes ({size / 1024:.1f} KB, {size / 1024 / 1024:.2f} MB)")


if __name__ == '__main__':
    main()
