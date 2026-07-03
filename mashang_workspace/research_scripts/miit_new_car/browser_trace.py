"""
Playwright browser network trace fallback for datainfo page resource discovery.

When static HTTP download of a datainfo page fails (404, etc.), this module
uses a headless Chrome to:
  1. Open the parent notice page
  2. Click the datainfo attachment link
  3. Capture all network requests/responses
  4. Save the rendered page content
  5. Feed page.content() back to datainfo_resource_extractor
  6. Output structured browser_trace_evidence

Design:
  - Graceful degradation if playwright is not installed or browsers missing
  - Handles target="_blank" (new page) and same-page navigation
  - Network listener captures all resource URLs (images, cms_files, API)

Usage:
  from browser_trace import run_browser_trace
  evidence = run_browser_trace(
      parent_notice_url='https://...',
      attachment_title='拟发布的新准入车辆...',
      attachment_url='https://...datainfo/...html',
  )
"""

import re
from typing import Optional

BROWSER_TRACE_EVIDENCE_FIELDS = [
    "browser_final_url",
    "browser_page_status",
    "browser_page_title",
    "browser_content_length",
    "browser_resource_urls",
    "browser_image_urls",
    "browser_api_urls",
    "browser_rendered_html",
    "browser_error",
]

RE_CMS_RESOURCE = re.compile(
    r"(/cms_files/|/webfile/|/upload/|/datainfo/|/picture/)", re.IGNORECASE
)
RE_IMAGE_EXT = re.compile(r"\.(jpg|jpeg|png|gif|webp|bmp|svg)(\?|$)", re.IGNORECASE)
RE_JSON_API = re.compile(r"\.json(\?|$)", re.IGNORECASE)


def _empty_evidence() -> dict:
    return {
        "browser_final_url": "",
        "browser_page_status": "",
        "browser_page_title": "",
        "browser_content_length": 0,
        "browser_resource_urls": [],
        "browser_image_urls": [],
        "browser_api_urls": [],
        "browser_rendered_html": "",
        "browser_error": "",
    }


def _classify_url(url: str) -> tuple[bool, bool, bool]:
    """Classify a URL. Returns (is_resource, is_image, is_api)."""
    is_resource = bool(RE_CMS_RESOURCE.search(url))
    is_image = bool(RE_IMAGE_EXT.search(url))
    is_api = bool(RE_JSON_API.search(url)) or "api" in url.lower()
    return is_resource, is_image, is_api


