"""
Tests for GitHub collector module.
"""

import os
import sys
import pytest
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from github_collector import (
    GitHubCollector,
    collect_repos,
    collect_commits,
    collect_issues,
    collect_gists,
    collect_starred,
    run_all,
)


class TestGitHubCollectorImports:
    """Test that all functions can be imported correctly."""

    def test_import_github_collector(self):
        """Test that the module imports without errors."""
        assert GitHubCollector is not None

    def test_import_convenience_functions(self):
        """Test that all convenience functions exist."""
        assert callable(collect_repos)
        assert callable(collect_commits)
        assert callable(collect_issues)
        assert callable(collect_gists)
        assert callable(collect_starred)
        assert callable(run_all)


class TestGitHubCollectorInit:
    """Test GitHubCollector initialization."""

    def test_init_without_token(self, monkeypatch):
        """Test that initialization fails without token."""
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(ValueError, match="GitHub token is required"):
            GitHubCollector()

    def test_init_with_token(self, monkeypatch):
        """Test initialization with token."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        collector = GitHubCollector()
        assert collector.token == "test_token"
        assert collector.output_dir == Path("data/raw")

    def test_init_custom_output_dir(self, monkeypatch):
        """Test initialization with custom output directory."""
        monkeypatch.setenv("GITHUB_TOKEN", "test_token")
        custom_dir = Path("test_output")
        collector = GitHubCollector(output_dir=str(custom_dir))
        assert collector.output_dir == custom_dir


class TestConvenienceFunctions:
    """Test convenience function signatures."""

    def test_collect_repos_signature(self):
        """Test collect_repos has correct default parameters."""
        import inspect

        sig = inspect.signature(collect_repos)
        params = sig.parameters

        assert "token" in params
        assert "output_dir" in params
        assert params["output_dir"].default == "data/raw"

    def test_run_all_signature(self):
        """Test run_all has correct parameters."""
        import inspect

        sig = inspect.signature(run_all)
        params = sig.parameters

        assert "token" in params
        assert "output_dir" in params
        assert "kwargs" in params  # **kwargs for flexibility


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
