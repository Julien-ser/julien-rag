#!/usr/bin/env python3
"""
Example usage of the GitHub collector.

This script demonstrates how to use the GitHubCollector to collect
various types of data from GitHub.
"""

import os
import json
from src.github_collector import GitHubCollector, run_all


def example_basic_collection():
    """Example: Basic collection using environment token."""
    # Ensure GITHUB_TOKEN is set in your .env file
    collector = GitHubCollector()

    # Collect repositories
    repos = collector.collect_repos(limit=10)
    print(f"Collected {len(repos)} repositories")

    # Save to file
    collector.save_to_json(repos, "example_repos.json")


def example_selective_collection():
    """Example: Collection with specific options."""
    collector = GitHubCollector()

    # Collect only your own repositories (exclude forks and private)
    repos = collector.collect_repos(include_forks=False, include_private=False)

    # Get commit history for your repositories
    repo_names = [repo["full_name"] for repo in repos]
    commits = collector.collect_commits(repo_names[:3], limit_per_repo=20)

    # Get issues from your repositories
    issues = collector.collect_issues(repo_names[:3], state="open", limit_per_repo=20)

    # Collect your gists
    gists = collector.collect_gists(limit=10)

    # Collect starred repositories
    starred = collector.collect_starred(limit=20)

    print(
        f"Repos: {len(repos)}, Commits: {len(commits)}, "
        f"Issues: {len(issues)}, Gists: {len(gists)}, Starred: {len(starred)}"
    )


def example_full_pipeline():
    """Example: Run all collections at once."""
    results = run_all(
        repos_limit=20,
        commits_limit_per_repo=30,
        issues_limit_per_repo=30,
        gists_limit=10,
        starred_limit=50,
    )

    print("Collection complete! Files saved:")
    for collection_type, filepath in results.items():
        print(f"  {collection_type}: {filepath}")


if __name__ == "__main__":
    # Make sure we're in the right directory
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print("GitHub Collector Examples")
    print("=" * 50)

    # Check for GitHub token
    if not os.getenv("GITHUB_TOKEN"):
        print("\nWARNING: GITHUB_TOKEN environment variable not set!")
        print("Please set your GitHub token:")
        print("  export GITHUB_TOKEN='your_token_here'")
        print("Or add it to your .env file")
        print("\nYou can create a token at: https://github.com/settings/tokens")
        print(
            "Required scopes: repo (for private repos if needed), public_repo, gist, user:read"
        )
    else:
        print("\nRunning full pipeline example...")
        try:
            example_full_pipeline()
        except Exception as e:
            print(f"Error: {e}")
            print("\nMake sure your token has the necessary permissions.")
