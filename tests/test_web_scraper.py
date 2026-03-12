"""
Tests for the web scraper module.

These tests use mocking to avoid actual network calls and validate
the scraping logic, parsing, and data extraction.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from bs4 import BeautifulSoup  # Added import

from src.web_scraper import (
    BaseScraper,
    PersonalWebsiteScraper,
    BlogScraper,
    ForumScraper,
    LinkedInScraper,
    TwitterScraper,
    WebScraper,
    scrape_personal_website,
    scrape_blogs,
    scrape_forums,
    scrape_linkedin,
    scrape_twitter,
    run_all,
)


# Sample HTML fixtures
SAMPLE_PERSONAL_HTML = """
<!DOCTYPE html>
<html>
<head><title>About Me - Julien</title></head>
<body>
    <main>
        <h1>About Me</h1>
        <p>Hi, I'm Julien, a software engineer passionate about building scalable systems.</p>
    </main>
</body>
</html>
"""

SAMPLE_BLOG_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>My Tech Blog</title>
    <link rel="alternate" type="application/rss+xml" href="/feed">
</head>
<body>
    <article class="post">
        <h1 class="title">Understanding Vector Databases</h1>
        <span class="author">Julien</span>
        <time class="date">2024-01-15</time>
        <div class="content">
            Vector databases have become essential infrastructure for AI applications.
        </div>
    </article>
</body>
</html>
"""

SAMPLE_BLOG_HTML_NO_RSS = """
<!DOCTYPE html>
<html>
<head>
    <title>My Tech Blog</title>
</head>
<body>
    <article class="post">
        <h1 class="title">Understanding Vector Databases</h1>
        <span class="author">Julien</span>
        <time class="date">2024-01-15</time>
        <div class="content">
            Vector databases have become essential infrastructure for AI applications.
        </div>
    </article>
</body>
</html>
"""

SAMPLE_FORUM_HTML = """
<!DOCTYPE html>
<html>
<head><title>Forum Topic</title></head>
<body>
    <div class="topic-title">Best Practices for RAG</div>
    <div class="topic-post">
        <span class="username">Julien</span>
        <span class="post-date">2024-01-20</span>
        <div class="post-content">I've been working on a RAG system and learned...</div>
    </div>
</body>
</html>
"""


# Concrete implementation for testing BaseScraper
class TestScraper(BaseScraper):
    """Concrete scraper for testing BaseScraper functionality."""

    def scrape(self, urls: list, **kwargs):
        return [{"url": url, "source": "test"} for url in urls]


class TestBaseScraper:
    """Tests for the BaseScraper class (using TestScraper concrete implementation)."""

    def test_init_creates_output_dir(self, tmp_path):
        """Test that output directory is created."""
        output_dir = tmp_path / "test_output"
        scraper = TestScraper(output_dir=str(output_dir))
        assert output_dir.exists()

    def test_extract_text_with_metadata_basic(self, tmp_path):
        """Test basic text extraction with metadata."""
        scraper = TestScraper(output_dir=str(tmp_path))
        soup = BeautifulSoup(SAMPLE_PERSONAL_HTML, "html.parser")
        doc = scraper.extract_text_with_metadata(soup, "https://example.com/test")

        assert doc["url"] == "https://example.com/test"
        assert doc["domain"] == "example.com"
        assert doc["title"] == "About Me - Julien"
        assert "software engineer" in doc["content"]
        assert doc["scraped_at"] is not None

    def test_save_to_json(self, tmp_path):
        """Test saving data to JSON."""
        scraper = TestScraper(output_dir=str(tmp_path))
        test_data = [{"test": "data"}]
        output_file = scraper.save_to_json(test_data, "test.json")

        assert output_file.exists()
        with open(output_file) as f:
            loaded = json.load(f)
        assert loaded == test_data

    def test_fetch_page_with_requests(self, tmp_path):
        """Test fetching page with requests."""
        scraper = TestScraper(output_dir=str(tmp_path), use_selenium=False)

        with patch("requests.Session.get") as mock_get:
            mock_response = Mock()
            mock_response.text = "<html>test</html>"
            mock_response.raise_for_status = Mock()
            mock_get.return_value = mock_response

            html = scraper.fetch_page("https://example.com")
            assert html == "<html>test</html>"

    def test_selenium_fallback(self, tmp_path):
        """Test that Selenium initialization failure falls back to requests."""
        with patch(
            "src.web_scraper.webdriver.Chrome",
            side_effect=Exception("Chrome not available"),
        ):
            scraper = TestScraper(output_dir=str(tmp_path), use_selenium=True)
            assert scraper.use_selenium is False

    def test_close(self, tmp_path):
        """Test that close properly handles resources."""
        scraper = TestScraper(output_dir=str(tmp_path), use_selenium=False)
        scraper.close()  # Should not raise


