import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field, validator

from webdom_extractor.formatters import OutputFormat, format_content

logger = logging.getLogger(__name__)


class Metadata(BaseModel):
    """Metadata extracted from a web page."""

    title: Optional[str] = None
    author: Optional[str] = None
    date_published: Optional[datetime] = None
    lead_image_url: Optional[str] = None
    dek: Optional[str] = None
    next_page_url: Optional[str] = None
    url: Optional[str] = None
    domain: Optional[str] = None
    excerpt: Optional[str] = None
    word_count: Optional[int] = None
    direction: str = "ltr"
    total_pages: int = 1
    rendered_pages: int = 1
    site_name: Optional[str] = None
    language: Optional[str] = None
    description: Optional[str] = None
    publisher: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    extraction_timestamp: datetime = Field(default_factory=datetime.now)

    @validator("date_published", pre=True)
    def parse_datetime(cls, v):
        """Parse datetime from various formats."""
        if v is None:
            return None
        if isinstance(v, datetime):
            return v
        try:
            if isinstance(v, str):
                # Try different date formats
                for fmt in [
                    "%Y-%m-%dT%H:%M:%S.%fZ",  # ISO format with microseconds
                    "%Y-%m-%dT%H:%M:%SZ",      # ISO format without microseconds
                    "%Y-%m-%d %H:%M:%S",       # Simple format
                    "%Y-%m-%d",                # Just date
                ]:
                    try:
                        return datetime.strptime(v, fmt)
                    except ValueError:
                        continue
            raise ValueError(f"Invalid datetime format: {v}")
        except Exception as e:
            logger.warning(f"Failed to parse datetime: {v}, error: {e}")
            return None


class Content(BaseModel):
    """Content extracted from a web page in different formats."""

    html: str
    markdown: Optional[str] = None
    text: Optional[str] = None
    json: Optional[Dict[str, Any]] = None

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


class Document:
    """Represents an extracted web document with content and metadata."""

    def __init__(
        self,
        content_html: str,
        metadata: Optional[Dict[str, Any]] = None,
        url: Optional[str] = None,
    ):
        """Initialize a Document with HTML content and optional metadata.

        Args:
            content_html: The extracted HTML content
            metadata: Optional metadata about the document
            url: Optional source URL
        """
        self.content = Content(html=content_html)
        
        # Initialize metadata
        meta_dict = metadata or {}
        if url and "url" not in meta_dict:
            meta_dict["url"] = url
            
        self.metadata = Metadata(**meta_dict)
        
        logger.debug(f"Document initialized with {len(content_html)} bytes of HTML")

    def to_dict(self) -> Dict[str, Any]:
        """Convert the document to a dictionary.

        Returns:
            Dict: Dictionary representation of the document
        """
        return {
            "metadata": self.metadata.dict(exclude_none=True),
            "content": {
                "html": self.content.html,
                "markdown": self.content.markdown,
                "text": self.content.text,
            },
        }

    def to_json(self, pretty: bool = False) -> str:
        """Convert the document to a JSON string.

        Args:
            pretty: Whether to format the JSON for readability

        Returns:
            str: JSON string representation of the document
        """
        indent = 2 if pretty else None
        return json.dumps(
            self.to_dict(),
            default=lambda o: o.isoformat() if isinstance(o, datetime) else None,
            indent=indent,
        )

    def to_markdown(self) -> str:
        """Get the document content as Markdown.

        Returns:
            str: Markdown representation of the document
        """
        if self.content.markdown is None:
            self.content.markdown = format_content(
                self.content.html, OutputFormat.MARKDOWN
            )
        return self.content.markdown

    def to_text(self) -> str:
        """Get the document content as plain text.

        Returns:
            str: Plain text representation of the document
        """
        if self.content.text is None:
            self.content.text = format_content(self.content.html, OutputFormat.TEXT)
        return self.content.text

    def save(
        self,
        path: Union[str, Path],
        format: str = "json",
        pretty: bool = True,
    ) -> None:
        """Save the document to a file.

        Args:
            path: Path to save the file to
            format: Format to save as ('json', 'markdown', 'text', 'html')
            pretty: Whether to format for readability (for JSON)

        Raises:
            ValueError: If an unsupported format is specified
        """
        if isinstance(path, str):
            path = Path(path)

        # Create directory if it doesn't exist
        path.parent.mkdir(parents=True, exist_ok=True)

        format = format.lower()
        
        if format == "json":
            content = self.to_json(pretty=pretty)
        elif format == "markdown" or format == "md":
            content = self.to_markdown()
        elif format == "text" or format == "txt":
            content = self.to_text()
        elif format == "html":
            content = self.content.html
        else:
            raise ValueError(
                f"Unsupported format: {format}. "
                "Use 'json', 'markdown', 'text', or 'html'."
            )

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
            
        logger.info(f"Document saved to {path} in {format} format")

    def __repr__(self) -> str:
        """Get string representation of the document.

        Returns:
            str: String representation
        """
        title = self.metadata.title or "[No Title]"
        url = self.metadata.url or "[No URL]"
        return f"Document(title='{title}', url='{url}')"
