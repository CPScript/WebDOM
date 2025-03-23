import asyncio
import hashlib
import json
import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import aiohttp
import diskcache
import requests
import validators
from bs4 import BeautifulSoup
from pydantic import ValidationError

from webdom_extractor.config import Config, ExtractionConfig
from webdom_extractor.document import Document

logger = logging.getLogger(__name__)


class ExtractionError(Exception):
    """Exception raised when content extraction fails."""

    pass


class PostlightParserError(ExtractionError):
    """Exception raised when the Postlight Parser fails."""

    pass


class FetchError(ExtractionError):
    """Exception raised when fetching a URL fails."""

    pass


class Extractor:
    """Main content extraction class.

    This class is responsible for extracting clean, readable content from
    web pages using the Postlight Parser.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        parser_path: Optional[str] = None,
    ):
        """Initialize the extractor with configuration.

        Args:
            config: Optional configuration dict
            parser_path: Optional path to the Postlight Parser executable

        Raises:
            ValueError: If parser_path is not provided and not found
        """
        # Parse configuration
        try:
            self.config = Config(**(config or {}))
        except ValidationError as e:
            logger.error(f"Invalid configuration: {e}")
            logger.warning("Using default configuration")
            self.config = Config()

        # Configure logging
        self._configure_logging()

        # Find parser path
        self.parser_path = parser_path or self.config.postlight_parser_path
        if not self.parser_path:
            self.parser_path = self._find_parser_path()

        # Validate parser path
        if not os.path.exists(self.parser_path):
            raise ValueError(
                f"Postlight Parser not found at {self.parser_path}. "
                "Install it with: npm install -g @postlight/parser"
            )

        # Initialize cache if enabled
        if self.config.cache.enabled:
            self._init_cache()
        else:
            self.cache = None

        logger.info(f"Extractor initialized with parser at {self.parser_path}")

    def _configure_logging(self) -> None:
        """Configure logging based on configuration."""
        log_level = getattr(logging, self.config.log_level)
        root_logger = logging.getLogger("webdom_extractor")
        
        # Only configure if handlers don't exist already
        if not root_logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            handler.setFormatter(formatter)
            root_logger.addHandler(handler)
            
        root_logger.setLevel(log_level)

    def _init_cache(self) -> None:
        """Initialize the content cache."""
        cache_dir = self.config.cache.cache_dir
        if not cache_dir:
            cache_dir = os.path.join(os.path.expanduser("~"), ".webdom", "cache")
            
        os.makedirs(cache_dir, exist_ok=True)
        
        self.cache = diskcache.Cache(
            cache_dir,
            size_limit=self.config.cache.max_size,
            cull_limit=10,  # Remove 10% when size limit is reached
        )
        
        logger.info(f"Cache initialized at {cache_dir}")

    def _find_parser_path(self) -> str:
        """Find the Postlight Parser executable path.

        Returns:
            str: Path to the Postlight Parser executable

        Raises:
            ValueError: If parser is not found
        """
        # Common installation paths
        common_paths = [
            "/usr/local/bin/postlight-parser",
            "/usr/bin/postlight-parser",
            "/opt/homebrew/bin/postlight-parser",
            os.path.join(os.path.expanduser("~"), "node_modules", ".bin", "postlight-parser"),
        ]
        
        # For Windows
        if os.name == "nt":
            common_paths.extend([
                r"C:\Program Files\nodejs\postlight-parser.cmd",
                r"C:\Program Files (x86)\nodejs\postlight-parser.cmd",
                os.path.join(os.path.expanduser("~"), "AppData", "Roaming", "npm", "postlight-parser.cmd"),
            ])
            
        # Try to find in PATH
        try:
            if os.name == "nt":
                result = subprocess.run(
                    ["where", "postlight-parser"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                paths = result.stdout.strip().split("\n")
                if paths:
                    return paths[0]
            else:
                result = subprocess.run(
                    ["which", "postlight-parser"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                return result.stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            logger.debug("Could not find postlight-parser in PATH")
            
        # Check common paths
        for path in common_paths:
            if os.path.exists(path):
                return path
                
        raise ValueError(
            "Postlight Parser not found. Install it with: "
            "npm install -g @postlight/parser"
        )

    def extract_url(self, url: str) -> Document:
        """Extract content from a URL.

        Args:
            url: URL to extract content from

        Returns:
            Document: Extracted document

        Raises:
            ValueError: If URL is invalid
            FetchError: If fetching the URL fails
            ExtractionError: If extraction fails
        """
        # Validate URL
        if not validators.url(url):
            raise ValueError(f"Invalid URL: {url}")
            
        logger.info(f"Extracting content from URL: {url}")
        
        # Check cache if enabled
        if self.cache:
            cache_key = self._get_cache_key(url)
            cached_data = self.cache.get(cache_key)
            if cached_data:
                logger.info(f"Using cached content for {url}")
                return self._document_from_cache(cached_data)
        
        # Run parser
        try:
            parser_result = self._run_parser(url)
            
            # Cache result if enabled
            if self.cache:
                self.cache.set(
                    cache_key,
                    parser_result,
                    expire=self.config.cache.ttl_seconds,
                )
                
            return self._create_document(parser_result, url)
        except Exception as e:
            logger.error(f"Error extracting content from {url}: {e}")
            # Try fallback method
            logger.info(f"Attempting fallback extraction for {url}")
            return self._fallback_extraction(url)

    def extract_html(self, html: str, url: Optional[str] = None) -> Document:
        """Extract content from HTML.

        Args:
            html: HTML content to extract from
            url: Optional source URL for reference

        Returns:
            Document: Extracted document

        Raises:
            ExtractionError: If extraction fails
        """
        logger.info(f"Extracting content from HTML ({len(html)} bytes)")
        
        if not html:
            raise ExtractionError("Empty HTML content")
            
        # Save HTML to temporary file for parser
        import tempfile
        
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".html", delete=False
        ) as f:
            f.write(html)
            temp_path = f.name
            
        try:
            # Run parser on the temporary file
            file_url = f"file://{temp_path}"
            parser_result = self._run_parser(file_url)
            
            # If URL was provided, update the result
            if url:
                parser_result["url"] = url
                
            return self._create_document(parser_result, url)
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except Exception as e:
                logger.warning(f"Failed to remove temporary file {temp_path}: {e}")

    def extract_batch(
        self, urls: List[str], max_workers: Optional[int] = None
    ) -> List[Tuple[str, Optional[Document]]]:
        """Extract content from multiple URLs in parallel.

        Args:
            urls: List of URLs to extract content from
            max_workers: Maximum number of parallel workers

        Returns:
            List[Tuple[str, Optional[Document]]]: List of (url, document) pairs
        """
        if not urls:
            return []
            
        workers = max_workers or self.config.parallel.max_workers
        logger.info(f"Batch extracting {len(urls)} URLs with {workers} workers")
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            results = list(executor.map(self._safe_extract, urls))
            
        return list(zip(urls, results))

    async def extract_batch_async(
        self, urls: List[str], max_workers: Optional[int] = None
    ) -> List[Tuple[str, Optional[Document]]]:
        """Extract content from multiple URLs asynchronously.

        Args:
            urls: List of URLs to extract content from
            max_workers: Maximum number of parallel workers

        Returns:
            List[Tuple[str, Optional[Document]]]: List of (url, document) pairs
        """
        if not urls:
            return []
            
        workers = max_workers or self.config.parallel.max_workers
        logger.info(f"Async batch extracting {len(urls)} URLs with {workers} tasks")
        
        tasks = []
        semaphore = asyncio.Semaphore(workers)
        
        async def _extract_with_semaphore(url):
            async with semaphore:
                return url, await self._safe_extract_async(url)
                
        for url in urls:
            tasks.append(_extract_with_semaphore(url))
            
        return await asyncio.gather(*tasks)

    def _run_parser(self, url: str) -> Dict[str, Any]:
        """Run the Postlight Parser on a URL.

        Args:
            url: URL to parse

        Returns:
            Dict: Parser result

        Raises:
            PostlightParserError: If parser fails
        """
        logger.debug(f"Running Postlight Parser on {url}")
        
        try:
            result = subprocess.run(
                [self.parser_path, url],
                capture_output=True,
                text=True,
                check=True,
            )
            output = result.stdout
            
            # Extract JSON from output
            json_start = output.find("{")
            if json_start == -1:
                raise PostlightParserError(f"No JSON found in parser output: {output}")
                
            parser_result = json.loads(output[json_start:])
            
            # Check for parser error
            if "error" in parser_result:
                raise PostlightParserError(
                    f"Parser error: {parser_result.get('message', 'Unknown error')}"
                )
                
            return parser_result
        except subprocess.SubprocessError as e:
            error_output = getattr(e, "stderr", str(e))
            raise PostlightParserError(f"Parser process error: {error_output}")
        except json.JSONDecodeError as e:
            raise PostlightParserError(f"Invalid parser output: {e}")

    def _create_document(
        self, parser_result: Dict[str, Any], url: Optional[str] = None
    ) -> Document:
        """Create a Document from parser result.

        Args:
            parser_result: Parser result
            url: Optional source URL

        Returns:
            Document: Extracted document
        """
        content_html = parser_result.pop("content", "")
        
        # Use URL from parser result or provided URL
        final_url = parser_result.get("url") or url
        
        # Create document
        doc = Document(content_html, parser_result, final_url)
        
        logger.info(
            f"Created document: {doc.metadata.title or '[No Title]'} "
            f"({doc.metadata.word_count or 0} words)"
        )
        
        return doc

    def _get_cache_key(self, url: str) -> str:
        """Generate a cache key for a URL.

        Args:
            url: URL to generate cache key for

        Returns:
            str: Cache key
        """
        return hashlib.md5(url.encode("utf-8")).hexdigest()

    def _document_from_cache(self, cached_data: Dict[str, Any]) -> Document:
        """Create a Document from cached data.

        Args:
            cached_data: Cached parser result

        Returns:
            Document: Extracted document
        """
        content_html = cached_data.pop("content", "")
        return Document(content_html, cached_data)

    def _fallback_extraction(self, url: str) -> Document:
        """Fallback extraction method when parser fails.

        Args:
            url: URL to extract content from

        Returns:
            Document: Extracted document

        Raises:
            FetchError: If fetching fails
        """
        logger.info(f"Using fallback extraction for {url}")
        
        try:
            # Fetch the page
            headers = {"User-Agent": self.config.extraction.user_agent}
            if self.config.extraction.custom_headers:
                headers.update(self.config.extraction.custom_headers)
                
            response = requests.get(
                url,
                headers=headers,
                timeout=self.config.extraction.timeout_seconds,
                allow_redirects=self.config.extraction.follow_redirects,
            )
            response.raise_for_status()
            
            # Parse with BeautifulSoup
            html = response.text
            soup = BeautifulSoup(html, "lxml")
            
            # Extract metadata
            metadata = self._extract_fallback_metadata(soup, url, response)
            
            # Extract main content
            content_html = self._extract_fallback_content(soup)
            
            return Document(content_html, metadata, url)
        except requests.RequestException as e:
            raise FetchError(f"Failed to fetch {url}: {e}")
        except Exception as e:
            logger.error(f"Fallback extraction failed: {e}")
            # Create minimal document
            return Document(
                "<p>Content extraction failed</p>",
                {"url": url, "title": "Extraction Failed"},
                url,
            )

    def _extract_fallback_metadata(
        self, soup: BeautifulSoup, url: str, response: requests.Response
    ) -> Dict[str, Any]:
        """Extract metadata from HTML using fallback method.

        Args:
            soup: BeautifulSoup object
            url: Source URL
            response: HTTP response

        Returns:
            Dict: Metadata
        """
        metadata = {"url": url, "domain": url.split("//")[-1].split("/")[0]}
        
        # Title
        title_tag = soup.find("title")
        if title_tag:
            metadata["title"] = title_tag.text.strip()
            
        # Meta description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            metadata["excerpt"] = meta_desc.get("content", "")
            
        # Open Graph metadata
        og_title = soup.find("meta", property="og:title")
        if og_title:
            metadata["title"] = og_title.get("content", metadata.get("title", ""))
            
        og_desc = soup.find("meta", property="og:description")
        if og_desc:
            metadata["excerpt"] = og_desc.get("content", metadata.get("excerpt", ""))
            
        og_image = soup.find("meta", property="og:image")
        if og_image:
            metadata["lead_image_url"] = og_image.get("content", "")
            
        # Author
        author = soup.find("meta", attrs={"name": "author"})
        if author:
            metadata["author"] = author.get("content", "")
            
        # Count words in visible text
        visible_text = " ".join(soup.stripped_strings)
        metadata["word_count"] = len(visible_text.split())
        
        return metadata

    def _extract_fallback_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from HTML using fallback method.

        Args:
            soup: BeautifulSoup object

        Returns:
            str: Extracted HTML content
        """
        # Try to find main content container
        main_content = None
        
        # Check for common content containers
        for container in [
            soup.find("main"),
            soup.find("article"),
            soup.find(id="content"),
            soup.find(class_="content"),
            soup.find(id="main"),
            soup.find(class_="main"),
            soup.find(id="article"),
            soup.find(class_="article"),
        ]:
            if container:
                main_content = container
                break
                
        # If no content container found, use body
        if not main_content:
            main_content = soup.find("body")
            
            # Remove common noise elements
            for element in main_content.select(
                "nav, header, footer, aside, script, style, noscript, iframe"
            ):
                element.decompose()
                
        # Convert to string
        return str(main_content) if main_content else "<p>No content found</p>"

    def _safe_extract(self, url: str) -> Optional[Document]:
        """Safely extract content from a URL, catching exceptions.

        Args:
            url: URL to extract from

        Returns:
            Optional[Document]: Extracted document or None if extraction fails
        """
        try:
            return self.extract_url(url)
        except Exception as e:
            logger.error(f"Failed to extract {url}: {e}")
            return None

    async def _safe_extract_async(self, url: str) -> Optional[Document]:
        """Asynchronously extract content from a URL, catching exceptions.

        Args:
            url: URL to extract from

        Returns:
            Optional[Document]: Extracted document or None if extraction fails
        """
        try:
            # Run parser in a thread pool since it's a subprocess call
            loop = asyncio.get_event_loop()
            parser_result = await loop.run_in_executor(None, self._run_parser, url)
            
            return self._create_document(parser_result, url)
        except Exception as e:
            logger.error(f"Failed to extract {url} asynchronously: {e}")
            try:
                # Try fallback
                return await self._fallback_extraction_async(url)
            except Exception as fallback_e:
                logger.error(f"Fallback extraction failed for {url}: {fallback_e}")
                return None

    async def _fallback_extraction_async(self, url: str) -> Document:
        """Asynchronous fallback extraction method.

        Args:
            url: URL to extract content from

        Returns:
            Document: Extracted document

        Raises:
            FetchError: If fetching fails
        """
        logger.info(f"Using async fallback extraction for {url}")
        
        try:
            # Fetch the page
            headers = {"User-Agent": self.config.extraction.user_agent}
            if self.config.extraction.custom_headers:
                headers.update(self.config.extraction.custom_headers)
                
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(
                        total=self.config.extraction.timeout_seconds
                    ),
                    allow_redirects=self.config.extraction.follow_redirects,
                ) as response:
                    response.raise_for_status()
                    html = await response.text()
                    
            # Parse with BeautifulSoup
            soup = BeautifulSoup(html, "lxml")
            
            # Extract metadata (simplified for async version)
            metadata = {
                "url": url,
                "domain": url.split("//")[-1].split("/")[0],
                "title": (soup.find("title").text.strip() if soup.find("title") else ""),
            }
            
            # Extract main content
            content_html = self._extract_fallback_content(soup)
            
            return Document(content_html, metadata, url)
        except aiohttp.ClientError as e:
            raise FetchError(f"Failed to fetch {url}: {e}")
        except Exception as e:
            logger.error(f"Async fallback extraction failed: {e}")
            # Create minimal document
            return Document(
                "<p>Content extraction failed</p>",
                {"url": url, "title": "Extraction Failed"},
                url,
            )
