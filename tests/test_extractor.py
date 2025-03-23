"""Tests for the Extractor class."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import pytest

from webdom_extractor.extractor import Extractor, ExtractionError, FetchError
from webdom_extractor.document import Document


class TestExtractor:
    """Test suite for the Extractor class."""

    def test_initialization(self):
        """Test that the extractor initializes correctly."""
        # Mock parser path finding
        with patch("webdom_extractor.extractor.Extractor._find_parser_path") as mock_find:
            mock_find.return_value = "/path/to/parser"
            with patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True
                
                extractor = Extractor()
                assert extractor.parser_path == "/path/to/parser"
                assert extractor.config is not None

    def test_initialization_with_invalid_parser_path(self):
        """Test that the extractor raises an error with invalid parser path."""
        with patch("os.path.exists") as mock_exists:
            mock_exists.return_value = False
            
            with pytest.raises(ValueError):
                Extractor(parser_path="/nonexistent/path")

    def test_find_parser_path(self):
        """Test finding the parser path."""
        # Mock subprocess.run
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "/path/to/parser\n"
            mock_run.return_value = mock_result
            
            with patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True
                
                extractor = Extractor(parser_path="/path/to/parser")
                assert extractor.parser_path == "/path/to/parser"

    def test_extract_url_with_invalid_url(self):
        """Test extracting content from an invalid URL."""
        with patch("webdom_extractor.extractor.Extractor._find_parser_path") as mock_find:
            mock_find.return_value = "/path/to/parser"
            with patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True
                
                extractor = Extractor()
                
                with pytest.raises(ValueError):
                    extractor.extract_url("not-a-url")

    def test_run_parser(self):
        """Test running the parser."""
        with patch("webdom_extractor.extractor.Extractor._find_parser_path") as mock_find:
            mock_find.return_value = "/path/to/parser"
            with patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True
                
                extractor = Extractor()
                
                # Mock subprocess.run
                with patch("subprocess.run") as mock_run:
                    mock_result = MagicMock()
                    mock_result.stdout = '{"title":"Test","content":"<p>Test</p>"}'
                    mock_run.return_value = mock_result
                    
                    result = extractor._run_parser("https://example.com")
                    assert result["title"] == "Test"
                    assert result["content"] == "<p>Test</p>"

    def test_extract_html(self):
        """Test extracting content from HTML."""
        with patch("webdom_extractor.extractor.Extractor._find_parser_path") as mock_find:
            mock_find.return_value = "/path/to/parser"
            with patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True
                
                extractor = Extractor()
                
                # Mock _run_parser
                with patch("webdom_extractor.extractor.Extractor._run_parser") as mock_run_parser:
                    mock_run_parser.return_value = {
                        "title": "Test",
                        "content": "<p>Test</p>",
                        "url": "https://example.com",
                    }
                    
                    document = extractor.extract_html("<html><body><p>Test</p></body></html>")
                    assert isinstance(document, Document)
                    assert document.content.html == "<p>Test</p>"
                    assert document.metadata.title == "Test"

    def test_extract_batch(self):
        """Test batch extraction."""
        with patch("webdom_extractor.extractor.Extractor._find_parser_path") as mock_find:
            mock_find.return_value = "/path/to/parser"
            with patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True
                
                extractor = Extractor()
                
                # Mock _safe_extract
                with patch("webdom_extractor.extractor.Extractor._safe_extract") as mock_extract:
                    document = Document("<p>Test</p>", {"title": "Test"})
                    mock_extract.return_value = document
                    
                    urls = ["https://example.com", "https://example.org"]
                    results = extractor.extract_batch(urls)
                    
                    assert len(results) == 2
                    assert results[0][0] == "https://example.com"
                    assert results[0][1] == document
                    assert results[1][0] == "https://example.org"
                    assert results[1][1] == document

    def test_fallback_extraction(self):
        """Test fallback extraction."""
        with patch("webdom_extractor.extractor.Extractor._find_parser_path") as mock_find:
            mock_find.return_value = "/path/to/parser"
            with patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True
                
                extractor = Extractor()
                
                # Mock requests.get
                with patch("requests.get") as mock_get:
                    mock_response = MagicMock()
                    mock_response.text = "<html><body><p>Test</p></body></html>"
                    mock_get.return_value = mock_response
                    
                    # Mock BeautifulSoup
                    with patch("webdom_extractor.extractor.BeautifulSoup") as mock_soup:
                        soup = MagicMock()
                        soup.find.return_value = MagicMock()
                        soup.find.return_value.text = "Test"
                        mock_soup.return_value = soup
                        
                        document = extractor._fallback_extraction("https://example.com")
                        assert isinstance(document, Document)

    def test_cache(self):
        """Test content caching."""
        with patch("webdom_extractor.extractor.Extractor._find_parser_path") as mock_find:
            mock_find.return_value = "/path/to/parser"
            with patch("os.path.exists") as mock_exists:
                mock_exists.return_value = True
                
                # Create temp directory for cache
                with tempfile.TemporaryDirectory() as temp_dir:
                    config = {
                        "cache": {
                            "enabled": True,
                            "cache_dir": temp_dir,
                        }
                    }
                    
                    extractor = Extractor(config=config)
                    
                    # Mock _run_parser
                    with patch("webdom_extractor.extractor.Extractor._run_parser") as mock_run_parser:
                        mock_run_parser.return_value = {
                            "title": "Test",
                            "content": "<p>Test</p>",
                            "url": "https://example.com",
                        }
                        
                        # First call should run parser
                        with patch("validators.url") as mock_validator:
                            mock_validator.return_value = True
                            
                            document1 = extractor.extract_url("https://example.com")
                            assert document1.metadata.title == "Test"
                            
                            # Second call should use cache
                            document2 = extractor.extract_url("https://example.com")
                            assert document2.metadata.title == "Test"
                            
                            # Parser should be called only once
                            assert mock_run_parser.call_count == 1
