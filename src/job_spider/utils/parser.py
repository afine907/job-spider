"""HTML parsing utilities."""

from typing import Any

from parsel import Selector


def parse_html(html: str | bytes, base_url: str = "") -> Selector:
    """Parse HTML content into a Selector.

    Args:
        html: HTML content
        base_url: Base URL for resolving relative URLs

    Returns:
        Parsel Selector object
    """
    if isinstance(html, bytes):
        html = html.decode("utf-8", errors="replace")
    return Selector(text=html, base_url=base_url)


def extract_text(selector: Selector, xpath: str = None, css: str = None) -> str:
    """Extract text from a selector.

    Args:
        selector: Parsel Selector
        xpath: XPath expression
        css: CSS selector

    Returns:
        Extracted text, stripped of whitespace
    """
    if xpath:
        result = selector.xpath(xpath).get()
    elif css:
        result = selector.css(css).get()
    else:
        result = selector.get()

    return result.strip() if result else ""


def extract_all_text(selector: Selector, xpath: str = None, css: str = None) -> list[str]:
    """Extract all matching texts from a selector.

    Args:
        selector: Parsel Selector
        xpath: XPath expression
        css: CSS selector

    Returns:
        List of extracted texts
    """
    if xpath:
        results = selector.xpath(xpath).getall()
    elif css:
        results = selector.css(css).getall()
    else:
        results = [selector.get()]

    return [r.strip() for r in results if r.strip()]


def extract_links(selector: Selector, base_url: str = "") -> list[dict[str, str]]:
    """Extract all links from a selector.

    Args:
        selector: Parsel Selector
        base_url: Base URL for resolving relative URLs

    Returns:
        List of dicts with 'text' and 'href' keys
    """
    links = []
    for a in selector.css("a"):
        href = a.css("::attr(href)").get()
        text = a.css("::text").get()

        if href:
            # Resolve relative URLs
            if base_url and not href.startswith(("http://", "https://")):
                from urllib.parse import urljoin
                href = urljoin(base_url, href)

            links.append({
                "text": text.strip() if text else "",
                "href": href,
            })

    return links


def extract_attribute(
    selector: Selector,
    attr: str,
    xpath: str = None,
    css: str = None,
) -> str:
    """Extract an attribute value from a selector.

    Args:
        selector: Parsel Selector
        attr: Attribute name
        xpath: XPath expression
        css: CSS selector

    Returns:
        Attribute value
    """
    if xpath:
        result = selector.xpath(xpath).attrib.get(attr, "")
    elif css:
        result = selector.css(css).attrib.get(attr, "")
    else:
        result = selector.attrib.get(attr, "")

    return result.strip() if result else ""
