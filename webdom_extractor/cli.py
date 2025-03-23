#!/usr/bin/env python3

"""Command-line interface for WebDOM Extractor.

This module provides a command-line interface to the WebDOM Extractor library
for extracting clean, readable content from web pages.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO, Tuple

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

from webdom_extractor import Extractor, Document
from webdom_extractor.config import Config
from webdom_extractor.formatters import OutputFormat

# Initialize rich console for prettier output
console = Console()


def setup_logging(verbose: bool = False) -> None:
    """Set up logging with rich formatter.

    Args:
        verbose: Whether to enable verbose logging
    """
    log_level = logging.DEBUG if verbose else logging.INFO
    
    # Configure root logger with rich handler
    logging.basicConfig(
        level=log_level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True)]
    )
    
    # Set level for webdom_extractor logger
    logging.getLogger("webdom_extractor").setLevel(log_level)
    
    # Reduce verbosity of other loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def load_config(config_path: Optional[str]) -> Dict[str, Any]:
    """Load configuration from file.

    Args:
        config_path: Path to configuration file

    Returns:
        Dict: Configuration dictionary
    """
    if not config_path:
        return {}
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        console.print(f"[bold red]Error loading configuration:[/] {e}")
        sys.exit(1)


@click.group()
@click.version_option()
@click.option(
    "-v", "--verbose",
    is_flag=True,
    help="Enable verbose output"
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """WebDOM Extractor - Extract clean, readable content from web pages.

    This tool extracts main content from web pages, removing navigation,
    advertisements, and other non-content elements.
    """
    # Set up logging
    setup_logging(verbose)
    
    # Initialize context
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@cli.command()
@click.argument("url")
@click.option(
    "-f", "--format",
    type=click.Choice(["json", "markdown", "text", "html"]),
    default="markdown",
    help="Output format"
)
@click.option(
    "-o", "--output",
    type=click.Path(),
    help="Output file path (default: stdout)"
)
@click.option(
    "-c", "--config",
    type=click.Path(exists=True),
    help="Path to configuration file"
)
@click.option(
    "-p", "--parser-path",
    help="Path to Postlight Parser executable"
)
@click.option(
    "-w", "--width",
    type=int,
    default=80,
    help="Line width for text wrapping"
)
@click.pass_context
def extract(
    ctx: click.Context,
    url: str,
    format: str,
    output: Optional[str],
    config: Optional[str],
    parser_path: Optional[str],
    width: int,
) -> None:
    """Extract content from a URL.

    Extract the main content from the specified URL and output it in the
    selected format.

    Examples:
        webdom extract https://example.com/article
        webdom extract https://example.com/article --format json --output article.json
    """
    config_dict = load_config(config)
    
    # Merge width into config
    if "formatting" not in config_dict:
        config_dict["formatting"] = {}
    config_dict["formatting"]["line_width"] = width
    
    with console.status("[bold green]Extracting content...", spinner="dots"):
        try:
            extractor = Extractor(config=config_dict, parser_path=parser_path)
            document = extractor.extract_url(url)
        except Exception as e:
            console.print(f"[bold red]Error extracting content:[/] {e}")
            sys.exit(1)
    
    # Get content in requested format
    try:
        if format == "json":
            content = document.to_json(pretty=True)
        elif format == "markdown":
            content = document.to_markdown()
        elif format == "text":
            content = document.to_text()
        elif format == "html":
            content = document.content.html
        else:
            content = document.to_markdown()
    except Exception as e:
        console.print(f"[bold red]Error formatting output:[/] {e}")
        sys.exit(1)
    
    # Write to output
    if output:
        try:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            console.print(f"[bold green]Content saved to {output}")
        except Exception as e:
            console.print(f"[bold red]Error writing to file:[/] {e}")
            sys.exit(1)
    else:
        # Print to console
        if format == "json":
            console.print_json(json.loads(content))
        else:
            print(content)


@cli.command()
@click.argument(
    "input_file",
    type=click.Path(exists=True)
)
@click.option(
    "-o", "--output-dir",
    type=click.Path(),
    required=True,
    help="Output directory for extracted content"
)
@click.option(
    "-f", "--format",
    type=click.Choice(["json", "markdown", "text", "html"]),
    default="markdown",
    help="Output format"
)
@click.option(
    "-c", "--config",
    type=click.Path(exists=True),
    help="Path to configuration file"
)
@click.option(
    "-p", "--parser-path",
    help="Path to Postlight Parser executable"
)
@click.option(
    "-w", "--workers",
    type=int,
    default=5,
    help="Number of parallel workers"
)
@click.option(
    "--async",
    "use_async",
    is_flag=True,
    help="Use asynchronous extraction"
)
@click.pass_context
def batch(
    ctx: click.Context,
    input_file: str,
    output_dir: str,
    format: str,
    config: Optional[str],
    parser_path: Optional[str],
    workers: int,
    use_async: bool,
) -> None:
    """Extract content from multiple URLs listed in a file.

    The input file should contain one URL per line. Each URL will be
    processed and saved to the output directory.

    Examples:
        webdom batch urls.txt --output-dir ./extracted
        webdom batch urls.txt --output-dir ./extracted --format json --workers 10
    """
    config_dict = load_config(config)
    
    # Read URLs from file
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            urls = [line.strip() for line in f if line.strip()]
    except Exception as e:
        console.print(f"[bold red]Error reading input file:[/] {e}")
        sys.exit(1)
        
    if not urls:
        console.print("[bold yellow]No URLs found in input file")
        sys.exit(0)
        
    console.print(f"[bold]Found {len(urls)} URLs to process")
    
    # Create output directory
    output_path = Path(output_dir)
    try:
        output_path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        console.print(f"[bold red]Error creating output directory:[/] {e}")
        sys.exit(1)
    
    # Initialize extractor
    try:
        extractor = Extractor(config=config_dict, parser_path=parser_path)
    except Exception as e:
        console.print(f"[bold red]Error initializing extractor:[/] {e}")
        sys.exit(1)
        
    # Process URLs
    if use_async:
        results = asyncio.run(
            _process_urls_async(extractor, urls, workers, format, output_path)
        )
    else:
        results = _process_urls(extractor, urls, workers, format, output_path)
        
    # Report results
    success = sum(1 for _, doc in results if doc is not None)
    console.print(f"[bold green]Processed {success}/{len(urls)} URLs successfully")
    
    # List failed URLs
    failed = [(url, i) for i, (url, doc) in enumerate(results) if doc is None]
    if failed:
        console.print("[bold red]Failed URLs:")
        for url, idx in failed:
            console.print(f"  {idx+1}. {url}")


def _process_urls(
    extractor: Extractor,
    urls: List[str],
    workers: int,
    format: str,
    output_path: Path,
) -> List[Tuple[str, Optional[Document]]]:
    """Process URLs in parallel.

    Args:
        extractor: Extractor instance
        urls: List of URLs to process
        workers: Number of parallel workers
        format: Output format
        output_path: Output directory path

    Returns:
        List[Tuple[str, Optional[Document]]]: List of (url, document) pairs
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        TextColumn("[bold yellow]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[bold green]Extracting content...", total=len(urls))
        
        results = []
        for url, document in extractor.extract_batch(urls, max_workers=workers):
            if document:
                _save_document(document, url, format, output_path)
                
            results.append((url, document))
            progress.update(task, advance=1)
            
    return results


