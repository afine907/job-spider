"""Utility functions."""

from .http import HttpClient, create_client
from .parser import parse_html, extract_text, extract_links

__all__ = [
    "HttpClient",
    "create_client",
    "parse_html",
    "extract_text",
    "extract_links",
]
