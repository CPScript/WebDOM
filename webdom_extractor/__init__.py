import logging
from typing import Dict, Optional

from webdom_extractor.extractor import Extractor, ExtractionConfig
from webdom_extractor.document import Document
from webdom_extractor.formatters import OutputFormat

__version__ = "1.0.0"
__author__ = "CPScript"
__license__ = "MIT"

# Configure logging
logging.getLogger(__name__).addHandler(logging.NullHandler())


def extract_url(url: str, config: Optional[Dict] = None) -> Document:
    """Extract content from a URL.

    A convenience function that creates an Extractor instance and extracts
    content from the specified URL.

    Args:
        url: The URL to extract content from
        config: Optional extraction configuration parameters

    Returns:
        Document: The extracted document

    Examples:
        >>> doc = extract_url("https://example.com/article")
        >>> print(doc.to_markdown())
    """
    extractor = Extractor(config=config)
    return extractor.extract_url(url)


def extract_html(html: str, url: Optional[str] = None, config: Optional[Dict] = None) -> Document:
    """Extract content from HTML.

    A convenience function that creates an Extractor instance and extracts
    content from the provided HTML string.

    Args:
        html: The HTML content to extract from
        url: Optional source URL for reference
        config: Optional extraction configuration parameters

    Returns:
        Document: The extracted document

    Examples:
        >>> with open("page.html", "r") as f:
        ...     html = f.read()
        >>> doc = extract_html(html, url="https://example.com/article")
        >>> print(doc.to_text())
    """
    extractor = Extractor(config=config)
    return extractor.extract_html(html, url=url)


__all__ = [
    "Extractor",
    "Document",
    "OutputFormat",
    "ExtractionConfig",
    "extract_url",
    "extract_html",
]
