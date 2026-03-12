"""
GitHub API data collector for RAG system.

This module collects various types of GitHub data:
- Repositories (owned and contributed to)
- Commits
- Issues and Pull Requests
- Gists
- Starred repositories
"""

import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from pathlib import Path

from github import Github, GithubException
from github.Repository import Repository
from github.Gist import Gist
from github.Issue import Issue
from github.Commit import Commit

logger = logging.getLogger(__name__)


class GitHubCollector:
    """Collects data from GitHub using the PyGithub library."""

    def __init__(self, token: Optional[str] = None, output_dir: str = "data/raw"):
        """
        Initialize the GitHub collector.

        Args:
            token: GitHub personal access token. If None, reads from GITHUB_TOKEN env var.
            output_dir: Directory to save collected data

        Raises:
            ValueError: If no GitHub token is provided
        """
        self.token = token or os.getenv("GITHUB_TOKEN")
        if not self.token:
            raise ValueError(
                "GitHub token is required. Set GITHUB_TOKEN environment variable "
                "or pass token directly."
            )

        self.g = Github(self.token)
        self.user = self.g.get_user()
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Don't access user.login here to avoid API call on init
        logger.info("Initialized GitHub collector")

    def collect_repos(
        self,
        include_forks: bool = True,
        include_private: bool = True,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Collect repositories owned by the authenticated user.

        Args:
            include_forks: Whether to include forked repositories
            include_private: Whether to include private repositories
            limit: Maximum number of repositories to collect (None for all)

        Returns:
            List of repository data dictionaries
        """
        logger.info("Collecting repositories...")
        repos_data = []
        count = 0

        try:
            repos = self.user.get_repos()
            if limit:
                repos = list(repos)[:limit]

            for repo in repos:
                try:
                    # Apply filters
                    if not include_forks and repo.fork:
                        continue
                    if not include_private and repo.private:
                        continue

                    repo_info = {
                        "id": repo.id,
                        "name": repo.name,
                        "full_name": repo.full_name,
                        "description": repo.description,
                        "url": repo.html_url,
                        "private": repo.private,
                        "fork": repo.fork,
                        "created_at": repo.created_at.isoformat()
                        if repo.created_at
                        else None,
                        "updated_at": repo.updated_at.isoformat()
                        if repo.updated_at
                        else None,
                        "language": repo.language,
                        "stargazers_count": repo.stargazers_count,
                        "forks_count": repo.forks_count,
                        "open_issues_count": repo.open_issues_count,
                        "topics": repo.get_topics(),
                        "license": repo.license.key if repo.license else None,
                        "size": repo.size,
                        "owner": {
                            "login": repo.owner.login,
                            "type": repo.owner.type,
                            "url": repo.owner.html_url,
                        },
                    }
                    repos_data.append(repo_info)
                    count += 1

                    if count % 10 == 0:
                        logger.info(f"Collected {count} repositories...")

                except GithubException as e:
                    logger.warning(f"Error collecting repo {repo.full_name}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Unexpected error for repo {repo.full_name}: {e}")
                    continue

        except GithubException as e:
            logger.error(f"GitHub API error while collecting repos: {e}")
            raise

        logger.info(f"Successfully collected {len(repos_data)} repositories")
        return repos_data

    def collect_commits(
        self, repo_full_names: Optional[List[str]] = None, limit_per_repo: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Collect commits from repositories.

        Args:
            repo_full_names: List of repository full names. If None, uses user's repos.
            limit_per_repo: Maximum commits to collect per repository

        Returns:
            List of commit data dictionaries
        """
        logger.info("Collecting commits...")
        commits_data = []

        # If no repos specified, get user's repos
        if repo_full_names is None:
            repos = self.user.get_repos()
            repo_full_names = [repo.full_name for repo in repos]

        for repo_name in repo_full_names:
            try:
                logger.info(f"Collecting commits from {repo_name}...")
                repo = self.g.get_repo(repo_name)

                count = 0
                try:
                    commits = repo.get_commits()
                    for commit in commits:
                        if count >= limit_per_repo:
                            break

                        commit_info = {
                            "sha": commit.sha,
                            "message": commit.commit.message,
                            "author": {
                                "name": commit.commit.author.name,
                                "email": commit.commit.author.email,
                                "date": commit.commit.author.date.isoformat()
                                if commit.commit.author.date
                                else None,
                            },
                            "committer": {
                                "name": commit.commit.committer.name,
                                "email": commit.commit.committer.email,
                                "date": commit.commit.committer.date.isoformat()
                                if commit.commit.committer.date
                                else None,
                            },
                            "url": commit.html_url,
                            "repo": repo_name,
                            "parents": [p.sha for p in commit.parents],
                        }
                        commits_data.append(commit_info)
                        count += 1

                except GithubException as e:
                    logger.warning(f"Error getting commits for {repo_name}: {e}")
                    continue

            except GithubException as e:
                logger.warning(f"Error accessing repo {repo_name}: {e}")
                continue

        logger.info(f"Successfully collected {len(commits_data)} commits")
        return commits_data

    def collect_issues(
        self,
        repo_full_names: Optional[List[str]] = None,
        state: str = "all",
        limit_per_repo: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Collect issues and pull requests from repositories.

        Args:
            repo_full_names: List of repository full names. If None, uses user's repos.
            state: Issue state - "open", "closed", or "all"
            limit_per_repo: Maximum issues to collect per repository

        Returns:
            List of issue data dictionaries
        """
        logger.info("Collecting issues and pull requests...")
        issues_data = []

        if repo_full_names is None:
            repos = self.user.get_repos()
            repo_full_names = [repo.full_name for repo in repos]

        for repo_name in repo_full_names:
            try:
                logger.info(f"Collecting issues from {repo_name}...")
                repo = self.g.get_repo(repo_name)

                count = 0
                try:
                    issues = repo.get_issues(
                        state=state, sort="updated", direction="desc"
                    )
                    for issue in issues:
                        if count >= limit_per_repo:
                            break

                        # Check if it's a pull request
                        is_pr = issue.pull_request is not None

                        issue_info = {
                            "id": issue.id,
                            "number": issue.number,
                            "title": issue.title,
                            "body": issue.body,
                            "state": issue.state,
                            "is_pull_request": is_pr,
                            "url": issue.html_url,
                            "repo": repo_name,
                            "created_at": issue.created_at.isoformat()
                            if issue.created_at
                            else None,
                            "updated_at": issue.updated_at.isoformat()
                            if issue.updated_at
                            else None,
                            "closed_at": issue.closed_at.isoformat()
                            if issue.closed_at
                            else None,
                            "user": {
                                "login": issue.user.login,
                                "url": issue.user.html_url,
                            }
                            if issue.user
                            else None,
                            "labels": [label.name for label in issue.labels],
                            "comments_count": issue.comments,
                            "assignees": [
                                {"login": a.login, "url": a.html_url}
                                for a in issue.assignees
                            ],
                        }
                        issues_data.append(issue_info)
                        count += 1

                except GithubException as e:
                    logger.warning(f"Error getting issues for {repo_name}: {e}")
                    continue

            except GithubException as e:
                logger.warning(f"Error accessing repo {repo_name}: {e}")
                continue

        logger.info(f"Successfully collected {len(issues_data)} issues/pull requests")
        return issues_data

    def collect_gists(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Collect gists created by the authenticated user.

        Args:
            limit: Maximum number of gists to collect

        Returns:
            List of gist data dictionaries
        """
        logger.info("Collecting gists...")
        gists_data = []
        count = 0

        try:
            gists = self.user.get_gists()
            if limit:
                gists = list(gists)[:limit]

            for gist in gists:
                try:
                    # Get files in the gist
                    files_info = []
                    for filename, file_obj in gist.files.items():
                        files_info.append(
                            {
                                "filename": filename,
                                "size": file_obj.size,
                                "language": file_obj.language,
                                "raw_url": file_obj.raw_url,
                            }
                        )

                    gist_info = {
                        "id": gist.id,
                        "description": gist.description,
                        "url": gist.html_url,
                        "created_at": gist.created_at.isoformat()
                        if gist.created_at
                        else None,
                        "updated_at": gist.updated_at.isoformat()
                        if gist.updated_at
                        else None,
                        "files": files_info,
                        "forks_count": gist.forks,
                        "comments_count": gist.comments,
                        "public": gist.public,
                    }
                    gists_data.append(gist_info)
                    count += 1

                except GithubException as e:
                    logger.warning(f"Error collecting gist {gist.id}: {e}")
                    continue
                except Exception as e:
                    logger.warning(f"Unexpected error for gist {gist.id}: {e}")
                    continue

        except GithubException as e:
            logger.error(f"GitHub API error while collecting gists: {e}")
            raise

        logger.info(f"Successfully collected {len(gists_data)} gists")
        return gists_data

    def collect_starred(
        self,
        limit: Optional[int] = None,
        sort: str = "created",
        direction: str = "desc",
    ) -> List[Dict[str, Any]]:
        """
        Collect repositories starred by the authenticated user.

        Args:
            limit: Maximum number of starred repos to collect
            sort: Sorting method - "created" or "updated"
            direction: Sort direction - "asc" or "desc"

        Returns:
            List of starred repository data dictionaries
        """
        logger.info("Collecting starred repositories...")
        starred_data = []
        count = 0

        try:
            starred = self.user.get_starred()
            if sort:
                starred = sorted(
                    starred,
                    key=lambda r: r.created_at if sort == "created" else r.updated_at,
                    reverse=(direction == "desc"),
                )
            if limit:
                starred = list(starred)[:limit]

            for repo in starred:
                try:
                    star_info = {
                        "id": repo.id,
                        "name": repo.name,
                        "full_name": repo.full_name,
                        "description": repo.description,
                        "url": repo.html_url,
                        "private": repo.private,
                        "language": repo.language,
                        "stargazers_count": repo.stargazers_count,
                        "forks_count": repo.forks_count,
                        "owner": {
                            "login": repo.owner.login,
                            "type": repo.owner.type,
                            "url": repo.owner.html_url,
                        },
                    }
                    starred_data.append(star_info)
                    count += 1

                    if count % 20 == 0:
                        logger.info(f"Collected {count} starred repositories...")

                except GithubException as e:
                    logger.warning(
                        f"Error collecting starred repo {repo.full_name}: {e}"
                    )
                    continue
                except Exception as e:
                    logger.warning(
                        f"Unexpected error for starred repo {repo.full_name}: {e}"
                    )
                    continue

        except GithubException as e:
            logger.error(f"GitHub API error while collecting starred repos: {e}")
            raise

        logger.info(f"Successfully collected {len(starred_data)} starred repositories")
        return starred_data

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

    def run_all_collections(
        self,
        repos_limit: Optional[int] = None,
        commits_limit_per_repo: int = 50,
        issues_limit_per_repo: int = 50,
        gists_limit: Optional[int] = None,
        starred_limit: Optional[int] = None,
    ) -> Dict[str, Path]:
        """
        Run all collection methods and save results.

        Args:
            repos_limit: Limit for repositories collection
            commits_limit_per_repo: Max commits per repository
            issues_limit_per_repo: Max issues per repository
            gists_limit: Limit for gists collection
            starred_limit: Limit for starred repositories

        Returns:
            Dictionary mapping collection names to output file paths
        """
        logger.info("Starting full GitHub data collection...")
        results = {}

        # Collect repositories
        repos = self.collect_repos(limit=repos_limit)
        results["repos"] = self.save_to_json(repos, "github_repos.json")

        # Collect commits (from user's repos)
        repo_names = [repo["full_name"] for repo in repos]
        commits = self.collect_commits(
            repo_names, limit_per_repo=commits_limit_per_repo
        )
        results["commits"] = self.save_to_json(commits, "github_commits.json")

        # Collect issues
        issues = self.collect_issues(repo_names, limit_per_repo=issues_limit_per_repo)
        results["issues"] = self.save_to_json(issues, "github_issues.json")

        # Collect gists
        gists = self.collect_gists(limit=gists_limit)
        results["gists"] = self.save_to_json(gists, "github_gists.json")

        # Collect starred repos
        starred = self.collect_starred(limit=starred_limit)
        results["starred"] = self.save_to_json(starred, "github_starred.json")

        logger.info("Full collection complete!")
        logger.info(f"Results saved to:")
        for name, path in results.items():
            logger.info(f"  {name}: {path}")

        return results


def collect_repos(token=None, output_dir="data/raw", **kwargs) -> List[Dict[str, Any]]:
    """
    Convenience function to collect only repositories.

    Args:
        token: GitHub token (uses GITHUB_TOKEN env var if None)
        output_dir: Directory to save output
        **kwargs: Additional arguments passed to GitHubCollector.collect_repos()

    Returns:
        List of repository data dictionaries
    """
    collector = GitHubCollector(token=token, output_dir=output_dir)
    return collector.collect_repos(**kwargs)


def collect_commits(
    token=None, output_dir="data/raw", repo_full_names=None, **kwargs
) -> List[Dict[str, Any]]:
    """
    Convenience function to collect only commits.

    Args:
        token: GitHub token (uses GITHUB_TOKEN env var if None)
        output_dir: Directory to save output
        repo_full_names: List of repository full names
        **kwargs: Additional arguments passed to GitHubCollector.collect_commits()

    Returns:
        List of commit data dictionaries
    """
    collector = GitHubCollector(token=token, output_dir=output_dir)
    return collector.collect_commits(repo_full_names=repo_full_names, **kwargs)


def collect_issues(
    token=None, output_dir="data/raw", repo_full_names=None, **kwargs
) -> List[Dict[str, Any]]:
    """
    Convenience function to collect only issues.

    Args:
        token: GitHub token (uses GITHUB_TOKEN env var if None)
        output_dir: Directory to save output
        repo_full_names: List of repository full names
        **kwargs: Additional arguments passed to GitHubCollector.collect_issues()

    Returns:
        List of issue data dictionaries
    """
    collector = GitHubCollector(token=token, output_dir=output_dir)
    return collector.collect_issues(repo_full_names=repo_full_names, **kwargs)


def collect_gists(token=None, output_dir="data/raw", **kwargs) -> List[Dict[str, Any]]:
    """
    Convenience function to collect only gists.

    Args:
        token: GitHub token (uses GITHUB_TOKEN env var if None)
        output_dir: Directory to save output
        **kwargs: Additional arguments passed to GitHubCollector.collect_gists()

    Returns:
        List of gist data dictionaries
    """
    collector = GitHubCollector(token=token, output_dir=output_dir)
    return collector.collect_gists(**kwargs)


def collect_starred(
    token=None, output_dir="data/raw", **kwargs
) -> List[Dict[str, Any]]:
    """
    Convenience function to collect only starred repositories.

    Args:
        token: GitHub token (uses GITHUB_TOKEN env var if None)
        output_dir: Directory to save output
        **kwargs: Additional arguments passed to GitHubCollector.collect_starred()

    Returns:
        List of starred repository data dictionaries
    """
    collector = GitHubCollector(token=token, output_dir=output_dir)
    return collector.collect_starred(**kwargs)


def run_all(token=None, output_dir="data/raw", **kwargs) -> Dict[str, Path]:
    """
    Convenience function to run all collection methods.

    Args:
        token: GitHub token (uses GITHUB_TOKEN env var if None)
        output_dir: Directory to save output
        **kwargs: Additional arguments passed to GitHubCollector.run_all_collections()

    Returns:
        Dictionary mapping collection names to output file paths
    """
    collector = GitHubCollector(token=token, output_dir=output_dir)
    return collector.run_all_collections(**kwargs)
