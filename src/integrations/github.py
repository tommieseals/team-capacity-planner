"""
GitHub Integration for Team Capacity Planner

Pulls PRs, issues, reviews, and commit activity from GitHub.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field

import httpx


@dataclass
class GitHubUser:
    """Represents a GitHub user with workload metrics."""
    login: str
    name: Optional[str] = None
    open_prs: int = 0
    pending_reviews: int = 0
    assigned_issues: int = 0
    recent_commits: int = 0
    
    @property
    def workload_score(self) -> float:
        """Calculate workload score based on GitHub activity."""
        return (
            self.open_prs * 3.0 +
            self.pending_reviews * 2.0 +
            self.assigned_issues * 2.0 +
            self.recent_commits * 0.5
        )


@dataclass
class PullRequest:
    """Represents a GitHub Pull Request."""
    number: int
    title: str
    author: str
    state: str
    created_at: datetime
    updated_at: datetime
    reviewers: list[str] = field(default_factory=list)
    review_status: str = "pending"
    additions: int = 0
    deletions: int = 0
    
    @property
    def age_days(self) -> int:
        """How old is this PR in days."""
        return (datetime.now() - self.created_at).days
    
    @property
    def complexity_score(self) -> float:
        """Estimate PR complexity based on size."""
        lines = self.additions + self.deletions
        if lines < 50:
            return 1.0
        elif lines < 200:
            return 2.0
        elif lines < 500:
            return 3.0
        else:
            return 5.0


@dataclass 
class Issue:
    """Represents a GitHub Issue."""
    number: int
    title: str
    assignee: Optional[str]
    state: str
    labels: list[str] = field(default_factory=list)
    created_at: datetime = None
    
    @property
    def is_bug(self) -> bool:
        return any('bug' in label.lower() for label in self.labels)
    
    @property
    def priority(self) -> str:
        """Extract priority from labels."""
        for label in self.labels:
            if 'p0' in label.lower() or 'critical' in label.lower():
                return 'critical'
            elif 'p1' in label.lower() or 'high' in label.lower():
                return 'high'
            elif 'p2' in label.lower() or 'medium' in label.lower():
                return 'medium'
        return 'normal'


class GitHubClient:
    """
    GitHub API client for fetching team workload data.
    
    Usage:
        client = GitHubClient(token="ghp_xxx", org="mycompany")
        workloads = await client.get_team_workload(team="engineering")
    """
    
    BASE_URL = "https://api.github.com"
    
    def __init__(
        self,
        token: Optional[str] = None,
        org: Optional[str] = None,
        repos: Optional[list[str]] = None
    ):
        self.token = token or os.getenv("GITHUB_TOKEN")
        self.org = org or os.getenv("GITHUB_ORG")
        self.repos = repos or []
        
        if not self.token:
            raise ValueError("GitHub token required. Set GITHUB_TOKEN env var or pass token parameter.")
        
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
    
    async def _request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make authenticated request to GitHub API."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.BASE_URL}{endpoint}",
                headers=self.headers,
                params=params,
                timeout=30.0
            )
            response.raise_for_status()
            return response.json()
    
    async def _paginate(self, endpoint: str, params: Optional[dict] = None) -> list:
        """Paginate through all results."""
        params = params or {}
        params["per_page"] = 100
        params["page"] = 1
        
        all_results = []
        while True:
            results = await self._request(endpoint, params)
            if not results:
                break
            all_results.extend(results)
            if len(results) < 100:
                break
            params["page"] += 1
        
        return all_results
    
    async def get_org_members(self) -> list[str]:
        """Get all members of the organization."""
        if not self.org:
            raise ValueError("Organization not configured")
        
        members = await self._paginate(f"/orgs/{self.org}/members")
        return [m["login"] for m in members]
    
    async def get_team_members(self, team_slug: str) -> list[str]:
        """Get members of a specific team."""
        members = await self._paginate(f"/orgs/{self.org}/teams/{team_slug}/members")
        return [m["login"] for m in members]
    
    async def get_open_prs(self, repo: str) -> list[PullRequest]:
        """Get all open PRs for a repository."""
        owner = self.org or repo.split("/")[0]
        repo_name = repo if "/" not in repo else repo.split("/")[1]
        
        prs_data = await self._paginate(f"/repos/{owner}/{repo_name}/pulls", {"state": "open"})
        
        prs = []
        for pr in prs_data:
            reviewers = [r["login"] for r in pr.get("requested_reviewers", [])]
            prs.append(PullRequest(
                number=pr["number"],
                title=pr["title"],
                author=pr["user"]["login"],
                state=pr["state"],
                created_at=datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00")),
                updated_at=datetime.fromisoformat(pr["updated_at"].replace("Z", "+00:00")),
                reviewers=reviewers,
                additions=pr.get("additions", 0),
                deletions=pr.get("deletions", 0)
            ))
        
        return prs
    
    async def get_assigned_issues(self, repo: str, assignee: str) -> list[Issue]:
        """Get open issues assigned to a user."""
        owner = self.org or repo.split("/")[0]
        repo_name = repo if "/" not in repo else repo.split("/")[1]
        
        issues_data = await self._paginate(
            f"/repos/{owner}/{repo_name}/issues",
            {"state": "open", "assignee": assignee}
        )
        
        # Filter out PRs (they show up as issues too)
        issues = []
        for issue in issues_data:
            if "pull_request" not in issue:
                issues.append(Issue(
                    number=issue["number"],
                    title=issue["title"],
                    assignee=assignee,
                    state=issue["state"],
                    labels=[l["name"] for l in issue.get("labels", [])],
                    created_at=datetime.fromisoformat(issue["created_at"].replace("Z", "+00:00"))
                ))
        
        return issues
    
    async def get_pending_reviews(self, repo: str, reviewer: str) -> list[PullRequest]:
        """Get PRs waiting for review from a specific user."""
        all_prs = await self.get_open_prs(repo)
        return [pr for pr in all_prs if reviewer in pr.reviewers]
    
    async def get_recent_commits(
        self,
        repo: str,
        author: str,
        since_days: int = 7
    ) -> int:
        """Count commits by author in recent days."""
        owner = self.org or repo.split("/")[0]
        repo_name = repo if "/" not in repo else repo.split("/")[1]
        since = (datetime.now() - timedelta(days=since_days)).isoformat()
        
        commits = await self._paginate(
            f"/repos/{owner}/{repo_name}/commits",
            {"author": author, "since": since}
        )
        
        return len(commits)
    
    async def get_user_workload(self, username: str, repos: Optional[list[str]] = None) -> GitHubUser:
        """
        Calculate complete workload for a user across repositories.
        
        Args:
            username: GitHub username
            repos: List of repos to check (defaults to configured repos)
            
        Returns:
            GitHubUser with aggregated workload metrics
        """
        repos = repos or self.repos
        if not repos:
            raise ValueError("No repositories configured")
        
        user = GitHubUser(login=username)
        
        for repo in repos:
            # Count open PRs authored by user
            all_prs = await self.get_open_prs(repo)
            user.open_prs += len([pr for pr in all_prs if pr.author == username])
            
            # Count pending reviews
            user.pending_reviews += len([pr for pr in all_prs if username in pr.reviewers])
            
            # Count assigned issues
            issues = await self.get_assigned_issues(repo, username)
            user.assigned_issues += len(issues)
            
            # Count recent commits
            user.recent_commits += await self.get_recent_commits(repo, username)
        
        return user
    
    async def get_team_workload(
        self,
        team: Optional[str] = None,
        members: Optional[list[str]] = None,
        repos: Optional[list[str]] = None
    ) -> list[GitHubUser]:
        """
        Get workload for all team members.
        
        Args:
            team: Team slug (if using GitHub teams)
            members: Explicit list of usernames
            repos: Repositories to check
            
        Returns:
            List of GitHubUser objects with workload data
        """
        if team:
            members = await self.get_team_members(team)
        elif not members:
            members = await self.get_org_members()
        
        workloads = []
        for member in members:
            user = await self.get_user_workload(member, repos)
            workloads.append(user)
        
        # Sort by workload score descending
        workloads.sort(key=lambda u: u.workload_score, reverse=True)
        
        return workloads
    
    async def get_pr_review_stats(self, repo: str, days: int = 30) -> dict:
        """
        Get PR review statistics for the repository.
        
        Returns metrics like:
        - Average time to first review
        - Average time to merge
        - Review distribution by person
        """
        owner = self.org or repo.split("/")[0]
        repo_name = repo if "/" not in repo else repo.split("/")[1]
        since = (datetime.now() - timedelta(days=days)).isoformat()
        
        # Get recently merged PRs
        prs = await self._paginate(
            f"/repos/{owner}/{repo_name}/pulls",
            {"state": "closed", "sort": "updated", "direction": "desc"}
        )
        
        review_times = []
        merge_times = []
        reviewer_counts = {}
        
        for pr in prs:
            if not pr.get("merged_at"):
                continue
                
            created = datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
            merged = datetime.fromisoformat(pr["merged_at"].replace("Z", "+00:00"))
            
            if created < datetime.fromisoformat(since.replace("Z", "+00:00") if "Z" in since else since + "+00:00"):
                continue
            
            merge_times.append((merged - created).total_seconds() / 3600)  # hours
            
            # Count reviewers (would need additional API call for full data)
            for reviewer in pr.get("requested_reviewers", []):
                login = reviewer["login"]
                reviewer_counts[login] = reviewer_counts.get(login, 0) + 1
        
        return {
            "avg_merge_time_hours": sum(merge_times) / len(merge_times) if merge_times else 0,
            "total_prs_merged": len(merge_times),
            "review_distribution": reviewer_counts
        }


# Convenience function for quick usage
async def get_github_workload(
    token: str,
    org: str,
    repos: list[str],
    team: Optional[str] = None
) -> list[GitHubUser]:
    """
    Quick function to get team workload from GitHub.
    
    Example:
        workloads = await get_github_workload(
            token="ghp_xxx",
            org="mycompany", 
            repos=["frontend", "backend", "infra"],
            team="engineering"
        )
        
        for user in workloads:
            print(f"{user.login}: {user.workload_score}")
    """
    client = GitHubClient(token=token, org=org, repos=repos)
    return await client.get_team_workload(team=team)
