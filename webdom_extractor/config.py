"""Configuration models for WebDOM Extractor.

This module defines configuration classes using Pydantic for robust
type validation and serialization.
"""

import os
from typing import Dict, List, Optional, Union
from pydantic import BaseModel, Field, validator

DEFAULT_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".webdom", "config.json")


class ExtractionConfig(BaseModel):
    """Configuration for content extraction."""

    preserve_images: bool = True
    extract_comments: bool = False
    ignore_links: bool = False
    min_text_length: int = 25
    strip_html_comments: bool = True
    extract_metadata: bool = True
    sanitize_content: bool = True
    detect_encoding: bool = True
    follow_redirects: bool = True
    timeout_seconds: int = 30
    user_agent: str = "WebDOM-Extractor/1.0"
    custom_headers: Optional[Dict[str, str]] = None

    @validator("min_text_length")
    def validate_min_text_length(cls, v):
        """Validate minimum text length."""
        if v < 0:
            raise ValueError("min_text_length must be non-negative")
        return v

    @validator("timeout_seconds")
    def validate_timeout(cls, v):
        """Validate timeout."""
        if v <= 0:
            raise ValueError("timeout_seconds must be positive")
        return v


class FormattingConfig(BaseModel):
    """Configuration for content formatting."""

    line_width: Optional[int] = 80
    heading_style: str = "atx"  # atx or setext
    wrap_blocks: bool = True
    code_block_style: str = "fenced"  # fenced or indented
    preserve_line_breaks: bool = False
    preserve_emphasis: bool = True
    include_metadata_header: bool = True
    add_title_heading: bool = True
    add_source_url: bool = True
    add_date: bool = True

    @validator("line_width")
    def validate_line_width(cls, v):
        """Validate line width."""
        if v is not None and v < 20:
            raise ValueError("line_width must be at least 20 if specified")
        return v


class CacheConfig(BaseModel):
    """Configuration for content caching."""

    enabled: bool = True
    ttl_seconds: int = 86400  # 24 hours
    max_size: int = 1_000_000_000  # 1GB
    cache_dir: Optional[str] = None

    @validator("ttl_seconds")
    def validate_ttl(cls, v):
        """Validate TTL."""
        if v < 0:
            raise ValueError("ttl_seconds must be non-negative")
        return v

    @validator("max_size")
    def validate_max_size(cls, v):
        """Validate max size."""
        if v < 0:
            raise ValueError("max_size must be non-negative")
        return v


class ParallelConfig(BaseModel):
    """Configuration for parallel processing."""

    enabled: bool = True
    max_workers: int = 5
    max_retries: int = 3
    retry_delay_seconds: int = 1

    @validator("max_workers")
    def validate_max_workers(cls, v):
        """Validate max workers."""
        if v <= 0:
            raise ValueError("max_workers must be positive")
        return v


class Config(BaseModel):
    """Main configuration model for WebDOM Extractor."""

    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    formatting: FormattingConfig = Field(default_factory=FormattingConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    parallel: ParallelConfig = Field(default_factory=ParallelConfig)
    postlight_parser_path: Optional[str] = None
    log_level: str = "INFO"

    @validator("log_level")
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v.upper()
