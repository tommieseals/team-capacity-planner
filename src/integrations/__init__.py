"""
Team Capacity Planner - Integrations

This module provides integrations with external services:
- GitHub: PRs, issues, reviews
- Jira: Tickets, sprints, story points  
- Calendar: PTO, meetings (Google/Outlook)
"""

from .github import GitHubClient, GitHubUser, PullRequest, Issue, get_github_workload
from .jira import JiraClient, JiraUser, JiraTicket, Sprint, get_jira_workload
from .calendar import (
    CalendarClient,
    GoogleCalendarClient,
    OutlookCalendarClient,
    CalendarEvent,
    PTOPeriod,
    UserAvailability,
    get_team_pto_conflicts
)

__all__ = [
    # GitHub
    "GitHubClient",
    "GitHubUser", 
    "PullRequest",
    "Issue",
    "get_github_workload",
    
    # Jira
    "JiraClient",
    "JiraUser",
    "JiraTicket",
    "Sprint",
    "get_jira_workload",
    
    # Calendar
    "CalendarClient",
    "GoogleCalendarClient",
    "OutlookCalendarClient",
    "CalendarEvent",
    "PTOPeriod",
    "UserAvailability",
    "get_team_pto_conflicts",
]
