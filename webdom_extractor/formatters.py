"""Formatters for WebDOM Extractor.

This module provides functionality to convert extracted HTML content
to different output formats including Markdown, plain text, and JSON.
"""

import enum
import json
import logging
import textwrap
from html import unescape
from typing import Any, Dict, Optional, Union

import bleach
from html2text import HTML2Text

logger = logging.getLogger(__name__)


class OutputFormat(str, enum.Enum):
    """Supported output formats."""

    JSON = "json"
    MARKDOWN = "markdown"
    TEXT = "text"
    HTML = "html"


class MarkdownFormatter:
    """Formatter for converting HTML to Markdown."""

    def __init__(
        self,
        body_width: Optional[int] = 80,
        heading_style: str = "atx",
        wrap_blocks: bool = True,
        code_block_style: str = "fenced",
        preserve_emphasis: bool = True,
    ):
        """Initialize the Markdown formatter.

        Args:
            body_width: Character width for line wrapping (None for no wrapping)
            heading_style: 'atx' (#) or 'setext' (====) style headings
            wrap_blocks: Whether to wrap text in blocks
            code_block_style: 'fenced' (```) or 'indented' (4 spaces) code blocks
            preserve_emphasis: Whether to preserve bold, italic, etc.
        """
        self.formatter = HTML2Text()
        self.formatter.body_width = body_width
        self.formatter.ignore_images = False
        self.formatter.ignore_links = False
        self.formatter.ignore_emphasis = not preserve_emphasis
        self.formatter.convert_charrefs = True
        self.formatter.wrap_links = False
        
        # Configure heading style
        self.formatter.use_atx_headers = (heading_style.lower() == "atx")
        
        # Configure code block style
        self.formatter.code_block_style = code_block_style
        
        # Configure wrapping
        if not wrap_blocks:
            self.formatter.body_width = 0
            
        logger.debug(f"Initialized MarkdownFormatter with body_width={body_width}")

    def convert(self, html: str) -> str:
        """Convert HTML to Markdown.

        Args:
            html: HTML content to convert

        Returns:
            str: Markdown formatted content
        """
        try:
            markdown = self.formatter.handle(html)
            # Clean up the markdown output
            markdown = unescape(markdown)
            markdown = self._cleanup_markdown(markdown)
            return markdown
        except Exception as e:
            logger.error(f"Error converting HTML to Markdown: {e}")
            # Fallback to a simplified conversion
            simple_formatter = HTML2Text()
            simple_formatter.ignore_images = True
            simple_formatter.ignore_links = True
            simple_formatter.ignore_emphasis = True
            return unescape(simple_formatter.handle(html))
            
    def _cleanup_markdown(self, markdown: str) -> str:
        """Clean up common issues in the generated Markdown.
        
        Args:
            markdown: Raw markdown to clean up
            
        Returns:
            str: Cleaned markdown
        """
        # Fix multiple consecutive blank lines
        import re
        markdown = re.sub(r'\n{3,}', '\n\n', markdown)
        
        # Fix list item spacing
        markdown = re.sub(r'(\n\s*\*.*\n)\n+(\s*\*)', r'\1\2', markdown)
        
        return markdown


class TextFormatter:
    """Formatter for converting HTML to plain text."""

    def __init__(
        self,
        body_width: Optional[int] = 80,
        preserve_line_breaks: bool = False,
    ):
        """Initialize the Text formatter.

        Args:
            body_width: Character width for line wrapping (None for no wrapping)
            preserve_line_breaks: Whether to preserve line breaks in the HTML
        """
        self.formatter = HTML2Text()
        self.formatter.body_width = body_width
        self.formatter.ignore_images = True
        self.formatter.ignore_links = True
        self.formatter.ignore_emphasis = True
        self.formatter.convert_charrefs = True
        self.formatter.ignore_tables = False
        self.formatter.inline_links = False
        self.formatter.protect_links = True
        self.formatter.unicode_snob = True
        self.formatter.preserve_newlines = preserve_line_breaks
        
        logger.debug(f"Initialized TextFormatter with body_width={body_width}")

    def convert(self, html: str) -> str:
        """Convert HTML to plain text.

        Args:
            html: HTML content to convert

        Returns:
            str: Plain text formatted content
        """
        try:
            # First, sanitize HTML to remove potentially harmful content
            html = bleach.clean(html, strip=True)
            
            # Convert to plain text
            text = self.formatter.handle(html)
            
            # Clean up the text output
            text = unescape(text)
            text = self._cleanup_text(text)
            
            return text
        except Exception as e:
            logger.error(f"Error converting HTML to plain text: {e}")
            # Fallback to a very basic conversion
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            return soup.get_text(separator="\n")
            
    def _cleanup_text(self, text: str) -> str:
        """Clean up the generated plain text.
        
        Args:
            text: Raw text to clean up
            
        Returns:
            str: Cleaned text
        """
        # Fix multiple consecutive blank lines
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove trailing whitespace
        text = "\n".join(line.rstrip() for line in text.splitlines())
        
        return text