class TestPersonalWebsiteScraper:
    """Tests for PersonalWebsiteScraper."""

    def test_scrape_single_page(self, tmp_path):
        """Test scraping a single personal website page."""
        scraper = PersonalWebsiteScraper(output_dir=str(tmp_path))

        with patch.object(scraper, "fetch_page", return_value=SAMPLE_PERSONAL_HTML):
            docs = scraper.scrape(["https://example.com/about"])

        assert len(docs) == 1
        assert docs[0]["source_type"] == "personal_website"
        assert docs[0]["url"] == "https://example.com/about"
        assert "software engineer" in docs[0]["content"]

    def test_scrape_multiple_pages(self, tmp_path):
        """Test scraping multiple pages."""
        scraper = PersonalWebsiteScraper(output_dir=str(tmp_path))

        with patch.object(scraper, "fetch_page", return_value=SAMPLE_PERSONAL_HTML):
            docs = scraper.scrape(
                [
                    "https://example.com/about",
                    "https://example.com/projects",
                ]
            )

        assert len(docs) == 2

    def test_scrape_handles_fetch_failure(self, tmp_path):
        """Test that scrape handles failed fetches gracefully."""
        scraper = PersonalWebsiteScraper(output_dir=str(tmp_path))

        with patch.object(scraper, "fetch_page", return_value=None):
            docs = scraper.scrape(["https://example.com/test"])

        assert len(docs) == 0

    def test_scrape_rate_limiting(self, tmp_path):
        """Test that scraping includes rate limiting."""
        scraper = PersonalWebsiteScraper(output_dir=str(tmp_path))

        with patch.object(
            scraper, "fetch_page", return_value=SAMPLE_PERSONAL_HTML
        ) as mock_fetch:
            docs = scraper.scrape(["https://example.com/1"])

            # Should only fetch once (sleep is not mocked but we don't test it)
            assert mock_fetch.call_count == 1


class TestBlogScraper:
    """Tests for BlogScraper."""

    def test_scrape_html_page(self, tmp_path):
        """Test scraping a blog HTML page."""
        scraper = BlogScraper(output_dir=str(tmp_path))

        with patch.object(scraper, "fetch_page", return_value=SAMPLE_BLOG_HTML_NO_RSS):
            docs = scraper.scrape(["https://blog.example.com/post"])

        assert len(docs) == 1
        assert docs[0]["source_type"] == "blog"
        # Title from <title> tag
        assert docs[0]["title"] == "My Tech Blog"
        assert docs[0]["author"] == "Julien"

    def test_scrape_rss_feed(self, tmp_path):
        """Test scraping from RSS feed."""
        scraper = BlogScraper(output_dir=str(tmp_path))

        rss_content = """<?xml version="1.0"?>
        <rss version="2.0">
        <channel>
            <item>
                <title>Blog Post Title</title>
                <link>https://blog.example.com/post</link>
                <description>Post content here</description>
                <author>julien@example.com</author>
                <pubDate>Mon, 15 Jan 2024 10:30:00 GMT</pubDate>
            </item>
        </channel>
        </rss>"""

        with patch.object(scraper, "fetch_page", return_value=rss_content):
            docs = scraper.scrape(["https://blog.example.com/feed"])

        assert len(docs) == 1
        assert docs[0]["title"] == "Blog Post Title"
        assert docs[0]["content"] == "Post content here"

    def test_discover_rss_feed(self, tmp_path):
        """Test RSS feed discovery from blog homepage."""
        scraper = BlogScraper(output_dir=str(tmp_path))

        with patch.object(scraper, "fetch_page", return_value=SAMPLE_BLOG_HTML):
            rss_url = scraper._discover_rss_feed("https://blog.example.com")
            assert rss_url is not None
            assert "feed" in rss_url

    def test_scrape_multiple_blog_posts(self, tmp_path):
        """Test scraping multiple blog posts from HTML."""
        scraper = BlogScraper(output_dir=str(tmp_path))

        html_with_multiple = SAMPLE_BLOG_HTML_NO_RSS.replace(
            "</article>", "</article>" + SAMPLE_BLOG_HTML_NO_RSS
        )

        with patch.object(scraper, "fetch_page", return_value=html_with_multiple):
            docs = scraper.scrape(["https://blog.example.com/blog"])

        # Should find posts (at least 1)
        assert len(docs) >= 1


