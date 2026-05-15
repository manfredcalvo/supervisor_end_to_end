#!/usr/bin/env python3
"""
scrape_data_management_docs.py

Scrapes Databricks documentation sections and generates one PDF per section.
Each PDF contains the full rendered content of every page — text, images,
code blocks, and diagrams.

Tracks and their sections (one PDF per d=1 sidebar node):
  data_management (default output: ./output/data_management)
    Data Engineering  → de_concepts.pdf, de_lakeflow_connect.pdf,
                        de_lakeflow_pipelines.pdf, de_lakeflow_jobs.pdf,
                        de_best_practices.pdf
    OLTP / Lakebase   → oltp_autoscaling.pdf, oltp_provisioned.pdf,
                        oltp_upgrade.pdf
    SQL               → sql_get_started.pdf, sql_editor.pdf, sql_queries.pdf,
                        sql_alerts.pdf, sql_api_update.pdf
    Data Sharing      → data_sharing_marketplace.pdf, data_sharing_clean_rooms.pdf

  ai_analytics (default output: ./output/ai_analytics)
    Genie             → genie_interface.pdf, genie_spaces.pdf
    AI & ML           → ml_tutorials.pdf, ml_deploy_models.pdf,
                        ml_train_models.pdf, ml_serve_data_ai.pdf,
                        ml_genai_guide.pdf, ml_build_agents.pdf,
                        ml_mlflow.pdf, ml_mlops.pdf, ml_maintenance_policy.pdf,
                        ml_integrations.pdf, ml_graph_analysis.pdf,
                        ml_reference_solutions.pdf
    AI/BI             → aibi_concepts.pdf, aibi_dashboards.pdf,
                        aibi_partner_tools.pdf, aibi_admin.pdf
    Business Semantics→ bs_metric_views.pdf, bs_agent_metadata.pdf

How it works:
  1. URL discovery — Playwright reads the left sidebar nav using depth-first
     traversal, so pages are ordered hierarchically (parent → all children →
     next sibling). Goes up to --nav-levels deep (default 3).
  2. Page rendering — Playwright renders each page with full JS/CSS, then exports
     to PDF via page.pdf(). Nav/sidebar/footer are hidden so only the article
     content is captured.
  3. PDF merging — pypdf merges all per-page PDFs into one file per section.

Usage:
  pip install playwright pypdf
  playwright install chromium
  python scripts/scrape_data_management_docs.py [--track data_management] [--output DIR]
  python scripts/scrape_data_management_docs.py --track ai_analytics --output ./output/ai_analytics

Options:
  --track TRACK      Which doc track to scrape: data_management or ai_analytics
                     (default: data_management)
  --output DIR       Output directory for generated PDFs
                     (default: ./output/<track>)
  --nav-delay MS     Milliseconds to wait after page load before printing (default: 1500)
  --nav-levels N     Sidebar nav levels to follow (default: 3)
  --section NAME     Run only one section by pdf_name, e.g. --section oltp.pdf
"""

import argparse
import asyncio
import io
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright
from pypdf import PdfWriter, PdfReader

# ---------------------------------------------------------------------------
# Section configuration
# ---------------------------------------------------------------------------

BASE_DOMAIN = "https://docs.databricks.com"

