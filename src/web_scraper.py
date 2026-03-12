"""
Web content scraper for RAG system.

This module provides modular scrapers for various online platforms:
- Personal websites (static HTML)
- Blogs (RSS/Atom feeds, HTML pages)
- Forum posts (Discourse, phpBB, etc.)
- LinkedIn (public profiles/posts)
- Twitter/X (public tweets)

Uses beautifulsoup4 for static content and selenium for dynamic pages.
"""

import os
import json
import logging
import time
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from pathlib import Path
from urllib.parse import urljoin, urlparse
from abc import ABC, abstractmethod

import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

logger = logging.getLogger(__name__)


class BaseScraper(ABC):
    """Base class for all scrapers with common functionality."""

    def __init__(
        self,
        output_dir: str = "data/raw",
        requests_session: Optional[requests.Session] = None,
        use_selenium: bool = False,
        selenium_options: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the base scraper.

        Args:
            output_dir: Directory to save scraped data
            requests_session: Pre-configured requests session (for headers, auth, etc.)
            use_selenium: Whether to use Selenium for JavaScript rendering
            selenium_options: Options for Selenium driver configuration
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.session = requests_session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

        self.use_selenium = use_selenium
        self.driver = None

        if self.use_selenium:
            self._init_selenium(selenium_options or {})

    def _init_selenium(self, options: Dict[str, Any]):
        """Initialize Selenium WebDriver."""
        try:
            chrome_options = webdriver.ChromeOptions()

            # Headless mode by default
            if options.get("headless", True):
                chrome_options.add_argument("--headless")

            # Additional options
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")

            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("Selenium WebDriver initialized")
        except Exception as e:
            logger.warning(
                f"Failed to initialize Selenium: {e}. Falling back to requests."
            )
            self.use_selenium = False
            self.driver = None

    def close(self):
        """Clean up resources."""
        if self.driver:
            self.driver.quit()
            self.driver = None

    def fetch_page(
        self, url: str, wait_for: Optional[str] = None, timeout: int = 10
    ) -> Union[str, None]:
        """
        Fetch a web page using requests or Selenium.

        Args:
            url: URL to fetch
            wait_for: CSS selector to wait for (Selenium only)
            timeout: Timeout in seconds

        Returns:
            Page HTML content or None if failed
        """
        try:
            if self.use_selenium and self.driver:
                logger.debug(f"Fetching {url} with Selenium")
                self.driver.get(url)
                if wait_for:
                    WebDriverWait(self.driver, timeout).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, wait_for))
                    )
                return self.driver.page_source
            else:
                logger.debug(f"Fetching {url} with requests")
                response = self.session.get(url, timeout=timeout)
                response.raise_for_status()
                return response.text
        except Exception as e:
            logger.error(f"Error fetching {url}: {e}")
            return None

    def parse_html(self, html: str) -> BeautifulSoup:
        """Parse HTML string into BeautifulSoup object."""
        return BeautifulSoup(html, "html.parser")

    @abstractmethod
    def scrape(self, urls: List[str], **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape content from given URLs.

        Args:
            urls: List of URLs to scrape
            **kwargs: Additional scraper-specific arguments

        Returns:
            List of scraped document dictionaries
        """
        pass

    def save_to_json(self, data: List[Dict[str, Any]], filename: str) -> Path:
        """
        Save collected data to JSON file.

        Args:
            data: List of data dictionaries to save
            filename: Output filename (will be placed in output_dir)

        Returns:
            Path to saved file
        """
        output_path = self.output_dir / filename

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(data)} items to {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Error saving data to {output_path}: {e}")
            raise

    def extract_text_with_metadata(
        self,
        soup: BeautifulSoup,
        url: str,
        selectors: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Extract text content and metadata from a BeautifulSoup object.

        Args:
            soup: Parsed HTML document
            url: Source URL
            selectors: Optional dict mapping field names to CSS selectors

        Returns:
            Dictionary with extracted content and metadata
        """
        # Default selectors for common content areas
        default_selectors = {
            "title": "title",
            "content": "main, article, .content, .post, .entry-content, body",
            "author": '[rel="author"], .author, .byline',
            "date": "time, .date, .published, .post-date",
        }

        selectors = selectors or default_selectors

        document = {
            "url": url,
            "domain": urlparse(url).netloc,
            "title": None,
            "content": None,
            "author": None,
            "date": None,
            "scraped_at": datetime.utcnow().isoformat(),
            "raw_length": 0,
        }

        # Extract title
        if "title" in selectors:
            title_elem = soup.select_one(selectors["title"])
            if title_elem:
                document["title"] = title_elem.get_text(strip=True)

        # Extract content (try multiple selectors)
        content_selectors = (
            selectors["content"].split(", ")
            if isinstance(selectors["content"], str)
            else [selectors["content"]]
        )
        content = ""
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                # Remove script and style elements
                for script in content_elem(
                    ["script", "style", "nav", "footer", "header"]
                ):
                    script.decompose()
                content = content_elem.get_text(separator="\n", strip=True)
                break

        if not content:
            # Fallback: get all text from body
            body = soup.find("body")
            if body:
                content = body.get_text(separator="\n", strip=True)

        document["content"] = content[:100000]  # Limit content size
        document["raw_length"] = len(content)

        # Extract author
        if "author" in selectors:
            author_elem = soup.select_one(selectors["author"])
            if author_elem:
                document["author"] = author_elem.get_text(strip=True)

        # Extract date
        if "date" in selectors:
            date_elem = soup.select_one(selectors["date"])
            if date_elem:
                document["date"] = date_elem.get_text(strip=True)
                # Try to parse datetime from meta tags
                if not document["date"]:
                    meta_date = soup.find(
                        "meta", {"property": "article:published_time"}
                    ) or soup.find("meta", {"name": "date"})
                    if meta_date:
                        document["date"] = meta_date.get("content")

        return document


class PersonalWebsiteScraper(BaseScraper):
    """Scraper for personal websites (static HTML)."""

    def __init__(self, output_dir: str = "data/raw", **kwargs):
        super().__init__(output_dir, **kwargs)

    def scrape(self, urls: List[str], **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape personal website pages.

        Args:
            urls: List of page URLs to scrape
            **kwargs: Additional arguments (ignored)

        Returns:
            List of scraped documents
        """
        documents = []

        for url in urls:
            logger.info(f"Scraping personal website: {url}")

            html = self.fetch_page(url)
            if not html:
                logger.warning(f"Failed to fetch {url}")
                continue

            soup = self.parse_html(html)
            doc = self.extract_text_with_metadata(soup, url)

            # Add source type
            doc["source_type"] = "personal_website"
            documents.append(doc)

            # Rate limiting
            time.sleep(1)

        logger.info(f"Scraped {len(documents)} personal website pages")
        return documents


class BlogScraper(BaseScraper):
    """Scraper for blogs (HTML pages and RSS feeds)."""

    def __init__(self, output_dir: str = "data/raw", **kwargs):
        super().__init__(output_dir, **kwargs)

    def scrape(
        self, urls: List[str], max_posts: int = 50, **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Scrape blog posts from given URLs.

        Args:
            urls: List of blog URLs or RSS feed URLs
            max_posts: Maximum number of posts to scrape per blog
            **kwargs: Additional arguments

        Returns:
            List of scraped blog post documents
        """
        documents = []

        for url in urls:
            logger.info(f"Scraping blog: {url}")

            # Check if it's an RSS feed
            if url.endswith((".rss", ".atom", "/feed", "/rss")):
                posts = self._scrape_rss_feed(url, max_posts)
            else:
                # Try to discover RSS feed
                rss_url = self._discover_rss_feed(url)
                if rss_url:
                    posts = self._scrape_rss_feed(rss_url, max_posts)
                else:
                    # Scrape as HTML page
                    posts = self._scrape_blog_page(url)

            documents.extend(posts)
            time.sleep(1)

        logger.info(f"Scraped {len(documents)} blog posts")
        return documents

    def _discover_rss_feed(self, blog_url: str) -> Optional[str]:
        """Try to discover RSS feed link from blog homepage."""
        html = self.fetch_page(blog_url)
        if not html:
            return None

        soup = self.parse_html(html)

        # Check common RSS link patterns
        rss_selectors = [
            'link[type="application/rss+xml"]',
            'link[type="application/atom+xml"]',
            'a[href*="rss"]',
            'a[href*="feed"]',
        ]

        for selector in rss_selectors:
            link = soup.select_one(selector)
            if link:
                href = link.get("href")
                if href:
                    # Ensure href is a single string
                    if isinstance(href, list):
                        href = href[0] if href else None
                    if href:
                        return urljoin(blog_url, str(href))

        return None

    def _scrape_rss_feed(self, feed_url: str, max_posts: int) -> List[Dict[str, Any]]:
        """Scrape posts from an RSS/Atom feed."""
        documents = []

        try:
            content = self.fetch_page(feed_url, timeout=10)
            if not content:
                logger.error(f"Failed to fetch RSS feed: {feed_url}")
                return documents

            # Parse XML
            import xml.etree.ElementTree as ET

            root = ET.fromstring(
                content.encode() if isinstance(content, str) else content
            )

            # Handle both RSS and Atom
            items = root.findall(".//item") or root.findall(
                ".//{http://www.w3.org/2005/Atom}entry"
            )

            for item in items[:max_posts]:
                doc = {
                    "source_type": "blog",
                    "url": None,
                    "title": None,
                    "content": None,
                    "author": None,
                    "date": None,
                    "scraped_at": datetime.utcnow().isoformat(),
                }

                # Extract data (simplified - would need proper namespace handling)
                for elem in item:
                    tag = elem.tag.split("}")[-1]  # Remove namespace
                    if tag == "link":
                        doc["url"] = elem.get("href") or elem.text
                    elif tag == "title":
                        doc["title"] = elem.text
                    elif tag == "description" or tag == "summary":
                        doc["content"] = elem.text
                    elif tag == "author":
                        author_elem = elem.find("name") or elem
                        doc["author"] = (
                            author_elem.text if author_elem is not None else None
                        )
                    elif tag == "pubDate" or tag == "published":
                        doc["date"] = elem.text

                if doc["url"] or doc["content"]:
                    documents.append(doc)

        except Exception as e:
            logger.error(f"Error parsing RSS feed {feed_url}: {e}")

        return documents

    def _scrape_blog_page(self, url: str) -> List[Dict[str, Any]]:
        """Scrape a single blog page."""
        html = self.fetch_page(url)
        if not html:
            return []

        soup = self.parse_html(html)
        doc = self.extract_text_with_metadata(soup, url)
        doc["source_type"] = "blog"

        return [doc]


class ForumScraper(BaseScraper):
    """Scraper for forum posts (Discourse, phpBB, vanilla forums)."""

    # CSS selectors for common forum platforms
    PLATFORM_SELECTORS = {
        "discourse": {
            "posts": ".post-wrapper, .topic-post",
            "content": ".post-content, .cooked",
            "author": ".username, .creator",
            "date": ".post-date, .created-at",
            "title": ".topic-title, .fancy-title",
        },
        "phpbb": {
            "posts": ".post, .postbg",
            "content": ".postbody, .content",
            "author": ".postauthor, .username",
            "date": ".postdate",
            "title": ".topictitle",
        },
        "vanilla": {
            "posts": ".Message",
            "content": ".Message-content",
            "author": ".Username",
            "date": ".DateCreated",
            "title": ".Title",
        },
    }

    def __init__(self, output_dir: str = "data/raw", **kwargs):
        super().__init__(output_dir, **kwargs)

    def scrape(
        self, urls: List[str], max_posts_per_topic: int = 100, **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Scrape forum posts from topic URLs.

        Args:
            urls: List of forum topic URLs
            max_posts_per_topic: Maximum posts to scrape per topic
            **kwargs: Additional arguments

        Returns:
            List of scraped forum post documents
        """
        documents = []

        for url in urls:
            logger.info(f"Scraping forum topic: {url}")

            html = self.fetch_page(url)
            if not html:
                logger.warning(f"Failed to fetch {url}")
                continue

            soup = self.parse_html(html)

            # Detect forum platform
            platform = self._detect_platform(soup, url)
            selectors = self.PLATFORM_SELECTORS.get(
                platform, self.PLATFORM_SELECTORS["discourse"]
            )

            # Extract posts
            posts = soup.select(selectors["posts"])[:max_posts_per_topic]

            for post in posts:
                doc = {
                    "source_type": "forum",
                    "platform": platform,
                    "url": url,
                    "title": None,
                    "content": None,
                    "author": None,
                    "date": None,
                    "scraped_at": datetime.utcnow().isoformat(),
                }

                # Extract title from page
                title_elem = soup.select_one(selectors["title"])
                if title_elem:
                    doc["title"] = title_elem.get_text(strip=True)

                # Extract post-specific content
                content_elem = post.select_one(selectors["content"])
                if content_elem:
                    doc["content"] = content_elem.get_text(separator="\n", strip=True)

                # Extract author
                author_elem = post.select_one(selectors["author"])
                if author_elem:
                    doc["author"] = author_elem.get_text(strip=True)

                # Extract date
                date_elem = post.select_one(selectors["date"])
                if date_elem:
                    doc["date"] = date_elem.get_text(strip=True)

                if doc["content"]:
                    documents.append(doc)

            time.sleep(1)

        logger.info(f"Scraped {len(documents)} forum posts")
        return documents

    def _detect_platform(self, soup: BeautifulSoup, url: str) -> str:
        """Detect forum platform from page structure."""
        html_str = str(soup)

        if "discourse" in html_str.lower() or "discourse" in url:
            return "discourse"
        elif "phpbb" in html_str.lower() or "phpbb" in url:
            return "phpbb"
        elif "vanilla" in html_str.lower():
            return "vanilla"

        # Default to discourse
        return "discourse"


class LinkedInScraper(BaseScraper):
    """Scraper for LinkedIn public profiles and posts."""

    def __init__(self, output_dir: str = "data/raw", **kwargs):
        super().__init__(output_dir, use_selenium=True, **kwargs)

    def scrape(self, urls: List[str], **kwargs) -> List[Dict[str, Any]]:
        """
        Scrape LinkedIn public profiles.

        Args:
            urls: List of LinkedIn profile URLs (must be public)
            **kwargs: Additional arguments

        Returns:
            List of scraped LinkedIn profile documents
        """
        documents = []

        for url in urls:
            logger.info(f"Scraping LinkedIn profile: {url}")

            # LinkedIn requires JavaScript, use Selenium
            html = self.fetch_page(url, wait_for=".profile")
            if not html:
                logger.warning(f"Failed to fetch {url}")
                continue

            soup = self.parse_html(html)

            doc = {
                "source_type": "linkedin",
                "url": url,
                "name": None,
                "headline": None,
                "about": None,
                "experience": [],
                "education": [],
                "skills": [],
                "scraped_at": datetime.utcnow().isoformat(),
            }

            # Extract name
            name_elem = soup.select_one("h1.text-heading-xlarge, .pv-top-card--list li")
            if name_elem:
                doc["name"] = name_elem.get_text(strip=True)

            # Extract headline
            headline_elem = soup.select_one(
                ".text-body-medium.break-words, .pv-top-card--headline"
            )
            if headline_elem:
                doc["headline"] = headline_elem.get_text(strip=True)

            # Extract about section
            about_elem = soup.select_one("#about, .pv-about-section")
            if about_elem:
                doc["about"] = about_elem.get_text(separator="\n", strip=True)

            # Extract experience
            exp_section = soup.select_one("#experience, .pv-experience-section")
            if exp_section:
                exp_items = exp_section.select("li.artdeco-list__item")
                for item in exp_items:
                    exp_text = item.get_text(separator="\n", strip=True)
                    if exp_text:
                        doc["experience"].append(exp_text)

            documents.append(doc)
            time.sleep(3)  # Be extra careful with rate limiting

        logger.info(f"Scraped {len(documents)} LinkedIn profiles")
        return documents


class TwitterScraper(BaseScraper):
    """Scraper for public Twitter/X profiles and tweets."""

    def __init__(self, output_dir: str = "data/raw", **kwargs):
        super().__init__(output_dir, use_selenium=True, **kwargs)

    def scrape(
        self, urls: List[str], max_tweets: int = 50, **kwargs
    ) -> List[Dict[str, Any]]:
        """
        Scrape public Twitter/X profiles.

        Args:
            urls: List of Twitter/X profile URLs (must be public)
            max_tweets: Maximum number of tweets to scrape per profile
            **kwargs: Additional arguments

        Returns:
            List of scraped tweet documents
        """
        documents = []

        for url in urls:
            logger.info(f"Scraping Twitter/X profile: {url}")

            html = self.fetch_page(url, wait_for='[data-testid="tweet"]')
            if not html:
                logger.warning(f"Failed to fetch {url}")
                continue

            soup = self.parse_html(html)

            # Extract profile info
            profile = {
                "source_type": "twitter",
                "url": url,
                "username": urlparse(url).path.strip("/"),
                "display_name": None,
                "bio": None,
                "tweets": [],
                "scraped_at": datetime.utcnow().isoformat(),
            }

            # Extract display name
            name_elem = soup.select_one('[data-testid="User-Name"]')
            if name_elem:
                profile["display_name"] = name_elem.get_text(strip=True)

            # Extract bio
            bio_elem = soup.select_one('[data-testid="UserDescription"]')
            if bio_elem:
                profile["bio"] = bio_elem.get_text(strip=True)

            # Extract tweets
            tweet_elements = soup.select('[data-testid="tweet"]')[:max_tweets]
            for tweet_elem in tweet_elements:
                tweet = {
                    "text": None,
                    "date": None,
                    "replies": 0,
                    "retweets": 0,
                    "likes": 0,
                }

                # Extract tweet text
                text_elem = tweet_elem.select_one('[data-testid="tweetText"]')
                if text_elem:
                    tweet["text"] = text_elem.get_text(strip=True)

                # Extract timestamp
                time_elem = tweet_elem.select_one("time")
                if time_elem:
                    tweet["date"] = time_elem.get("datetime")

                # Extract engagement metrics
                for metric_type, selector in [
                    ("replies", '[data-testid="reply"]'),
                    ("retweets", '[data-testid="retweet"]'),
                    ("likes", '[data-testid="like"]'),
                ]:
                    metric_elem = tweet_elem.select_one(selector)
                    if metric_elem:
                        metric_text = metric_elem.get_text(strip=True)
                        # Convert to int (handle K, M suffixes)
                        tweet[metric_type] = self._parse_count(metric_text)

                if tweet["text"]:
                    profile["tweets"].append(tweet)

            documents.append(profile)
            time.sleep(3)

        logger.info(f"Scraped {len(documents)} Twitter/X profiles")
        return documents

    def _parse_count(self, text: str) -> int:
        """Parse count strings like '1.2K', '5M'."""
        try:
            text = text.replace(",", "").lower().strip()
            if "k" in text:
                return int(float(text.replace("k", "")) * 1000)
            elif "m" in text:
                return int(float(text.replace("m", "")) * 1000000)
            return int(text)
        except:
            return 0


class WebScraper:
    """
    Unified web scraper that manages multiple platform-specific scrapers.

    Example:
        scraper = WebScraper(output_dir="data/raw")

        # Scrape personal website
        docs = scraper.scrape_personal_website(["https://example.com/about"])

        # Scrape blogs
        docs = scraper.scrape_blogs(["https://blog.example.com/rss"])

        # Scrape forums
        docs = scraper.scrape_forums(["https://forum.example.com/topic/123"])

        # Scrape LinkedIn (requires Selenium)
        docs = scraper.scrape_linkedin(["https://linkedin.com/in/username"])

        # Scrape Twitter (requires Selenium)
        docs = scraper.scrape_twitter(["https://twitter.com/username"])
    """

    def __init__(
        self,
        output_dir: str = "data/raw",
        requests_session: Optional[requests.Session] = None,
        use_selenium: bool = False,
        selenium_options: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the unified web scraper.

        Args:
            output_dir: Directory to save scraped data
            requests_session: Pre-configured requests session
            use_selenium: Enable Selenium for JavaScript rendering
            selenium_options: Selenium driver configuration
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize platform-specific scrapers
        session = requests_session or requests.Session()
        session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

        self.scrapers = {
            "personal": PersonalWebsiteScraper(
                output_dir=output_dir,
                requests_session=session,
                use_selenium=use_selenium,
                selenium_options=selenium_options,
            ),
            "blog": BlogScraper(
                output_dir=output_dir,
                requests_session=session,
                use_selenium=use_selenium,
                selenium_options=selenium_options,
            ),
            "forum": ForumScraper(
                output_dir=output_dir,
                requests_session=session,
                use_selenium=use_selenium,
                selenium_options=selenium_options,
            ),
            "linkedin": LinkedInScraper(
                output_dir=output_dir,
                requests_session=session,
                selenium_options=selenium_options,
            ),
            "twitter": TwitterScraper(
                output_dir=output_dir,
                requests_session=session,
                selenium_options=selenium_options,
            ),
        }

    def scrape_personal_website(
        self, urls: List[str], **kwargs
    ) -> List[Dict[str, Any]]:
        """Scrape personal website pages."""
        return self.scrapers["personal"].scrape(urls, **kwargs)

    def scrape_blogs(self, urls: List[str], **kwargs) -> List[Dict[str, Any]]:
        """Scrape blog posts."""
        return self.scrapers["blog"].scrape(urls, **kwargs)

    def scrape_forums(self, urls: List[str], **kwargs) -> List[Dict[str, Any]]:
        """Scrape forum posts."""
        return self.scrapers["forum"].scrape(urls, **kwargs)

    def scrape_linkedin(self, urls: List[str], **kwargs) -> List[Dict[str, Any]]:
        """Scrape LinkedIn profiles."""
        return self.scrapers["linkedin"].scrape(urls, **kwargs)

    def scrape_twitter(self, urls: List[str], **kwargs) -> List[Dict[str, Any]]:
        """Scrape Twitter/X profiles."""
        return self.scrapers["twitter"].scrape(urls, **kwargs)

    def scrape_all(
        self,
        config: Dict[str, List[str]],
        **kwargs,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Scrape multiple platforms based on configuration.

        Args:
            config: Dict mapping platform names to URL lists
                Example: {
                    'personal': ['https://example.com/about'],
                    'blog': ['https://blog.example.com/rss'],
                }
            **kwargs: Additional arguments passed to scrapers

        Returns:
            Dict mapping platform names to lists of scraped documents
        """
        results = {}

        for platform, urls in config.items():
            if platform not in self.scrapers:
                logger.warning(f"Unknown platform: {platform}. Skipping.")
                continue

            if not urls:
                logger.info(f"No URLs provided for {platform}. Skipping.")
                continue

            logger.info(f"Scraping {platform} with {len(urls)} URLs...")

            try:
                docs = self.scrapers[platform].scrape(urls, **kwargs)
                results[platform] = docs
            except Exception as e:
                logger.error(f"Error scraping {platform}: {e}")
                results[platform] = []

        # Save all results
        all_docs = []
        for platform_docs in results.values():
            all_docs.extend(platform_docs)

        if all_docs:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"web_scraped_{timestamp}.json"
            self.scrapers["personal"].save_to_json(all_docs, filename)

        logger.info(f"Scraping complete: {len(all_docs)} total documents")
        return results

    def close(self):
        """Close all scrapers and their resources."""
        for scraper in self.scrapers.values():
            scraper.close()


# Convenience functions
def scrape_personal_website(
    urls: List[str], output_dir: str = "data/raw", **kwargs
) -> List[Dict[str, Any]]:
    """Convenience function to scrape personal website pages."""
    scraper = PersonalWebsiteScraper(output_dir=output_dir, **kwargs)
    try:
        return scraper.scrape(urls, **kwargs)
    finally:
        scraper.close()


def scrape_blogs(
    urls: List[str], output_dir: str = "data/raw", **kwargs
) -> List[Dict[str, Any]]:
    """Convenience function to scrape blogs."""
    scraper = BlogScraper(output_dir=output_dir, **kwargs)
    try:
        return scraper.scrape(urls, **kwargs)
    finally:
        scraper.close()


def scrape_forums(
    urls: List[str], output_dir: str = "data/raw", **kwargs
) -> List[Dict[str, Any]]:
    """Convenience function to scrape forum posts."""
    scraper = ForumScraper(output_dir=output_dir, **kwargs)
    try:
        return scraper.scrape(urls, **kwargs)
    finally:
        scraper.close()


def scrape_linkedin(
    urls: List[str], output_dir: str = "data/raw", **kwargs
) -> List[Dict[str, Any]]:
    """Convenience function to scrape LinkedIn profiles."""
    scraper = LinkedInScraper(output_dir=output_dir, **kwargs)
    try:
        return scraper.scrape(urls, **kwargs)
    finally:
        scraper.close()


def scrape_twitter(
    urls: List[str], output_dir: str = "data/raw", **kwargs
) -> List[Dict[str, Any]]:
    """Convenience function to scrape Twitter/X profiles."""
    scraper = TwitterScraper(output_dir=output_dir, **kwargs)
    try:
        return scraper.scrape(urls, **kwargs)
    finally:
        scraper.close()


def run_all(
    config: Dict[str, List[str]],
    output_dir: str = "data/raw",
    **kwargs,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Convenience function to run all configured scrapers.

    Args:
        config: Dict mapping platform names to URL lists
        output_dir: Directory to save output
        **kwargs: Additional arguments passed to scrapers

    Returns:
        Dict mapping platform names to scraped documents
    """
    scraper = WebScraper(output_dir=output_dir, **kwargs)
    try:
        return scraper.scrape_all(config, **kwargs)
    finally:
        scraper.close()