async def _process_urls_async(
    extractor: Extractor,
    urls: List[str],
    workers: int,
    format: str,
    output_path: Path,
) -> List[Tuple[str, Optional[Document]]]:
    """Process URLs asynchronously.

    Args:
        extractor: Extractor instance
        urls: List of URLs to process
        workers: Number of parallel workers
        format: Output format
        output_path: Output directory path

    Returns:
        List[Tuple[str, Optional[Document]]]: List of (url, document) pairs
    """
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        TextColumn("[bold yellow]{task.completed}/{task.total}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[bold green]Extracting content...", total=len(urls))
        
        results = await extractor.extract_batch_async(urls, max_workers=workers)
        
        for url, document in results:
            if document:
                _save_document(document, url, format, output_path)
                
            progress.update(task, advance=1)
            
    return results


def _save_document(
    document: Document, url: str, format: str, output_path: Path
) -> None:
    """Save document to file.

    Args:
        document: Document to save
        url: Source URL
        format: Output format
        output_path: Output directory path
    """
    # Generate safe filename from URL
    import re
    from urllib.parse import urlparse
    
    parsed = urlparse(url)
    domain = parsed.netloc
    
    # Create a path with domain as subdirectory
    domain_path = output_path / domain
    domain_path.mkdir(exist_ok=True)
    
    # Create filename from path
    path = parsed.path
    if not path or path == "/":
        filename = "index"
    else:
        # Remove extension and convert to filename
        path = path.rstrip("/")
        basename = os.path.basename(path)
        filename = re.sub(r"\.[^.]+$", "", basename)
        
        # Remove special characters
        filename = re.sub(r"[^\w\-]", "_", filename)
        
    # Add extension based on format
    ext = {
        "json": ".json",
        "markdown": ".md",
        "text": ".txt",
        "html": ".html",
    }.get(format, ".md")
    
    # Create full path
    file_path = domain_path / f"{filename}{ext}"
    
    # If file exists, add numeric suffix
    counter = 1
    original_path = file_path
    while file_path.exists():
        file_path = original_path.with_name(f"{filename}_{counter}{ext}")
        counter += 1
        
    # Save document
    document.save(file_path, format=format)