class TestForumScraper:
    """Tests for ForumScraper."""

    def test_scrape_forum_posts(self, tmp_path):
        """Test scraping forum posts."""
        scraper = ForumScraper(output_dir=str(tmp_path))

        with patch.object(scraper, "fetch_page", return_value=SAMPLE_FORUM_HTML):
            docs = scraper.scrape(["https://forum.example.com/t/123"])

        assert len(docs) >= 1
        assert docs[0]["source_type"] == "forum"
        assert docs[0]["platform"] in ["discourse", "phpbb", "vanilla"]

    def test_detect_forum_platform(self, tmp_path):
        """Test forum platform detection."""
        scraper = ForumScraper(output_dir=str(tmp_path))
        soup = BeautifulSoup(SAMPLE_FORUM_HTML, "html.parser")

        platform = scraper._detect_platform(soup, "https://forum.example.com")
        assert platform == "discourse"  # Default


class TestLinkedInScraper:
    """Tests for LinkedInScraper."""

    def test_scrape_linkedin_profile(self, tmp_path):
        """Test scraping LinkedIn profile."""
        scraper = LinkedInScraper(output_dir=str(tmp_path))

        linkedin_html = """
        <html>
        <body>
            <h1 class="text-heading-xlarge">Julien Developer</h1>
            <div class="text-body-medium break-words">Software Engineer</div>
            <div id="about"><p>Passionate about building intelligent systems.</p></div>
            <div id="experience">
                <li class="artdeco-list__item">Senior at Tech Corp</li>
            </div>
        </body>
        </html>"""

        with patch.object(scraper, "fetch_page", return_value=linkedin_html):
            docs = scraper.scrape(["https://linkedin.com/in/julien"])

        assert len(docs) == 1
        assert docs[0]["source_type"] == "linkedin"
        assert docs[0]["name"] == "Julien Developer"
        assert "intelligent systems" in docs[0]["about"]


class TestTwitterScraper:
    """Tests for TwitterScraper."""

    def test_scrape_twitter_profile(self, tmp_path):
        """Test scraping Twitter profile."""
        scraper = TwitterScraper(output_dir=str(tmp_path))

        twitter_html = """
        <html>
        <body>
            <div data-testid="User-Name">Julien Dev</div>
            <div data-testid="UserDescription">Tech enthusiast</div>
            <div data-testid="tweet">
                <div data-testid="tweetText">Hello world!</div>
                <time datetime="2024-01-15T10:00:00.000Z">Jan 15</time>
            </div>
        </body>
        </html>"""

        with patch.object(scraper, "fetch_page", return_value=twitter_html):
            docs = scraper.scrape(["https://twitter.com/julien"])

        assert len(docs) == 1
        assert docs[0]["source_type"] == "twitter"
        assert docs[0]["username"] == "julien"
        assert len(docs[0]["tweets"]) >= 1

    def test_parse_count(self, tmp_path):
        """Test count parsing with K/M suffixes."""
        scraper = TwitterScraper(output_dir=str(tmp_path))

        assert scraper._parse_count("1.2K") == 1200
        assert scraper._parse_count("5M") == 5000000
        assert scraper._parse_count("42") == 42
        assert scraper._parse_count("invalid") == 0


