"""
Parse MIIT 工信部 enterprise admission change HTML attachment.

Handles source_format=html_image_attachment for attachments like:
  - 拟发布新准入车辆生产企业及已准入企业变更信息清单
  - (datainfo/.../art/...html data pages with images)

V1.0:
  - Extract page title and section headings
  - Detect image-backed content (cms_files / img tags)
  - No OCR: reports parse_status=partial for image content
  - Structured evidence output

V1.1:
  - datainfo_resource_extractor: comprehensive HTML/JS/DOM resource extraction
  - Extracts img.src, data-src, data-original, data-url, a.href, iframe.src
  - Scans <script> content for embedded resource URLs
  - Determines extraction_status (success / needs_browser_network_trace)
  - Resolves relative URLs, deduplicates, records source fields
  - No direct OCR: only enters OCR fallback when image_asset_urls is non-empty
"""

import re, json
from pathlib import Path
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from typing import Optional

MODULE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = MODULE_DIR.parents[1]

CANONICAL_SECTION = "拟发布新准入车辆生产企业"
SECTION_CANDIDATES = [
    "拟发布的新准入车辆生产企业",
    "拟发布新准入车辆生产企业",
    "新准入车辆生产企业",
    "汽车生产企业",
    "摩托车生产企业",
    "三轮汽车生产企业",
    "已准入企业变更信息",
    "已准入企业变更",
]

RE_ENTERPRISE_ADMISSION = re.compile(
    r"(新准入车辆生产企业|已准入企业变更信息清单|拟发布的新准入车辆生产企业|新增车辆生产企业|拟发布新增车辆生产企业)"
)
RE_SECTION_HEADING = re.compile(
    r"(拟发布新准入车辆生产企业|汽车生产企业|摩托车生产企业|三轮汽车生产企业|已准入企业变更信息)"
)
RE_CMS_IMAGE = re.compile(r"/cms_files/.*\.(png|jpg|jpeg|gif|bmp|webp)", re.IGNORECASE)
RE_IMAGE_TAG = re.compile(r'<img[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)

# V1.1: Comprehensive resource extraction patterns
RE_DATAINFO_IMAGE_MARKER = re.compile(r'Image\s*详细信息|图片信息|图片内容|图像信息', re.IGNORECASE)
RE_CMS_FILE_REF = re.compile(r'/cms_files/[^"\'\)\s<>]+', re.IGNORECASE)
RE_DATAINFO_REF = re.compile(r'/datainfo/[^"\'\)\s<>]+', re.IGNORECASE)
RE_WEBFILE_REF = re.compile(r'/webfile/[^"\'\)\s<>]+', re.IGNORECASE)
RE_UPLOAD_REF = re.compile(r'/upload/[^"\'\)\s<>]+', re.IGNORECASE)
RE_SCRIPT_RESOURCE_URL = re.compile(
    r'(?:cms_files|webfile|upload|picture|image|datainfo|attach)'
    r'[^"\'\)\s<>]*?\.(?:jpg|jpeg|png|gif|webp|json|html|doc|docx|xls|xlsx|pdf)',
    re.IGNORECASE
)
RE_JSON_API_URL = re.compile(r'https?://[^\s"\'\)<>]+\.json', re.IGNORECASE)
RE_IMAGE_EXT = re.compile(r'\.(jpg|jpeg|png|gif|webp|bmp|svg)$', re.IGNORECASE)


class _HtmlDataPageParser(HTMLParser):
    """Parse HTML data page to extract title, headings, images."""

    def __init__(self, base_url: str = ""):
        super().__init__()
        self.base_url = base_url
        self.page_title: str = ""
        self.section_headings: list[str] = []
        self.image_urls: list[str] = []
        self.all_text: list[str] = []
        self._in_title = False
        self._in_content = False
        self._current_tag = ""
        self._current_attrs: dict = {}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self._current_tag = tag
        self._current_attrs = a

        if tag == "title":
            self._in_title = True

        # Detect content container
        if tag == "div" and "class" in a:
            cls = a["class"]
            if any(c in cls for c in ("content", "article", "main", "zoom", "text", "TRS_Editor")):
                self._in_content = True
        if tag == "div" and "id" in a:
            aid = a["id"]
            if any(c in aid for c in ("zoom", "content", "article", "main")):
                self._in_content = True

        # Extract image URLs
        if tag == "img" and "src" in a:
            src = a["src"]
            full_url = urljoin(self.base_url, src) if self.base_url else src
            if full_url not in self.image_urls:
                self.image_urls.append(full_url)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag in ("div", "article", "section"):
            self._in_content = False

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return

        if self._in_title:
            self.page_title += text

        if self._in_content or self._current_tag in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "span"):
            self.all_text.append(text)
            if self._current_tag in ("h1", "h2", "h3"):
                if RE_SECTION_HEADING.search(text):
                    if text not in self.section_headings:
                        self.section_headings.append(text)