DATA_MANAGEMENT_SECTIONS = [
    # ── Data Engineering ──────────────────────────────────────────────────────
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/data-engineering/concepts",
        "pdf_name": "de_concepts.pdf",
        "title": "Data Engineering — Concepts",
        "prefixes": ["/aws/en/data-engineering/concepts"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/ingestion/overview",
        "pdf_name": "de_lakeflow_connect.pdf",
        "title": "Data Engineering — Lakeflow Connect",
        "prefixes": ["/aws/en/ingestion/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/ldp/",
        "pdf_name": "de_lakeflow_pipelines.pdf",
        "title": "Data Engineering — Lakeflow Spark Declarative Pipelines",
        "prefixes": ["/aws/en/ldp/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/jobs/",
        "pdf_name": "de_lakeflow_jobs.pdf",
        "title": "Data Engineering — Lakeflow Jobs",
        "prefixes": ["/aws/en/jobs/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/data-engineering/best-practices",
        "pdf_name": "de_best_practices.pdf",
        "title": "Data Engineering — Best Practices",
        "prefixes": ["/aws/en/data-engineering/best-practices"],
    },
    # ── OLTP / Lakebase ───────────────────────────────────────────────────────
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/oltp/projects/",
        "pdf_name": "oltp_autoscaling.pdf",
        "title": "OLTP — Lakebase Autoscaling",
        "prefixes": ["/aws/en/oltp/projects/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/oltp/instances/",
        "pdf_name": "oltp_provisioned.pdf",
        "title": "OLTP — Lakebase Provisioned",
        "prefixes": ["/aws/en/oltp/instances/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/oltp/upgrade-to-autoscaling",
        "pdf_name": "oltp_upgrade.pdf",
        "title": "OLTP — Autoscaling by Default",
        "prefixes": ["/aws/en/oltp/upgrade-to-autoscaling"],
    },
    # ── SQL / Warehousing ─────────────────────────────────────────────────────
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/sql/get-started/",
        "pdf_name": "sql_get_started.pdf",
        "title": "SQL — Get Started",
        "prefixes": ["/aws/en/sql/get-started/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/sql/user/sql-editor/",
        "pdf_name": "sql_editor.pdf",
        "title": "SQL — SQL Editor",
        "prefixes": ["/aws/en/sql/user/sql-editor/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/sql/user/queries/",
        "pdf_name": "sql_queries.pdf",
        "title": "SQL — Queries",
        "prefixes": ["/aws/en/sql/user/queries/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/sql/user/alerts/",
        "pdf_name": "sql_alerts.pdf",
        "title": "SQL — Alerts",
        "prefixes": ["/aws/en/sql/user/alerts/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/sql/dbsql-api-latest",
        "pdf_name": "sql_api_update.pdf",
        "title": "SQL — Update Databricks SQL API Tools",
        "prefixes": ["/aws/en/sql/dbsql-api-latest"],
    },
    # ── Data Sharing ──────────────────────────────────────────────────────────
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/marketplace/",
        "pdf_name": "data_sharing_marketplace.pdf",
        "title": "Data Sharing — Databricks Marketplace",
        "prefixes": ["/aws/en/marketplace/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/clean-rooms/",
        "pdf_name": "data_sharing_clean_rooms.pdf",
        "title": "Data Sharing — Clean Rooms",
        "prefixes": ["/aws/en/clean-rooms/"],
    },
]

AI_ANALYTICS_SECTIONS = [
    # ── Genie ─────────────────────────────────────────────────────────────────
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/genie-ui/genie",
        "pdf_name": "genie_interface.pdf",
        "title": "Genie — Use the Genie Interface",
        "prefixes": ["/aws/en/genie-ui/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/genie/",
        "pdf_name": "genie_spaces.pdf",
        "title": "Genie — Genie Spaces",
        "prefixes": ["/aws/en/genie/"],
    },
    # ── AI & Machine Learning ─────────────────────────────────────────────────
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/machine-learning/ai-ml-tutorials",
        "pdf_name": "ml_tutorials.pdf",
        "title": "AI & ML — Tutorials",
        "prefixes": ["/aws/en/machine-learning/ai-ml-tutorials"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/machine-learning/model-serving/",
        "pdf_name": "ml_deploy_models.pdf",
        "title": "AI & ML — Deploy Models",
        "prefixes": ["/aws/en/machine-learning/model-serving/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/machine-learning/train-model/",
        "pdf_name": "ml_train_models.pdf",
        "title": "AI & ML — Train Models",
        "prefixes": ["/aws/en/machine-learning/train-model/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/machine-learning/serve-data-ai",
        "pdf_name": "ml_serve_data_ai.pdf",
        "title": "AI & ML — Serve Data for AI",
        "prefixes": ["/aws/en/machine-learning/serve-data-ai"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/generative-ai/guide/",
        "pdf_name": "ml_genai_guide.pdf",
        "title": "AI & ML — GenAI Guide",
        "prefixes": ["/aws/en/generative-ai/guide/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/generative-ai/agent-framework/build-genai-apps",
        "pdf_name": "ml_build_agents.pdf",
        "title": "AI & ML — Build Agents",
        "prefixes": ["/aws/en/generative-ai/agent-framework/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/mlflow/",
        "pdf_name": "ml_mlflow.pdf",
        "title": "AI & ML — MLflow for Models",
        "prefixes": ["/aws/en/mlflow/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/machine-learning/mlops/mlops-workflow",
        "pdf_name": "ml_mlops.pdf",
        "title": "AI & ML — MLOps",
        "prefixes": ["/aws/en/machine-learning/mlops/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/machine-learning/retired-models-policy",
        "pdf_name": "ml_maintenance_policy.pdf",
        "title": "AI & ML — Gen AI Model Maintenance Policy",
        "prefixes": ["/aws/en/machine-learning/retired-models-policy"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/machine-learning/integrations",
        "pdf_name": "ml_integrations.pdf",
        "title": "AI & ML — Integrations",
        "prefixes": ["/aws/en/machine-learning/integrations"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/machine-learning/graph-analysis",
        "pdf_name": "ml_graph_analysis.pdf",
        "title": "AI & ML — Graph and Network Analysis",
        "prefixes": ["/aws/en/machine-learning/graph-analysis"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/machine-learning/reference-solutions/",
        "pdf_name": "ml_reference_solutions.pdf",
        "title": "AI & ML — Reference Solutions",
        "prefixes": ["/aws/en/machine-learning/reference-solutions/"],
    },
    # ── AI/BI ─────────────────────────────────────────────────────────────────
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/ai-bi/concepts",
        "pdf_name": "aibi_concepts.pdf",
        "title": "AI/BI — Concepts",
        "prefixes": ["/aws/en/ai-bi/concepts"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/dashboards/",
        "pdf_name": "aibi_dashboards.pdf",
        "title": "AI/BI — Dashboards",
        "prefixes": ["/aws/en/dashboards/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/ai-bi/tools",
        "pdf_name": "aibi_partner_tools.pdf",
        "title": "AI/BI — Partner Tools",
        "prefixes": ["/aws/en/ai-bi/tools"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/ai-bi/admin/",
        "pdf_name": "aibi_admin.pdf",
        "title": "AI/BI — Admin Guide",
        "prefixes": ["/aws/en/ai-bi/admin/"],
    },
    # ── Business Semantics ────────────────────────────────────────────────────
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/business-semantics/metric-views/",
        "pdf_name": "bs_metric_views.pdf",
        "title": "Business Semantics — Metric Views",
        "prefixes": ["/aws/en/business-semantics/metric-views/"],
    },
    {
        "base_url": f"{BASE_DOMAIN}/aws/en/business-semantics/agent-metadata",
        "pdf_name": "bs_agent_metadata.pdf",
        "title": "Business Semantics — Agent Metadata",
        "prefixes": ["/aws/en/business-semantics/agent-metadata"],
    },
]

TRACKS = {
    "data_management": DATA_MANAGEMENT_SECTIONS,
    "ai_analytics": AI_ANALYTICS_SECTIONS,
}

# ---------------------------------------------------------------------------
# CSS: hide nav/sidebar/footer — only the article content is printed
# ---------------------------------------------------------------------------

HIDE_CHROME_CSS = """
    .navbar,
    .theme-doc-sidebar-container,
    .docSidebarContainer_dpKa,
    footer, .footer,
    .pagination-nav,
    .theme-doc-toc-mobile,
    .tocCollapsible_ETCw,
    nav[aria-label="Docs pages"],
    .announcementBar_mb4j,
    #__docusaurus-base-url-issue-banner,
    #onetrust-banner-sdk,
    #onetrust-consent-sdk,
    .cookie-consent,
    [class*="cookieBanner"],
    [class*="CookieConsent"],
    [id*="cookie-banner"],
    [class*="feedbackWidget"] {
        display: none !important;
    }
    article {
        max-width: 100% !important;
        margin: 0 auto !important;
        padding: 24px 32px !important;
    }
    .docItemContainer_c0TR, .docItemCol_z5aJ,
    .col, .container, main {
        max-width: 100% !important;
        padding: 0 !important;
        margin: 0 !important;
    }
"""

COOKIE_ACCEPT_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "button:has-text('Accept All')",
    "button:has-text('Accept all')",
    "button:has-text('Accept Cookies')",
    "button:has-text('I Accept')",
    "button:has-text('Agree')",
]

# JavaScript that reads ALL currently-visible sidebar items in one call
JS_GET_NAV_ITEMS = """
    () => {
        const results = [];
        function walk(ul, d) {
            ul.querySelectorAll(':scope > li').forEach(li => {
                const collDiv = li.querySelector(':scope > .menu__list-item-collapsible');
                const a = collDiv
                    ? collDiv.querySelector('a')
                    : li.querySelector(':scope > a');
                if (!a) return;
                const span = a.querySelector('span[title]');
                const text = span ? span.getAttribute('title') : a.textContent.trim();
                const href = a.getAttribute('href');
                if (!text || !href || href === '#') return;
                const isCategory = a.classList.contains('menu__link--sublist');
                results.push({ text, href, isCategory, depth: d });
                // recurse into already-expanded sub-lists
                const sub = li.querySelector(':scope > ul.menu__list');
                if (sub) walk(sub, d + 1);
            });
        }
        const sidebar = document.querySelector('.theme-doc-sidebar-container');
        if (!sidebar) return [];
        const topUl = sidebar.querySelector('ul.menu__list');
        if (topUl) walk(topUl, 0);
        return results;
    }
"""

# ---------------------------------------------------------------------------
# Sidebar-driven URL discovery
# ---------------------------------------------------------------------------

async def accept_cookies(page) -> None:
    """Accept the cookie banner once — the cookie persists for the whole session."""
    try:
        await page.goto(f"{BASE_DOMAIN}/aws/en/", wait_until="domcontentloaded", timeout=20000)
        for selector in COOKIE_ACCEPT_SELECTORS:
            try:
                await page.click(selector, timeout=2000)
                print("  Cookie banner accepted.")
                return
            except Exception:
                continue
        print("  No cookie banner found.")
    except Exception as exc:
        print(f"  Cookie setup skipped: {exc}")


async def collect_sidebar_urls(
    page,
    base_url: str,
    allowed_prefixes: list[str],
    nav_levels: int,
) -> list[tuple[str, int]]:
    """
    Discover pages by reading the sidebar nav using depth-first traversal.

    Navigates to each category page to reveal its children, recursing immediately
    so siblings are ordered after all of a category's descendants — matching the
    visual hierarchy in the sidebar.  item["depth"] (the item's position in the
    sidebar tree) is used for the nav_levels check so siblings discovered inside
    a child navigation aren't penalised by extra navigation steps.

    Returns an ordered, deduplicated list of (url, depth) pairs where depth is
    the sidebar tree depth at first discovery (0 = top-level section).
    """

    def in_scope(href: str) -> bool:
        return bool(href) and href != "#" and any(href.startswith(p) for p in allowed_prefixes)

    def abs_url(href: str) -> str:
        return href if href.startswith("http") else BASE_DOMAIN + href

    navigated: set[str] = set()
    collected: dict[str, int] = {}  # url -> depth at first discovery

    async def visit(url: str) -> None:
        if url in navigated:
            return
        navigated.add(url)
        try:
            await page.goto(url, wait_until="networkidle", timeout=60000)
        except Exception as exc:
            print(f"    [WARN] discovery navigation failed: {url} — {exc}")
            return
        items = await page.evaluate(JS_GET_NAV_ITEMS)
        for item in items:
            href: str = item["href"].split("#")[0]
            if not in_scope(href):
                continue
            u = abs_url(href)
            if u not in collected:
                collected[u] = item["depth"]  # record depth at first discovery
            if item["isCategory"] and item["depth"] < nav_levels and u not in navigated:
                await visit(u)  # recurse before moving to next sibling

    await visit(base_url)
    print(f"  {len(collected)} pages discovered via sidebar.")
    return list(collected.items())


# ---------------------------------------------------------------------------
# Page rendering
# ---------------------------------------------------------------------------

async def render_page_to_pdf(url: str, page, nav_delay_ms: int) -> bytes | None:
    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.add_style_tag(content=HIDE_CHROME_CSS)
        await page.wait_for_timeout(nav_delay_ms)
        return await page.pdf(
            format="A4",
            print_background=True,
            margin={"top": "20mm", "bottom": "20mm", "left": "18mm", "right": "18mm"},
        )
    except Exception as exc:
        print(f"    [WARN] render failed: {url} — {exc}")
        return None


# ---------------------------------------------------------------------------
# PDF merging and splitting
# ---------------------------------------------------------------------------

MAX_PAGES_PER_PDF = 500


def merge_pdfs(pdf_bytes_list: list[bytes], output_path: Path) -> None:
    writer = PdfWriter()
    for pdf_bytes in pdf_bytes_list:
        writer.append_pages_from_reader(PdfReader(io.BytesIO(pdf_bytes)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        writer.write(f)
    size_kb = output_path.stat().st_size // 1024
    print(f"  Saved: {output_path}  ({size_kb} KB)")


def split_coherently(
    rendered: list[tuple[bytes, int]],
    max_pages: int,
) -> list[list[bytes]]:
    """
    Split rendered pages into groups of at most `max_pages`, preserving subsection
    coherence.

    Strategy: try progressively relaxed split-depth thresholds (0, 1, 2, 3) until
    at least one split point is found.  This means:
      - First try: split only at top-level section boundaries (depth 0)
      - If no split found: allow splits at depth-1 subsection boundaries too
      - And so on — always preferring the shallowest coherent boundary available
    """
    for split_depth_limit in range(4):
        groups: list[list[bytes]] = []
        current: list[bytes] = []
        current_pages = 0

        for pdf_bytes, depth in rendered:
            page_count = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
            if depth <= split_depth_limit and current_pages >= max_pages and current:
                groups.append(current)
                current = []
                current_pages = 0
            current.append(pdf_bytes)
            current_pages += page_count

        if current:
            groups.append(current)

        if len(groups) > 1:
            return groups  # found a coherent split point at this depth

    # No split found at any depth — return as one group
    return [[b for b, _ in rendered]]


def save_pdfs(
    rendered: list[tuple[bytes, int]],
    output_dir: Path,
    pdf_name: str,
) -> None:
    """Merge rendered pages into one PDF, or split into numbered parts if >500 pages."""
    groups = split_coherently(rendered, MAX_PAGES_PER_PDF)
    if len(groups) == 1:
        merge_pdfs(groups[0], output_dir / pdf_name)
    else:
        stem, suffix = Path(pdf_name).stem, Path(pdf_name).suffix
        print(f"  >{MAX_PAGES_PER_PDF} pages — splitting into {len(groups)} parts:")
        for idx, group in enumerate(groups, 1):
            merge_pdfs(group, output_dir / f"{stem}_{idx}{suffix}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def process_section(
    section: dict,
    output_dir: Path,
    nav_delay_ms: int,
    nav_levels: int,
) -> None:
    print(f"\n{'='*60}")
    print(f"  {section['title']}")
    print(f"{'='*60}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        )
        page = await context.new_page()

        await accept_cookies(page)

        print(f"  Discovering pages via sidebar (nav_levels={nav_levels}) ...")
        url_depths = await collect_sidebar_urls(
            page,
            base_url=section["base_url"],
            allowed_prefixes=section["prefixes"],
            nav_levels=nav_levels,
        )

        rendered: list[tuple[bytes, int]] = []
        for i, (url, depth) in enumerate(url_depths, 1):
            print(f"  [{i:3}/{len(url_depths)}] (d={depth}) {url}")
            pdf = await render_page_to_pdf(url, page, nav_delay_ms)
            if pdf:
                rendered.append((pdf, depth))

        await browser.close()

    if rendered:
        total = sum(len(PdfReader(io.BytesIO(b)).pages) for b, _ in rendered)
        print(f"\n  Merging {len(rendered)} pages ({total} PDF pages) ...")
        save_pdfs(rendered, output_dir, section["pdf_name"])
    else:
        print("  [ERROR] No pages rendered successfully.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Databricks docs and generate one PDF per section."
    )
    parser.add_argument(
        "--track", default="data_management",
        choices=list(TRACKS.keys()),
        help="Doc track to scrape (default: data_management)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output directory (default: ./output/<track>)",
    )
    parser.add_argument(
        "--nav-delay", type=int, default=1500,
        help="Milliseconds to wait after page load before printing (default: 1500)",
    )
    parser.add_argument(
        "--nav-levels", type=int, default=3,
        help="Sidebar nav levels to follow (default: 3)",
    )
    parser.add_argument(
        "--section", type=str, default=None,
        help="Run only one section by pdf_name, e.g. --section oltp.pdf",
    )
    args = parser.parse_args()

    all_sections = TRACKS[args.track]
    output_dir = Path(args.output) if args.output else Path(f"./output/{args.track}")

    if args.section:
        sections = [s for s in all_sections if s["pdf_name"] == args.section]
        if not sections:
            print(f"Unknown section '{args.section}' in track '{args.track}'.")
            print(f"Options: {[s['pdf_name'] for s in all_sections]}")
            return
    else:
        sections = all_sections

    for section in sections:
        asyncio.run(process_section(section, output_dir, args.nav_delay, args.nav_levels))

    print(f"\nAll done. PDFs saved to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()