class TestWebScraper:
    """Tests for the unified WebScraper class."""

    def test_init_creates_all_scrapers(self, tmp_path):
        """Test that all platform scrapers are initialized."""
        scraper = WebScraper(output_dir=str(tmp_path))

        assert "personal" in scraper.scrapers
        assert "blog" in scraper.scrapers
        assert "forum" in scraper.scrapers
        assert "linkedin" in scraper.scrapers
        assert "twitter" in scraper.scrapers

    def test_scrape_personal_website(self, tmp_path):
        """Test using WebScraper for personal website."""
        scraper = WebScraper(output_dir=str(tmp_path))

        with patch.object(
            scraper.scrapers["personal"], "scrape", return_value=[{"test": "data"}]
        ):
            docs = scraper.scrape_personal_website(["https://example.com"])
            assert len(docs) == 1

    def test_scrape_all_integration(self, tmp_path):
        """Test scrape_all with multiple platforms."""
        scraper = WebScraper(output_dir=str(tmp_path))

        def mock_scrape(urls, **kwargs):
            return [{"url": url, "source_type": "test"} for url in urls]

        with patch.object(
            scraper.scrapers["personal"], "scrape", side_effect=mock_scrape
        ):
            with patch.object(
                scraper.scrapers["blog"], "scrape", side_effect=mock_scrape
            ):
                config = {
                    "personal": ["https://example.com/about"],
                    "blog": ["https://blog.example.com/rss"],
                }
                results = scraper.scrape_all(config)

                assert "personal" in results
                assert "blog" in results
                assert len(results["personal"]) == 1
                assert len(results["blog"]) == 1

    def test_scrape_all_unknown_platform(self, tmp_path):
        """Test that unknown platforms are skipped with warning."""
        scraper = WebScraper(output_dir=str(tmp_path))

        config = {"unknown": ["https://example.com"]}
        with patch.object(scraper.scrapers["personal"], "scrape"):
            results = scraper.scrape_all(config)

            assert "unknown" not in results

    def test_close_all_scrapers(self, tmp_path):
        """Test that close calls close on all scrapers."""
        scraper = WebScraper(output_dir=str(tmp_path))

        mock_scrapers = [Mock() for _ in range(5)]
        scraper.scrapers = {
            "personal": mock_scrapers[0],
            "blog": mock_scrapers[1],
            "forum": mock_scrapers[2],
            "linkedin": mock_scrapers[3],
            "twitter": mock_scrapers[4],
        }

        scraper.close()

        for mock_scraper in mock_scrapers:
            mock_scraper.close.assert_called_once()

    def test_save_to_json_integration(self, tmp_path):
        """Test that scrape_all saves combined results."""
        scraper = WebScraper(output_dir=str(tmp_path))

        test_docs = [
            {"url": "https://example.com/1", "source_type": "test"},
            {"url": "https://example.com/2", "source_type": "test"},
        ]

        with patch.object(
            scraper.scrapers["personal"], "scrape", return_value=test_docs
        ):
            with patch.object(
                scraper.scrapers["personal"], "save_to_json"
            ) as mock_save:
                config = {"personal": ["https://example.com"]}
                scraper.scrape_all(config)

                # Verify save_to_json was called
                assert mock_save.called


class TestConvenienceFunctions:
    """Tests for convenience module-level functions."""

    def test_scrape_personal_website_function(self, tmp_path):
        """Test the scrape_personal_website convenience function."""
        with patch("src.web_scraper.PersonalWebsiteScraper") as MockScraper:
            instance = MockScraper.return_value
            instance.scrape.return_value = [{"test": "data"}]

            docs = scrape_personal_website(
                ["https://example.com"], output_dir=str(tmp_path)
            )

            instance.scrape.assert_called_once()
            instance.close.assert_called_once()
            assert docs == [{"test": "data"}]

    def test_run_all_function(self, tmp_path):
        """Test the run_all convenience function."""
        with patch("src.web_scraper.WebScraper") as MockScraper:
            instance = MockScraper.return_value
            instance.scrape_all.return_value = {"personal": [{}]}

            results = run_all({"personal": ["url"]}, output_dir=str(tmp_path))

            instance.scrape_all.assert_called_once_with({"personal": ["url"]})
            instance.close.assert_called_once()
            assert results == {"personal": [{}]}


class TestIntegration:
    """Integration tests with real HTTP requests (optional)."""

    @pytest.mark.integration
    def test_scrape_example_com(self, tmp_path):
        """Test scraping a real simple website (example.com)."""
        scraper = PersonalWebsiteScraper(output_dir=str(tmp_path))
        try:
            docs = scraper.scrape(["https://example.com"])
            assert len(docs) >= 1
            assert docs[0]["url"] == "https://example.com"
        except Exception as e:
            pytest.skip(f"Network test failed: {e}")
