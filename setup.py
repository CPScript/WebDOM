#!/usr/bin/env python3

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="WebDOM",
    version="1.0.0",
    author="CPScript",
    author_email="example@example.com",
    description="web content extraction system",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/CPScript/WebDOM",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Intended Audience :: Information Technology",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Internet :: WWW/HTTP",
        "Topic :: Text Processing :: Markup :: HTML",
        "Topic :: Software Development :: Libraries :: Python Modules",
    ],
    python_requires=">=3.7",
    install_requires=[
        "html2text>=2020.1.16",
        "requests>=2.25.0",
        "aiohttp>=3.7.4",
        "beautifulsoup4>=4.9.3",
        "lxml>=4.6.3",
        "pydantic>=1.8.2",
        "click>=8.0.1",
        "rich>=10.9.0",
        "diskcache>=5.2.1",
        "bleach>=4.1.0",
        "validators>=0.18.2",
    ],
    entry_points={
        "console_scripts": [
            "webdom=webdom_extractor.cli:cli",
        ],
    },
)
