"""
Team Capacity Analyzer

Calculates workload scores and identifies overloaded team members.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from typing import Optional
from enum import Enum

from .integrations import GitHubUser, JiraUser, UserAvailability


class WorkloadStatus(Enum):
    """Workload health status."""
    HEALTHY = "healthy"      # 0-80%
    AT_CAPACITY = "at_capacity"  # 80-100%
    OVERLOADED = "overloaded"    # 100%+


@dataclass
class WorkloadWeights:
    """Configurable weights for workload calculation."""
    github_open_prs: float = 3.0
    github_pending_reviews: float = 2.0
    github_assigned_issues: float = 2.0
    github_recent_commits: float = 0.5
    jira_story_points: float = 1.0
    jira_in_progress: float = 2.0
    jira_blocked: float = 3.0
    meeting_hours: float = 0.5
    
    # Normalization factors (what's considered 100% in each category)
    max_open_prs: int = 5
    max_pending_reviews: int = 8
    max_assigned_issues: int = 10
    max_story_points: float = 13.0
    max_meeting_hours: float = 20.0


@dataclass
class TeamMemberWorkload:
    """Complete workload picture for a team member."""
    name: str
    email: Optional[str] = None
    
    # GitHub metrics
    github_open_prs: int = 0
    github_pending_reviews: int = 0
    github_assigned_issues: int = 0
    github_recent_commits: int = 0
    
    # Jira metrics
    jira_story_points: float = 0.0
    jira_tickets_in_progress: int = 0
    jira_tickets_blocked: int = 0
    
    # Calendar metrics
    meeting_hours_this_week: float = 0.0
    pto_days_upcoming: int = 0
    next_pto_date: Optional[date] = None
    
    # Calculated scores
    workload_score: float = 0.0
    workload_percentage: float = 0.0
    
    @property
    def status(self) -> WorkloadStatus:
        """Get workload status based on percentage."""
        if self.workload_percentage >= 100:
            return WorkloadStatus.OVERLOADED
        elif self.workload_percentage >= 80:
            return WorkloadStatus.AT_CAPACITY
        return WorkloadStatus.HEALTHY
    
    @property
    def status_emoji(self) -> str:
        """Get emoji for workload status."""
        return {
            WorkloadStatus.HEALTHY: "🟢",
            WorkloadStatus.AT_CAPACITY: "🟡",
            WorkloadStatus.OVERLOADED: "🔴"
        }[self.status]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "email": self.email,
            "github": {
                "open_prs": self.github_open_prs,
                "pending_reviews": self.github_pending_reviews,
                "assigned_issues": self.github_assigned_issues,
                "recent_commits": self.github_recent_commits
            },
            "jira": {
                "story_points": self.jira_story_points,
                "in_progress": self.jira_tickets_in_progress,
                "blocked": self.jira_tickets_blocked
            },
            "calendar": {
                "meeting_hours": self.meeting_hours_this_week,
                "pto_days_upcoming": self.pto_days_upcoming,
                "next_pto": self.next_pto_date.isoformat() if self.next_pto_date else None
            },
            "workload": {
                "score": round(self.workload_score, 1),
                "percentage": round(self.workload_percentage, 1),
                "status": self.status.value,
                "emoji": self.status_emoji
            }
        }


@dataclass
class TeamWorkloadSummary:
    """Summary of team workload."""
    members: list[TeamMemberWorkload] = field(default_factory=list)
    calculated_at: datetime = field(default_factory=datetime.now)
    
    @property
    def team_size(self) -> int:
        return len(self.members)
    
    @property
    def overloaded_count(self) -> int:
        return len([m for m in self.members if m.status == WorkloadStatus.OVERLOADED])
    
    @property
    def at_capacity_count(self) -> int:
        return len([m for m in self.members if m.status == WorkloadStatus.AT_CAPACITY])
    
    @property
    def healthy_count(self) -> int:
        return len([m for m in self.members if m.status == WorkloadStatus.HEALTHY])
    
    @property
    def average_workload(self) -> float:
        if not self.members:
            return 0
        return sum(m.workload_percentage for m in self.members) / len(self.members)
    
    @property
    def workload_variance(self) -> float:
        """Standard deviation of workload percentages."""
        if len(self.members) < 2:
            return 0
        
        avg = self.average_workload
        variance = sum((m.workload_percentage - avg) ** 2 for m in self.members) / len(self.members)
        return variance ** 0.5
    
    @property
    def is_balanced(self) -> bool:
        """Check if workload is reasonably balanced (variance < 30%)."""
        return self.workload_variance < 30
    
    def get_most_overloaded(self, n: int = 3) -> list[TeamMemberWorkload]:
        """Get the N most overloaded team members."""
        sorted_members = sorted(self.members, key=lambda m: m.workload_percentage, reverse=True)
        return sorted_members[:n]
    
    def get_available_capacity(self, n: int = 3) -> list[TeamMemberWorkload]:
        """Get team members with most available capacity."""
        sorted_members = sorted(self.members, key=lambda m: m.workload_percentage)
        return sorted_members[:n]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "calculated_at": self.calculated_at.isoformat(),
            "summary": {
                "team_size": self.team_size,
                "overloaded": self.overloaded_count,
                "at_capacity": self.at_capacity_count,
                "healthy": self.healthy_count,
                "average_workload": round(self.average_workload, 1),
                "variance": round(self.workload_variance, 1),
                "is_balanced": self.is_balanced
            },
            "members": [m.to_dict() for m in self.members]
        }


class WorkloadAnalyzer:
    """
    Analyzes team workload from multiple sources.
    
    Usage:
        analyzer = WorkloadAnalyzer()
        summary = analyzer.analyze(
            github_data=[GitHubUser(...)],
            jira_data=[JiraUser(...)],
            calendar_data=[UserAvailability(...)]
        )
    """
    
    def __init__(self, weights: Optional[WorkloadWeights] = None):
        self.weights = weights or WorkloadWeights()
    
    def _calculate_github_score(self, user: GitHubUser) -> float:
        """Calculate GitHub workload contribution."""
        return (
            user.open_prs * self.weights.github_open_prs +
            user.pending_reviews * self.weights.github_pending_reviews +
            user.assigned_issues * self.weights.github_assigned_issues +
            user.recent_commits * self.weights.github_recent_commits
        )
    
    def _calculate_jira_score(self, user: JiraUser) -> float:
        """Calculate Jira workload contribution."""
        return (
            user.total_story_points * self.weights.jira_story_points +
            user.tickets_in_progress * self.weights.jira_in_progress +
            user.tickets_blocked * self.weights.jira_blocked
        )
    
    def _calculate_calendar_score(self, availability: UserAvailability) -> float:
        """Calculate calendar/meeting workload contribution."""
        return availability.meeting_hours_this_week * self.weights.meeting_hours
    
    def _calculate_max_score(self) -> float:
        """Calculate theoretical maximum workload score (100%)."""
        return (
            self.weights.max_open_prs * self.weights.github_open_prs +
            self.weights.max_pending_reviews * self.weights.github_pending_reviews +
            self.weights.max_assigned_issues * self.weights.github_assigned_issues +
            self.weights.max_story_points * self.weights.jira_story_points +
            self.weights.max_meeting_hours * self.weights.meeting_hours
        )
    
    def analyze_member(
        self,
        name: str,
        github: Optional[GitHubUser] = None,
        jira: Optional[JiraUser] = None,
        calendar: Optional[UserAvailability] = None
    ) -> TeamMemberWorkload:
        """
        Analyze workload for a single team member.
        
        Args:
            name: Team member name
            github: GitHub workload data
            jira: Jira workload data
            calendar: Calendar/availability data
            
        Returns:
            TeamMemberWorkload with calculated scores
        """
        member = TeamMemberWorkload(name=name)
        total_score = 0.0
        
        # GitHub metrics
        if github:
            member.github_open_prs = github.open_prs
            member.github_pending_reviews = github.pending_reviews
            member.github_assigned_issues = github.assigned_issues
            member.github_recent_commits = github.recent_commits
            total_score += self._calculate_github_score(github)
        
        # Jira metrics
        if jira:
            member.jira_story_points = jira.total_story_points
            member.jira_tickets_in_progress = jira.tickets_in_progress
            member.jira_tickets_blocked = jira.tickets_blocked
            total_score += self._calculate_jira_score(jira)
        
        # Calendar metrics
        if calendar:
            member.email = calendar.email
            member.meeting_hours_this_week = calendar.meeting_hours_this_week
            
            if calendar.pto_periods:
                member.pto_days_upcoming = sum(p.days for p in calendar.pto_periods)
                next_pto = calendar.next_pto
                if next_pto:
                    member.next_pto_date = next_pto.start_date
            
            total_score += self._calculate_calendar_score(calendar)
        
        # Calculate final scores
        member.workload_score = total_score
        max_score = self._calculate_max_score()
        member.workload_percentage = (total_score / max_score) * 100 if max_score > 0 else 0
        
        return member
    
    def analyze(
        self,
        github_data: Optional[list[GitHubUser]] = None,
        jira_data: Optional[list[JiraUser]] = None,
        calendar_data: Optional[list[UserAvailability]] = None,
        team_members: Optional[list[str]] = None
    ) -> TeamWorkloadSummary:
        """
        Analyze workload for entire team.
        
        Matches data from different sources by username/name.
        
        Args:
            github_data: List of GitHub user workloads
            jira_data: List of Jira user workloads
            calendar_data: List of calendar availabilities
            team_members: Optional explicit list of team member names
            
        Returns:
            TeamWorkloadSummary with all member workloads
        """
        # Build lookup dictionaries
        github_lookup = {u.login.lower(): u for u in (github_data or [])}
        jira_lookup = {u.display_name.lower(): u for u in (jira_data or [])}
        calendar_lookup = {a.user.lower(): a for a in (calendar_data or [])}
        
        # Determine team members
        if team_members:
            names = team_members
        else:
            # Union of all names from all sources
            names = set(github_lookup.keys()) | set(jira_lookup.keys()) | set(calendar_lookup.keys())
        
        # Analyze each member
        members = []
        for name in names:
            name_lower = name.lower()
            member = self.analyze_member(
                name=name,
                github=github_lookup.get(name_lower),
                jira=jira_lookup.get(name_lower),
                calendar=calendar_lookup.get(name_lower)
            )
            members.append(member)
        
        # Sort by workload percentage descending
        members.sort(key=lambda m: m.workload_percentage, reverse=True)
        
        return TeamWorkloadSummary(members=members)
    
    def identify_overloaded(
        self,
        summary: TeamWorkloadSummary,
        threshold: float = 100.0
    ) -> list[TeamMemberWorkload]:
        """
        Get team members exceeding workload threshold.
        
        Args:
            summary: Team workload summary
            threshold: Percentage threshold (default 100%)
            
        Returns:
            List of overloaded team members
        """
        return [m for m in summary.members if m.workload_percentage >= threshold]
    
    def suggest_rebalancing(
        self,
        summary: TeamWorkloadSummary
    ) -> list[dict]:
        """
        Suggest work reassignments to balance team workload.
        
        Returns:
            List of suggested reassignments
        """
        suggestions = []
        
        overloaded = [m for m in summary.members if m.status == WorkloadStatus.OVERLOADED]
        available = [m for m in summary.members if m.status == WorkloadStatus.HEALTHY]
        
        for over in overloaded:
            # Find someone with capacity
            for avail in available:
                capacity_diff = over.workload_percentage - avail.workload_percentage
                
                if capacity_diff > 30:  # Only suggest if significant difference
                    suggestions.append({
                        "from": over.name,
                        "to": avail.name,
                        "from_load": round(over.workload_percentage, 1),
                        "to_load": round(avail.workload_percentage, 1),
                        "recommendation": f"Consider moving some work from {over.name} ({over.workload_percentage:.0f}%) to {avail.name} ({avail.workload_percentage:.0f}%)"
                    })
                    break  # One suggestion per overloaded person
        
        return suggestions


# Convenience function
def analyze_team_workload(
    github_data: Optional[list[GitHubUser]] = None,
    jira_data: Optional[list[JiraUser]] = None,
    calendar_data: Optional[list[UserAvailability]] = None,
    weights: Optional[WorkloadWeights] = None
) -> TeamWorkloadSummary:
    """
    Quick function to analyze team workload.
    
    Example:
        summary = analyze_team_workload(
            github_data=github_workloads,
            jira_data=jira_workloads
        )
        
        print(f"Team average: {summary.average_workload}%")
        for member in summary.get_most_overloaded():
            print(f"  {member.name}: {member.workload_percentage}%")
    """
    analyzer = WorkloadAnalyzer(weights=weights)
    return analyzer.analyze(github_data, jira_data, calendar_data)