class _DataInfoResourceParser(HTMLParser):
    """Comprehensive HTML/JS/DOM resource extractor for datainfo pages."""

    def __init__(self, base_url: str = ""):
        super().__init__()
        self.base_url = base_url
        self.page_title: str = ""
        self.image_asset_urls: list[dict] = []
        self.linked_asset_urls: list[dict] = []
        self.iframe_urls: list[dict] = []
        self._script_texts: list[str] = []
        self._in_title = False
        self._in_script = False
        self._script_buffer = ""

    def _add_url(self, url_list: list, url: str, source: str):
        full_url = _resolve_url(url, self.base_url)
        entry = {"url": full_url, "source": source}
        if entry not in url_list:
            url_list.append(entry)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)

        if tag == "title":
            self._in_title = True
        if tag == "script":
            self._in_script = True
            self._script_buffer = ""

        if tag == "img":
            for attr in ("src", "data-src", "data-original", "data-url"):
                if attr in a:
                    self._add_url(self.image_asset_urls, a[attr], f"img.{attr}")

        if tag == "a" and "href" in a:
            href = a["href"]
            self._add_url(self.linked_asset_urls, href, "a.href")

        if tag == "iframe" and "src" in a:
            self._add_url(self.iframe_urls, a["src"], "iframe.src")

        # data-url on any non-img element
        if tag != "img" and "data-url" in a:
            self._add_url(self.image_asset_urls, a["data-url"], f"{tag}.data-url")

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag == "script":
            self._in_script = False
            if self._script_buffer.strip():
                self._script_texts.append(self._script_buffer)
            self._script_buffer = ""

    def handle_data(self, data):
        text = data.strip()
        if not text:
            return
        if self._in_title:
            self.page_title += text
        if self._in_script:
            self._script_buffer += data


def _resolve_url(url: str, base_url: str) -> str:
    """Resolve a potentially relative URL to absolute using base_url."""
    if not url:
        return url
    if url.startswith("//"):
        return "https:" + url
    if url.startswith(("http://", "https://")):
        return url
    if base_url:
        return urljoin(base_url, url)
    return url


def _dedup_url_list(url_list: list[dict]) -> list[dict]:
    """Deduplicate a list of {url, source} dicts by url."""
    seen: set[str] = set()
    result: list[dict] = []
    for item in url_list:
        key = item["url"]
        if key not in seen:
            seen.add(key)
            result.append(item)
    return result