class JsonFormatter:
    """Formatter for converting document data to JSON."""

    def __init__(self, pretty: bool = True):
        """Initialize the JSON formatter.

        Args:
            pretty: Whether to format the JSON with indentation
        """
        self.pretty = pretty
        logger.debug(f"Initialized JsonFormatter with pretty={pretty}")

    def convert(self, data: Dict[str, Any]) -> str:
        """Convert data to JSON.

        Args:
            data: Data to convert to JSON

        Returns:
            str: JSON formatted data
        """
        try:
            indent = 2 if self.pretty else None
            return json.dumps(
                data,
                indent=indent,
                ensure_ascii=False,
                default=self._json_serialize,
            )
        except Exception as e:
            logger.error(f"Error converting to JSON: {e}")
            # Fallback to a basic conversion with problematic fields removed
            safe_data = self._sanitize_for_json(data)
            return json.dumps(safe_data, ensure_ascii=False)
            
    def _json_serialize(self, obj: Any) -> Any:
        """Custom JSON serializer for handling non-serializable objects.
        
        Args:
            obj: Object to serialize
            
        Returns:
            Serializable version of the object
        """
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        if hasattr(obj, "to_dict"):
            return obj.to_dict()
        return str(obj)
            
    def _sanitize_for_json(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Remove fields that could cause JSON serialization issues.
        
        Args:
            data: Data to sanitize
            
        Returns:
            Dict: Sanitized data
        """
        if not isinstance(data, dict):
            return {}
            
        result = {}
        for k, v in data.items():
            if isinstance(v, dict):
                result[k] = self._sanitize_for_json(v)
            elif isinstance(v, (str, int, float, bool, type(None))):
                result[k] = v
            elif isinstance(v, list):
                result[k] = [
                    self._sanitize_for_json(i) if isinstance(i, dict) else str(i)
                    for i in v
                ]
            else:
                # Convert anything else to string
                result[k] = str(v)
        return result


def format_content(
    html: str, 
    format_type: Union[OutputFormat, str], 
    **kwargs
) -> str:
    """Format HTML content to the specified output format.

    Args:
        html: HTML content to format
        format_type: Output format (OutputFormat enum or string)
        **kwargs: Additional formatting options

    Returns:
        str: Formatted content

    Raises:
        ValueError: If an unsupported format is specified
    """
    if isinstance(format_type, str):
        try:
            format_type = OutputFormat(format_type.lower())
        except ValueError:
            raise ValueError(
                f"Unsupported format: {format_type}. "
                f"Use one of {', '.join([f.value for f in OutputFormat])}"
            )
    
    logger.debug(f"Formatting content to {format_type.value}")
    
    if format_type == OutputFormat.MARKDOWN:
        formatter = MarkdownFormatter(**kwargs)
        return formatter.convert(html)
    elif format_type == OutputFormat.TEXT:
        formatter = TextFormatter(**kwargs)
        return formatter.convert(html)
    elif format_type == OutputFormat.HTML:
        # Just return sanitized HTML
        return bleach.clean(
            html,
            tags=bleach.sanitizer.ALLOWED_TAGS + [
                'div', 'span', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                'table', 'thead', 'tbody', 'tr', 'th', 'td',
                'ul', 'ol', 'li', 'dl', 'dt', 'dd',
                'img', 'figure', 'figcaption', 'main', 'article',
                'section', 'aside', 'details', 'summary'
            ],
            attributes={
                **bleach.sanitizer.ALLOWED_ATTRIBUTES,
                'img': ['src', 'alt', 'title', 'width', 'height'],
                'a': ['href', 'title', 'rel'],
                '*': ['class', 'id'],
            },
        )
    else:
        raise ValueError(f"Formatting for {format_type} not implemented")
