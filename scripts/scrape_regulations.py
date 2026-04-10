#!/usr/bin/env python3
"""
ITTF regulations scraper.

Strategy:
- Prefer lightweight requests-based discovery for PDF links
- Fall back to Playwright page loading when static discovery fails
- Download the latest PDF
- Extract PDF text into Markdown
- Prepare a Chinese translation prompt for downstream translation
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import sys
from pathlib import Path
from urllib.parse import urljoin

from lib.anti_bot import DelayConfig, RiskControlTriggered
from lib.capture import save_json
from lib.page_ops import guarded_goto

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ittf_regulations_scraper")

RANKINGS_URL = "https://ittf.com/rankings"
KNOWN_PATTERNS = [
    "ITTF-Table-Tennis-World-Ranking-Regulations",
    "World-Ranking-Regulations",
    "ITTF-Ranking-Regulations",
]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ITTF regulations scraper")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--slow-mo", type=int, default=100)
    parser.add_argument("--output", default="data/regulations/latest_regulations.json")
    parser.add_argument("--download-dir", default="../docs")
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-extract", action="store_true")
    parser.add_argument("--skip-translate-prompt", action="store_true")
    return parser


def discover_pdf_links_via_requests() -> list[str]:
    import requests
    from bs4 import BeautifulSoup

    response = requests.get(
        RANKINGS_URL,
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=30,
    )
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if ".pdf" not in href.lower():
            continue
        if not any(pattern in href for pattern in KNOWN_PATTERNS):
            continue
        links.append(urljoin(RANKINGS_URL, href))
    return sorted(set(links))


def discover_pdf_links_via_playwright(args: argparse.Namespace) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        logger.error("Please install Playwright first: pip install playwright && playwright install")
        return []

    delay_cfg = DelayConfig(3.0, 8.0, 5.0, 10.0)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=args.headless, slow_mo=args.slow_mo)
        context = browser.new_context()
        page = context.new_page()

        try:
            guarded_goto(page, RANKINGS_URL, delay_cfg, "open rankings page for regulations discovery")
            anchors = page.locator("a")
            links: list[str] = []
            for i in range(anchors.count()):
                href = anchors.nth(i).get_attribute("href")
                if not href:
                    continue
                if ".pdf" not in href.lower():
                    continue
                if not any(pattern in href for pattern in KNOWN_PATTERNS):
                    continue
                links.append(urljoin(RANKINGS_URL, href))
        except RiskControlTriggered as exc:
            logger.error("Risk control triggered: %s", exc)
            browser.close()
            return []

        browser.close()
    return sorted(set(links))


def download_latest_pdf(url: str, download_dir: Path) -> Path:
    import requests

    download_dir.mkdir(parents=True, exist_ok=True)
    filename = url.split("/")[-1] or "latest_regulations.pdf"
    pdf_path = download_dir / filename

    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    response.raise_for_status()
    pdf_path.write_bytes(response.content)
    return pdf_path


def get_file_hash(file_path: Path) -> str:
    hash_md5 = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def extract_pdf_to_markdown(pdf_path: Path, md_path: Path) -> bool:
    import pypdf

    logger.info("Extracting PDF content: %s", pdf_path)
    try:
        reader = pypdf.PdfReader(pdf_path)
        full_text = ""
        for i, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            if page_text:
                full_text += f"\n\n## 第 {i} 页\n\n{page_text}"

        md_path.write_text(full_text.strip() + "\n", encoding="utf-8")
        logger.info("Saved markdown: %s", md_path)
        return True
    except Exception as exc:
        logger.error("PDF extraction failed: %s", exc)
        return False


def write_translation_prompt(md_path: Path) -> Path:
    content = md_path.read_text(encoding="utf-8")
    prompt = f"""请将以下ITTF世界乒乓球排名规则的英文文档翻译成中文。

要求：
1. 保持原有格式和结构
2. 准确翻译专业术语
3. 表格保持原样
4. 添加页脚说明（文件来源、最后更新日期、原文链接）

以下是文档内容：

{content}"""
    prompt_path = md_path.with_suffix(".translation_prompt.txt")
    prompt_path.write_text(prompt, encoding="utf-8")
    return prompt_path


def run(args: argparse.Namespace) -> int:
    output_path = Path(args.output)

    try:
        links = discover_pdf_links_via_requests()
        discovery_method = "requests"
    except Exception as exc:
        logger.warning("Static PDF discovery failed, falling back to Playwright: %s", exc)
        links = discover_pdf_links_via_playwright(args)
        discovery_method = "playwright"

    if not links:
        logger.error("No regulations PDF links discovered")
        return 2

    latest_pdf = links[0]
    downloaded_to = None
    md_path = None
    prompt_path = None
    pdf_hash = None

    if not args.skip_download:
        try:
            downloaded_file = download_latest_pdf(latest_pdf, Path(args.download_dir))
            downloaded_to = str(downloaded_file.resolve())
            pdf_hash = get_file_hash(downloaded_file)
            logger.info("Downloaded latest regulations PDF: %s", downloaded_to)

            if not args.skip_extract:
                md_file = downloaded_file.with_suffix('.md')
                if extract_pdf_to_markdown(downloaded_file, md_file):
                    md_path = str(md_file.resolve())
                    if not args.skip_translate_prompt:
                        prompt_file = write_translation_prompt(md_file)
                        prompt_path = str(prompt_file.resolve())
                        logger.info("Saved translation prompt: %s", prompt_path)
        except Exception as exc:
            logger.warning("Failed to process latest regulations PDF: %s", exc)

    payload = {
        "source_url": RANKINGS_URL,
        "discovery_method": discovery_method,
        "pdf_links": links,
        "latest_pdf": latest_pdf,
        "downloaded_to": downloaded_to,
        "pdf_hash": pdf_hash,
        "markdown_path": md_path,
        "translation_prompt_path": prompt_path,
    }
    save_json(output_path, payload)
    logger.info("Saved regulations discovery JSON: %s", output_path)
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    rc = run(args)
    sys.exit(rc)


if __name__ == "__main__":
    main()
