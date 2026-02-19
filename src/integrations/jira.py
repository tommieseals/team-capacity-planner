"""
Jira Integration for Team Capacity Planner

Pulls tickets, sprints, and story points from Jira.
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field
from enum import Enum

import httpx


class TicketStatus(Enum):
    """Standard Jira ticket statuses."""
    TODO = "To Do"
    IN_PROGRESS = "In Progress"
    IN_REVIEW = "In Review"
    DONE = "Done"
    BLOCKED = "Blocked"


@dataclass
class JiraTicket:
    """Represents a Jira ticket/issue."""
    key: str
    summary: str
    status: str
    assignee: Optional[str]
    story_points: Optional[float] = None
    issue_type: str = "Task"
    priority: str = "Medium"
    sprint_id: Optional[int] = None
    sprint_name: Optional[str] = None
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    labels: list[str] = field(default_factory=list)
    
    @property
    def is_done(self) -> bool:
        return self.status.lower() in ["done", "closed", "resolved"]
    
    @property
    def is_in_progress(self) -> bool:
        return "progress" in self.status.lower()
    
    @property
    def is_blocked(self) -> bool:
        return "blocked" in self.status.lower() or "blocked" in [l.lower() for l in self.labels]


@dataclass
class Sprint:
    """Represents a Jira Sprint."""
    id: int
    name: str
    state: str  # active, closed, future
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    goal: Optional[str] = None
    
    @property
    def is_active(self) -> bool:
        return self.state == "active"
    
    @property
    def days_remaining(self) -> int:
        if not self.end_date:
            return 0
        return max(0, (self.end_date - datetime.now()).days)
    
    @property
    def progress_percentage(self) -> float:
        """How far through the sprint are we."""
        if not self.start_date or not self.end_date:
            return 0
        
        total = (self.end_date - self.start_date).days
        elapsed = (datetime.now() - self.start_date).days
        return min(100, max(0, (elapsed / total) * 100))


@dataclass
class JiraUser:
    """Jira user with workload data."""
    account_id: str
    display_name: str
    email: Optional[str] = None
    assigned_tickets: list[JiraTicket] = field(default_factory=list)
    
    @property
    def total_story_points(self) -> float:
        """Sum of story points for assigned tickets."""
        return sum(t.story_points or 0 for t in self.assigned_tickets)
    
    @property
    def tickets_in_progress(self) -> int:
        return len([t for t in self.assigned_tickets if t.is_in_progress])
    
    @property
    def tickets_blocked(self) -> int:
        return len([t for t in self.assigned_tickets if t.is_blocked])
    
    @property
    def workload_score(self) -> float:
        """Calculate workload score from Jira activity."""
        return (
            self.total_story_points * 1.0 +
            self.tickets_in_progress * 2.0 +
            self.tickets_blocked * 3.0  # Blocked items are stressful!
        )


class JiraClient:
    """
    Jira Cloud API client for fetching sprint and ticket data.
    
    Usage:
        client = JiraClient(
            url="https://company.atlassian.net",
            email="user@company.com",
            token="api_token"
        )
        sprint = await client.get_active_sprint("PROJ")
        tickets = await client.get_sprint_tickets(sprint.id)
    """
    
    def __init__(
        self,
        url: Optional[str] = None,
        email: Optional[str] = None,
        token: Optional[str] = None,
        project: Optional[str] = None
    ):
        self.url = (url or os.getenv("JIRA_URL", "")).rstrip("/")
        self.email = email or os.getenv("JIRA_EMAIL")
        self.token = token or os.getenv("JIRA_TOKEN")
        self.project = project or os.getenv("JIRA_PROJECT")
        
        if not all([self.url, self.email, self.token]):
            raise ValueError(
                "Jira credentials required. Set JIRA_URL, JIRA_EMAIL, JIRA_TOKEN env vars "
                "or pass them as parameters."
            )
        
        self.auth = (self.email, self.token)
    
    async def _request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None
    ) -> dict:
        """Make authenticated request to Jira API."""
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"{self.url}/rest/api/3{endpoint}",
                auth=self.auth,
                params=params,
                json=json,
                headers={"Accept": "application/json"},
                timeout=30.0
            )
            response.raise_for_status()
            return response.json() if response.content else {}
    
    async def _agile_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[dict] = None
    ) -> dict:
        """Make request to Jira Agile API."""
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"{self.url}/rest/agile/1.0{endpoint}",
                auth=self.auth,
                params=params,
                headers={"Accept": "application/json"},
                timeout=30.0
            )
            response.raise_for_status()
            return response.json() if response.content else {}
    
    async def get_boards(self, project: Optional[str] = None) -> list[dict]:
        """Get all boards for a project."""
        project = project or self.project
        params = {"projectKeyOrId": project} if project else {}
        result = await self._agile_request("GET", "/board", params)
        return result.get("values", [])
    
    async def get_sprints(
        self,
        board_id: int,
        state: Optional[str] = None
    ) -> list[Sprint]:
        """
        Get sprints for a board.
        
        Args:
            board_id: Jira board ID
            state: Filter by state (active, closed, future)
        """
        params = {}
        if state:
            params["state"] = state
        
        result = await self._agile_request("GET", f"/board/{board_id}/sprint", params)
        
        sprints = []
        for s in result.get("values", []):
            sprints.append(Sprint(
                id=s["id"],
                name=s["name"],
                state=s["state"],
                start_date=datetime.fromisoformat(s["startDate"].replace("Z", "+00:00")) if s.get("startDate") else None,
                end_date=datetime.fromisoformat(s["endDate"].replace("Z", "+00:00")) if s.get("endDate") else None,
                goal=s.get("goal")
            ))
        
        return sprints
    
    async def get_active_sprint(self, project: Optional[str] = None) -> Optional[Sprint]:
        """Get the currently active sprint for a project."""
        project = project or self.project
        boards = await self.get_boards(project)
        
        if not boards:
            return None
        
        # Use the first board (usually there's only one per project)
        board_id = boards[0]["id"]
        sprints = await self.get_sprints(board_id, state="active")
        
        return sprints[0] if sprints else None
    
    async def get_sprint_tickets(
        self,
        sprint_id: int,
        include_done: bool = True
    ) -> list[JiraTicket]:
        """Get all tickets in a sprint."""
        jql = f"sprint = {sprint_id}"
        if not include_done:
            jql += " AND status != Done"
        
        return await self.search_tickets(jql)
    
    async def search_tickets(
        self,
        jql: str,
        max_results: int = 100
    ) -> list[JiraTicket]:
        """
        Search for tickets using JQL.
        
        Args:
            jql: Jira Query Language string
            max_results: Maximum tickets to return
        """
        result = await self._request(
            "GET",
            "/search",
            params={
                "jql": jql,
                "maxResults": max_results,
                "fields": "summary,status,assignee,customfield_10016,issuetype,priority,labels,sprint,created,updated"
            }
        )
        
        tickets = []
        for issue in result.get("issues", []):
            fields = issue["fields"]
            
            # Extract sprint info if available
            sprint_data = fields.get("sprint") or (fields.get("sprint") or [None])[0] if isinstance(fields.get("sprint"), list) else None
            
            assignee = fields.get("assignee")
            
            tickets.append(JiraTicket(
                key=issue["key"],
                summary=fields["summary"],
                status=fields["status"]["name"],
                assignee=assignee["displayName"] if assignee else None,
                story_points=fields.get("customfield_10016"),  # Story points field
                issue_type=fields["issuetype"]["name"],
                priority=fields["priority"]["name"] if fields.get("priority") else "Medium",
                sprint_id=sprint_data["id"] if sprint_data else None,
                sprint_name=sprint_data["name"] if sprint_data else None,
                labels=fields.get("labels", []),
                created=datetime.fromisoformat(fields["created"].replace("Z", "+00:00")) if fields.get("created") else None,
                updated=datetime.fromisoformat(fields["updated"].replace("Z", "+00:00")) if fields.get("updated") else None
            ))
        
        return tickets
    
    async def get_user_tickets(
        self,
        user: str,
        project: Optional[str] = None,
        include_done: bool = False
    ) -> list[JiraTicket]:
        """Get tickets assigned to a specific user."""
        project = project or self.project
        jql = f'assignee = "{user}"'
        
        if project:
            jql += f" AND project = {project}"
        
        if not include_done:
            jql += " AND status != Done"
        
        return await self.search_tickets(jql)
    
    async def get_team_workload(
        self,
        users: list[str],
        project: Optional[str] = None
    ) -> list[JiraUser]:
        """
        Get workload data for a list of users.
        
        Args:
            users: List of user display names or account IDs
            project: Optional project filter
        """
        workloads = []
        
        for user in users:
            tickets = await self.get_user_tickets(user, project)
            
            jira_user = JiraUser(
                account_id=user,  # Ideally would look up actual account ID
                display_name=user,
                assigned_tickets=tickets
            )
            workloads.append(jira_user)
        
        # Sort by workload score descending
        workloads.sort(key=lambda u: u.workload_score, reverse=True)
        
        return workloads
    
    async def get_sprint_burndown_data(self, sprint_id: int) -> dict:
        """
        Get data for sprint burndown chart.
        
        Returns:
            Dictionary with daily progress data
        """
        tickets = await self.get_sprint_tickets(sprint_id)
        
        total_points = sum(t.story_points or 0 for t in tickets)
        done_points = sum(t.story_points or 0 for t in tickets if t.is_done)
        in_progress_points = sum(t.story_points or 0 for t in tickets if t.is_in_progress)
        
        return {
            "total_points": total_points,
            "done_points": done_points,
            "in_progress_points": in_progress_points,
            "remaining_points": total_points - done_points,
            "completion_percentage": (done_points / total_points * 100) if total_points > 0 else 0,
            "tickets_total": len(tickets),
            "tickets_done": len([t for t in tickets if t.is_done]),
            "tickets_in_progress": len([t for t in tickets if t.is_in_progress]),
            "tickets_blocked": len([t for t in tickets if t.is_blocked])
        }
    
    async def get_velocity_history(
        self,
        project: Optional[str] = None,
        num_sprints: int = 5
    ) -> list[dict]:
        """
        Get velocity data for recent completed sprints.
        
        Returns:
            List of sprint velocity data
        """
        project = project or self.project
        boards = await self.get_boards(project)
        
        if not boards:
            return []
        
        board_id = boards[0]["id"]
        sprints = await self.get_sprints(board_id, state="closed")
        
        # Get most recent sprints
        sprints = sorted(sprints, key=lambda s: s.end_date or datetime.min, reverse=True)[:num_sprints]
        
        velocity_data = []
        for sprint in sprints:
            tickets = await self.get_sprint_tickets(sprint.id)
            completed_points = sum(t.story_points or 0 for t in tickets if t.is_done)
            committed_points = sum(t.story_points or 0 for t in tickets)
            
            velocity_data.append({
                "sprint_name": sprint.name,
                "sprint_id": sprint.id,
                "end_date": sprint.end_date.isoformat() if sprint.end_date else None,
                "committed_points": committed_points,
                "completed_points": completed_points,
                "completion_rate": (completed_points / committed_points * 100) if committed_points > 0 else 0
            })
        
        return velocity_data


# Convenience function
async def get_jira_workload(
    url: str,
    email: str,
    token: str,
    project: str,
    users: list[str]
) -> list[JiraUser]:
    """
    Quick function to get team workload from Jira.
    
    Example:
        workloads = await get_jira_workload(
            url="https://company.atlassian.net",
            email="user@company.com",
            token="api_token",
            project="PROJ",
            users=["Alice", "Bob", "Carol"]
        )
        
        for user in workloads:
            print(f"{user.display_name}: {user.total_story_points} points")
    """
    client = JiraClient(url=url, email=email, token=token, project=project)
    return await client.get_team_workload(users, project)