def run_browser_trace(
    parent_notice_url: str,
    attachment_title: str = "",
    attachment_url: str = "",
    timeout: int = 30000,
    headless: bool = True,
) -> dict:
    """
    Use Playwright headless Chrome to navigate to the parent notice page,
    click the datainfo attachment link, and capture all network resources.

    Args:
        parent_notice_url: URL of the parent notice (detail) page
        attachment_title: Partial text of the attachment link to click
        attachment_url: URL of the attachment (used to find link by href)
        timeout: Navigation timeout in ms
        headless: Whether to run browser in headless mode

    Returns:
        browser_trace_evidence dict with fields:
          browser_final_url, browser_page_status, browser_page_title,
          browser_content_length, browser_resource_urls, browser_image_urls,
          browser_api_urls, browser_rendered_html, browser_error
    """
    evidence = _empty_evidence()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        evidence["browser_page_status"] = "browser_trace_failed"
        evidence["browser_error"] = "playwright Python SDK not available (pip install playwright)"
        return evidence

    collected_resources: set[str] = set()
    collected_images: set[str] = set()
    collected_apis: set[str] = set()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
            context = browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/148.0.0.0 Safari/537.36"
                ),
            )

            page = context.new_page()

            # Network response listener (track resources from all pages)
            def on_response(response):
                url = response.url
                if not url.startswith("http"):
                    return
                is_resource, is_image, is_api = _classify_url(url)
                if is_resource:
                    collected_resources.add(url)
                if is_image:
                    collected_images.add(url)
                if is_api:
                    collected_apis.add(url)

            page.on("response", on_response)

            # Step 1: Navigate to parent notice page
            try:
                page.goto(parent_notice_url, wait_until="networkidle", timeout=timeout)
            except Exception as e:
                evidence["browser_page_status"] = "navigation_failed"
                evidence["browser_error"] = f"parent page navigation failed: {e}"
                browser.close()
                return evidence

            # Step 2: Find and click the datainfo attachment link
            link_clicked = False
            click_error = ""
            datainfo_page = None

            # Helper: try clicking a locator, return True if successful
            def _try_click(locator_spec, strategy_name: str) -> bool:
                nonlocal datainfo_page, link_clicked, click_error
                try:
                    link = None
                    if isinstance(locator_spec, str):
                        link = page.locator(locator_spec)
                    else:
                        link = locator_spec
                    if link.count() == 0:
                        return False
                    # Use expect_popup to capture target="_blank" navigation
                    with page.expect_popup() as popup_info:
                        link.first.click(timeout=5000)
                    datainfo_page = popup_info.value
                    link_clicked = True
                    return True
                except Exception as e:
                    click_error = f"{strategy_name}: {e}"
                    return False

            # Determine href fragment for precise matching
            href_fragment = ""
            if attachment_url:
                # Use last 40 chars of the URL path for matching
                path = attachment_url.rstrip("/")
                if "/datainfo/" in path:
                    href_fragment = path.split("/datainfo/")[1][:40]
                else:
                    href_fragment = path.rsplit("/", 1)[-1][:40]

            # Strategy A: Match by href fragment (most precise)
            if not link_clicked and href_fragment:
                _try_click(f'a[href*="{href_fragment}"]', "href_match")

            # Strategy B: Match by text content (visible link text)
            if not link_clicked and attachment_title:
                # Try progressively smaller fragments
                for length in (30, 20, 15, 10):
                    fragment = attachment_title[:length]
                    if len(fragment) < 5:
                        continue
                    if _try_click(f"a:has-text('{fragment}')", f"text_match_{length}"):
                        break

            # Strategy C: Click any datainfo link
            if not link_clicked:
                _try_click('a[href*="/datainfo/"]', "any_datainfo_link")

            # Strategy D: Click any anchor with href containing key path segments
            if not link_clicked and href_fragment and len(href_fragment) > 10:
                _try_click(f'a[href*="{href_fragment[:20]}"]', "href_fallback")

            if not link_clicked:
                browser.close()
                evidence["browser_page_status"] = "click_failed"
                evidence["browser_error"] = (
                    f"could not find datainfo link to click; "
                    f"title='{attachment_title[:60]}', url='{attachment_url[:80]}'"
                )
                return evidence

            # Step 3: Wait for the datainfo page to load
            try:
                datainfo_page.on("response", on_response)
                datainfo_page.wait_for_load_state("networkidle", timeout=timeout)
            except Exception:
                pass

            # Step 4: Try to interact with Image-related elements
            try:
                for selector in [
                    "text=Image",
                    "text=详细信息",
                    "text=图片",
                    "text=查看图片",
                    "#zoom img",
                    ".content img",
                ]:
                    try:
                        els = datainfo_page.locator(selector)
                        if els.count() > 0:
                            els.first.click(timeout=2000)
                            datainfo_page.wait_for_timeout(500)
                    except Exception:
                        pass
            except Exception:
                pass

            # Step 5: Collect final state
            try:
                final_url = datainfo_page.url
            except Exception:
                final_url = ""
            try:
                final_title = datainfo_page.title()
            except Exception:
                final_title = ""
            try:
                rendered_html = datainfo_page.content()
            except Exception:
                rendered_html = ""

            browser.close()

            evidence["browser_final_url"] = final_url
            evidence["browser_page_title"] = final_title
            evidence["browser_content_length"] = len(rendered_html)
            evidence["browser_rendered_html"] = rendered_html
            evidence["browser_resource_urls"] = sorted(collected_resources)
            evidence["browser_image_urls"] = sorted(collected_images)
            evidence["browser_api_urls"] = sorted(collected_apis)

            # Determine page status
            if not final_url:
                evidence["browser_page_status"] = "error"
                evidence["browser_error"] = "no final URL after click"
            elif "404" in final_title or "404" in final_url:
                evidence["browser_page_status"] = "page_error"
                evidence["browser_error"] = (
                    f"datainfo URL returned 404 in browser "
                    f"(final_url={final_url[:120]})"
                )
            elif len(rendered_html) < 500:
                evidence["browser_page_status"] = "page_error"
                evidence["browser_error"] = (
                    f"rendered content too small ({len(rendered_html)} bytes)"
                )
            else:
                evidence["browser_page_status"] = "success"

    except Exception as e:
        evidence["browser_page_status"] = "browser_trace_failed"
        evidence["browser_error"] = f"browser trace exception: {e}"

    return evidence


def run_browser_trace_and_extract(
    parent_notice_url: str,
    attachment_title: str = "",
    attachment_url: str = "",
    timeout: int = 30000,
    headless: bool = True,
) -> dict:
    """
    Run browser trace, then feed rendered HTML back to datainfo_resource_extractor.

    Returns combined evidence:
      - browser_trace_evidence (the raw trace output)
      - datainfo_extraction (output of datainfo_resource_extractor on rendered HTML)
      - integration_status: "full_success" | "trace_only" | "trace_failed"
    """
    trace = run_browser_trace(
        parent_notice_url=parent_notice_url,
        attachment_title=attachment_title,
        attachment_url=attachment_url,
        timeout=timeout,
        headless=headless,
    )

    result = {
        "browser_trace_evidence": trace,
        "datainfo_extraction": None,
        "integration_status": "trace_failed",
    }

    if trace["browser_page_status"] == "success" and trace.get("browser_rendered_html"):
        from enterprise_admission_parser import datainfo_resource_extractor

        extraction = datainfo_resource_extractor(
            datainfo_html=trace["browser_rendered_html"],
            datainfo_url=trace["browser_final_url"] or attachment_url,
            parent_notice_url=parent_notice_url,
        )
        result["datainfo_extraction"] = extraction

        if extraction["extraction_status"] == "success":
            result["integration_status"] = "full_success"
        else:
            result["integration_status"] = "trace_only"
    elif trace["browser_page_status"] == "success":
        result["integration_status"] = "trace_only"
        result["datainfo_extraction"] = datainfo_resource_extractor(
            datainfo_html="",
            datainfo_url=trace["browser_final_url"] or attachment_url,
            parent_notice_url=parent_notice_url,
        )
    else:
        result["integration_status"] = "trace_failed"

    return result