def datainfo_resource_extractor(
    datainfo_html: str,
    datainfo_url: str,
    parent_notice_url: str = "",
) -> dict:
    """
    Extract all resources from a datainfo HTML page.

    Parses HTML/JS/DOM for:
      - <img src>, data-src, data-original, data-url
      - <a href> linked assets
      - <iframe src>
      - <script> text (regex scan for cms_files, webfile, upload, etc.)

    Does NOT perform OCR. If image_asset_urls is non-empty and images
    are downloaded, OCR may be attempted as a separate step.

    Args:
        datainfo_html: Raw HTML content of the datainfo page
                       (may be empty if download failed)
        datainfo_url: The datainfo page URL (used for relative URL resolution)
        parent_notice_url: Parent notice page URL (fallback for resolution)

    Returns:
        dict with fields:
          source_title, section_candidates,
          image_asset_urls, linked_asset_urls, iframe_urls,
          script_asset_urls, api_candidate_urls, cms_file_urls,
          extraction_status, extraction_reason
    """
    base_url = datainfo_url or parent_notice_url

    parser = _DataInfoResourceParser(base_url=base_url)
    try:
        parser.feed(datainfo_html)
    except Exception:
        pass

    source_title = parser.page_title.strip()
    if not source_title:
        source_title = _guess_title_from_html(datainfo_html)

    section_candidates = [s for s in SECTION_CANDIDATES if s in datainfo_html]

    image_asset_urls = _dedup_url_list(parser.image_asset_urls)
    linked_asset_urls = _dedup_url_list(parser.linked_asset_urls)
    iframe_urls = _dedup_url_list(parser.iframe_urls)

    # Scan script texts for embedded resource URLs
    script_asset_urls: list[dict] = []
    api_candidate_urls: list[dict] = []
    cms_file_urls: list[dict] = []

    for script_text in parser._script_texts:
        # cms_files paths
        for m in RE_CMS_FILE_REF.finditer(script_text):
            url = _resolve_url(m.group(0), base_url)
            entry = {"url": url, "source": "script.regex"}
            if entry not in script_asset_urls:
                script_asset_urls.append(entry)
            if entry not in cms_file_urls:
                cms_file_urls.append(entry)

        # datainfo paths
        for m in RE_DATAINFO_REF.finditer(script_text):
            url = _resolve_url(m.group(0), base_url)
            entry = {"url": url, "source": "script.regex"}
            if entry not in script_asset_urls:
                script_asset_urls.append(entry)

        # webfile / upload / picture / image references
        for m in RE_SCRIPT_RESOURCE_URL.finditer(script_text):
            url = _resolve_url(m.group(0), base_url)
            entry = {"url": url, "source": "script.regex"}
            if entry not in script_asset_urls:
                script_asset_urls.append(entry)
            # Classify cms_files in script too
            if "/cms_files/" in m.group(0) and entry not in cms_file_urls:
                cms_file_urls.append(entry)

        # JSON API URLs
        for m in RE_JSON_API_URL.finditer(script_text):
            entry = {"url": m.group(0), "source": "script.regex"}
            if entry not in api_candidate_urls:
                api_candidate_urls.append(entry)
            if entry not in script_asset_urls:
                script_asset_urls.append(entry)

    # Also classify cms_files from HTML attributes
    for entry in image_asset_urls + linked_asset_urls + iframe_urls:
        if "/cms_files/" in entry["url"] and entry not in cms_file_urls:
            cms_file_urls.append(entry)
        if entry["url"].endswith(".json") and entry not in api_candidate_urls:
            api_candidate_urls.append(entry)

    # Determine extraction status
    has_image_marker = bool(RE_DATAINFO_IMAGE_MARKER.search(datainfo_html))
    total_resources = (
        len(image_asset_urls)
        + len(linked_asset_urls)
        + len(iframe_urls)
        + len(script_asset_urls)
        + len(api_candidate_urls)
        + len(cms_file_urls)
    )

    if not datainfo_html.strip():
        extraction_status = "needs_browser_network_trace"
        extraction_reason = (
            "datainfo HTML is empty (download failed); "
            "cannot extract static resources; needs browser network trace"
        )
    elif has_image_marker and total_resources == 0:
        extraction_status = "needs_browser_network_trace"
        extraction_reason = (
            "html shell contains Image detail marker but no static asset URL found"
        )
    elif total_resources > 0:
        extraction_status = "success"
        extraction_reason = (
            f"extracted {total_resources} resource URLs from HTML/JS/DOM "
            f"({len(image_asset_urls)} images, {len(linked_asset_urls)} links, "
            f"{len(iframe_urls)} iframes, {len(script_asset_urls)} script refs)"
        )
    else:
        extraction_status = "partial"
        extraction_reason = "no resources found in HTML"

    return {
        "source_title": source_title,
        "section_candidates": section_candidates,
        "image_asset_urls": image_asset_urls,
        "linked_asset_urls": linked_asset_urls,
        "iframe_urls": iframe_urls,
        "script_asset_urls": script_asset_urls,
        "api_candidate_urls": api_candidate_urls,
        "cms_file_urls": cms_file_urls,
        "extraction_status": extraction_status,
        "extraction_reason": extraction_reason,
    }