@cli.command()
@click.argument(
    "html_file",
    type=click.Path(exists=True)
)
@click.option(
    "-u", "--url",
    help="Source URL for the HTML file"
)
@click.option(
    "-f", "--format",
    type=click.Choice(["json", "markdown", "text", "html"]),
    default="markdown",
    help="Output format"
)
@click.option(
    "-o", "--output",
    type=click.Path(),
    help="Output file path (default: stdout)"
)
@click.option(
    "-c", "--config",
    type=click.Path(exists=True),
    help="Path to configuration file"
)
@click.option(
    "-w", "--width",
    type=int,
    default=80,
    help="Line width for text wrapping"
)
@click.pass_context
def process_html(
    ctx: click.Context,
    html_file: str,
    url: Optional[str],
    format: str,
    output: Optional[str],
    config: Optional[str],
    width: int,
) -> None:
    """Process HTML from a file.

    Extract the main content from the specified HTML file and output it in the
    selected format.

    Examples:
        webdom process-html page.html
        webdom process-html page.html --url https://example.com/article --format json
    """
    config_dict = load_config(config)
    
    # Merge width into config
    if "formatting" not in config_dict:
        config_dict["formatting"] = {}
    config_dict["formatting"]["line_width"] = width
    
    # Read HTML file
    try:
        with open(html_file, "r", encoding="utf-8") as f:
            html = f.read()
    except Exception as e:
        console.print(f"[bold red]Error reading HTML file:[/] {e}")
        sys.exit(1)
    
    with console.status("[bold green]Extracting content...", spinner="dots"):
        try:
            extractor = Extractor(config=config_dict)
            document = extractor.extract_html(html, url=url)
        except Exception as e:
            console.print(f"[bold red]Error extracting content:[/] {e}")
            sys.exit(1)
    
    # Get content in requested format
    try:
        if format == "json":
            content = document.to_json(pretty=True)
        elif format == "markdown":
            content = document.to_markdown()
        elif format == "text":
            content = document.to_text()
        elif format == "html":
            content = document.content.html
        else:
            content = document.to_markdown()
    except Exception as e:
        console.print(f"[bold red]Error formatting output:[/] {e}")
        sys.exit(1)
    
    # Write to output
    if output:
        try:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            console.print(f"[bold green]Content saved to {output}")
        except Exception as e:
            console.print(f"[bold red]Error writing to file:[/] {e}")
            sys.exit(1)
    else:
        # Print to console
        if format == "json":
            console.print_json(json.loads(content))
        else:
            print(content)


@cli.command()
@click.option(
    "-p", "--parser-path",
    help="Path to Postlight Parser executable"
)
@click.pass_context
def check(ctx: click.Context, parser_path: Optional[str]) -> None:
    """Check if the environment is properly configured."""
    # Check if Postlight Parser is installed
    try:
        extractor = Extractor(parser_path=parser_path)
        parser_path = extractor.parser_path
        console.print(f"[bold green]✓[/] Postlight Parser found at: {parser_path}")
    except Exception as e:
        console.print(f"[bold red]✗[/] Postlight Parser not found: {e}")
        console.print(
            "[yellow]To install the Postlight Parser:[/]\n"
            "  npm install -g @postlight/parser\n"
            "  # or\n"
            "  yarn global add @postlight/parser"
        )
        sys.exit(1)
        
    # Check Python dependencies
    dependencies = [
        "html2text",
        "requests",
        "aiohttp", 
        "beautifulsoup4",
        "lxml",
        "pydantic",
        "click",
        "rich",
        "diskcache",
    ]
    
    for dep in dependencies:
        try:
            __import__(dep)
            console.print(f"[bold green]✓[/] {dep} installed")
        except ImportError:
            console.print(f"[bold red]✗[/] {dep} not installed")
            
    console.print("[bold green]Environment check completed")


if __name__ == "__main__":
    cli()