def extract_images_from_html(html: str, base_url: str) -> list[str]:
    """Extract image URLs from HTML content using regex."""
    urls = []
    # <img src="...">
    for m in RE_IMAGE_TAG.finditer(html):
        src = m.group(1)
        full_url = urljoin(base_url, src) if base_url else src
        if full_url not in urls:
            urls.append(full_url)
    # cms_files references in any attribute
    for m in RE_CMS_IMAGE.finditer(html):
        match_url = m.group(0)
        full_url = urljoin(base_url, match_url) if base_url else match_url
        if full_url not in urls:
            urls.append(full_url)
    return urls


def has_image_content(html: str) -> bool:
    """Check if the HTML page primarily contains image-based content."""
    # Check for img tags
    if "<img" in html:
        return True
    # Check for cms_files image references
    if RE_CMS_IMAGE.search(html):
        return True
    # Check for "Image" keyword in content (common in MIIT data pages)
    if "Image" in html or "详细信息" in html:
        return True
    return False


def parse_enterprise_admission_page(
    html: str,
    page_url: str = "",
    parent_notice_url: str = "",
    parent_notice_title: str = "",
) -> dict:
    """
    Parse an enterprise admission change HTML data page.

    Args:
        html: HTML content of the data page
        page_url: URL of the data page
        parent_notice_url: URL of the parent notice page
        parent_notice_title: Title of the parent notice page

    Returns:
        Parsed evidence dict with standardized fields
    """
    # V1.1: Run comprehensive resource extraction
    extraction = datainfo_resource_extractor(
        datainfo_html=html,
        datainfo_url=page_url,
        parent_notice_url=parent_notice_url,
    )

    parser = _HtmlDataPageParser(base_url=page_url)
    try:
        parser.feed(html)
    except Exception:
        pass

    page_title = extraction["source_title"] or parser.page_title.strip() or _guess_title_from_html(html)
    section_headings = parser.section_headings
    text_content = " ".join(parser.all_text)

    # Extract image URLs (backward-compatible flat list)
    image_urls = parser.image_urls
    if not image_urls:
        image_urls = extract_images_from_html(html, page_url)
    detail_asset_urls = [u["url"] for u in extraction["image_asset_urls"]]
    if not image_urls:
        image_urls = detail_asset_urls

    # Detect if content is image-backed
    is_image_backed = has_image_content(html)

    # Determine parse status using extraction info
    if extraction["extraction_status"] == "needs_browser_network_trace":
        parse_status = "partial"
        quality = "low_quality"
        quality_reason = extraction["extraction_reason"]
    elif is_image_backed and not detail_asset_urls:
        parse_status = "partial"
        quality = "low_quality"
        quality_reason = "detail content is image-backed; image indicators found but no extractable URLs"
    elif is_image_backed and detail_asset_urls:
        parse_status = "partial"
        quality = "low_quality"
        quality_reason = "detail content is image-backed; image asset captured but text extraction not available"
    elif text_content.strip():
        parse_status = "success"
        quality = "usable"
        quality_reason = None
    else:
        parse_status = "partial"
        quality = "low_quality"
        quality_reason = "no text content and no image assets found"

    # Determine canonical section
    canonical_section = CANONICAL_SECTION
    found_sections = [h for h in SECTION_CANDIDATES if h in page_title or h in text_content]
    if found_sections:
        canonical_section = found_sections[0]

    result = {
        "batch_no": _extract_batch_no(page_title, page_url),
        "source_type": "enterprise_admission_change",
        "source_format": "html_image_attachment",
        "source_title": page_title,
        "parent_notice_title": parent_notice_title,
        "parent_notice_url": parent_notice_url,
        "official_attachment_url": page_url,
        "canonical_section": canonical_section,
        "section_candidates": SECTION_CANDIDATES,
        "section_headings_found": section_headings,
        "parse_status": parse_status,
        "quality": quality,
        "quality_reason": quality_reason,
        "detail_asset_type": "image" if is_image_backed else "text",
        "detail_asset_urls": detail_asset_urls or image_urls,
        "detail_asset_downloaded": False,
        "detail_asset_path": None,
        "text_snippet": text_content[:500] if text_content else "",
        # V1.1: Comprehensive extraction fields
        "image_asset_urls": extraction["image_asset_urls"],
        "linked_asset_urls": extraction["linked_asset_urls"],
        "iframe_urls": extraction["iframe_urls"],
        "script_asset_urls": extraction["script_asset_urls"],
        "api_candidate_urls": extraction["api_candidate_urls"],
        "cms_file_urls": extraction["cms_file_urls"],
        "extraction_status": extraction["extraction_status"],
        "extraction_reason": extraction["extraction_reason"],
    }

    return result


def _guess_title_from_html(html: str) -> str:
    """Fallback: extract title from <title> tag or h1."""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return m.group(1).strip()
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return ""


def _extract_batch_no(title: str, url: str) -> int:
    """Extract batch number from title or URL."""
    m = re.search(r"第(\d+)批", title)
    if m:
        return int(m.group(1))
    m = re.search(r"第(\d+)批", url)
    if m:
        return int(m.group(1))
    return 0


def process_attachment(
    batch_no: int,
    attachment_local_path: Path,
    attachment_url: str,
    parent_notice_url: str = "",
    parent_notice_title: str = "",
    output_dir: Optional[Path] = None,
) -> dict:
    """
    Process a downloaded enterprise admission attachment.

    Reads the attachment file (HTML), parses it, and writes evidence JSON.
    """
    if not attachment_local_path.exists():
        return {
            "batch_no": batch_no,
            "source_type": "enterprise_admission_change",
            "source_format": "html_image_attachment",
            "parse_status": "error",
            "quality": "unusable",
            "quality_reason": f"attachment file not found: {attachment_local_path}",
        }

    try:
        html = attachment_local_path.read_text("utf-8", errors="replace")
    except Exception as e:
        return {
            "batch_no": batch_no,
            "source_type": "enterprise_admission_change",
            "source_format": "html_image_attachment",
            "parse_status": "error",
            "quality": "unusable",
            "quality_reason": f"failed to read attachment: {e}",
        }

    result = parse_enterprise_admission_page(
        html=html,
        page_url=attachment_url,
        parent_notice_url=parent_notice_url,
        parent_notice_title=parent_notice_title,
    )
    result["batch_no"] = batch_no

    # Save evidence JSON
    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = output_dir / f"batch_{batch_no}_enterprise_admission_evidence.json"
        with open(evidence_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def main():
    """CLI entry point for testing."""
    import sys, argparse
    p = argparse.ArgumentParser(description="Parse MIIT enterprise admission change HTML attachment")
    p.add_argument("--input", type=str, help="Path to downloaded HTML file")
    p.add_argument("--url", type=str, default="", help="Original URL of the attachment")
    p.add_argument("--parent-url", type=str, default="", help="Parent notice URL")
    p.add_argument("--parent-title", type=str, default="", help="Parent notice title")
    p.add_argument("--format", choices=["terminal", "json"], default="terminal")
    args = p.parse_args()

    if not args.input:
        p.error("--input is required")

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[ERROR] File not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    html = input_path.read_text("utf-8", errors="replace")
    result = parse_enterprise_admission_page(
        html=html,
        page_url=args.url,
        parent_notice_url=args.parent_url,
        parent_notice_title=args.parent_title,
    )

    if args.format == "json":
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"\n[Summary] 企业准入变更解析")
        print(f"  Title: {result['source_title'][:80]}")
        print(f"  Section: {result['canonical_section']}")
        print(f"  Parse Status: {result['parse_status']}")
        print(f"  Quality: {result['quality']}")
        print(f"  Reason: {result['quality_reason']}")
        print(f"  Image URLs: {len(result['detail_asset_urls'])}")
        print(f"  Headings: {result['section_headings_found']}")


if __name__ == "__main__":
    main()
