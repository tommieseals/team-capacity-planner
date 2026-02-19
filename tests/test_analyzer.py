"""
Tests for the workload analyzer.
"""

import pytest
from datetime import date

from src.analyzer import (
    WorkloadAnalyzer,
    TeamMemberWorkload,
    TeamWorkloadSummary,
    WorkloadStatus,
    WorkloadWeights,
    analyze_team_workload
)
from src.integrations.github import GitHubUser
from src.integrations.jira import JiraUser, JiraTicket
from src.integrations.calendar import UserAvailability, PTOPeriod


class TestWorkloadAnalyzer:
    """Tests for WorkloadAnalyzer class."""
    
    def test_analyze_member_github_only(self):
        """Test analyzing a member with only GitHub data."""
        analyzer = WorkloadAnalyzer()
        
        github = GitHubUser(
            login="alice",
            open_prs=3,
            pending_reviews=5,
            assigned_issues=4,
            recent_commits=10
        )
        
        member = analyzer.analyze_member("Alice", github=github)
        
        assert member.name == "Alice"
        assert member.github_open_prs == 3
        assert member.github_pending_reviews == 5
        assert member.github_assigned_issues == 4
        assert member.github_recent_commits == 10
        assert member.workload_score > 0
        assert member.workload_percentage > 0
    
    def test_analyze_member_jira_only(self):
        """Test analyzing a member with only Jira data."""
        analyzer = WorkloadAnalyzer()
        
        tickets = [
            JiraTicket(key="PROJ-1", summary="Task 1", status="In Progress", assignee="Bob", story_points=5),
            JiraTicket(key="PROJ-2", summary="Task 2", status="To Do", assignee="Bob", story_points=3),
        ]
        jira = JiraUser(account_id="bob", display_name="Bob", assigned_tickets=tickets)
        
        member = analyzer.analyze_member("Bob", jira=jira)
        
        assert member.name == "Bob"
        assert member.jira_story_points == 8
        assert member.jira_tickets_in_progress == 1
        assert member.workload_score > 0
    
    def test_analyze_member_all_sources(self):
        """Test analyzing with all data sources."""
        analyzer = WorkloadAnalyzer()
        
        github = GitHubUser(login="carol", open_prs=2, pending_reviews=3, assigned_issues=2)
        
        tickets = [
            JiraTicket(key="PROJ-1", summary="Task 1", status="In Progress", assignee="Carol", story_points=5),
        ]
        jira = JiraUser(account_id="carol", display_name="Carol", assigned_tickets=tickets)
        
        calendar = UserAvailability(
            user="carol",
            email="carol@company.com",
            meeting_hours_this_week=15.0
        )
        
        member = analyzer.analyze_member("Carol", github=github, jira=jira, calendar=calendar)
        
        assert member.github_open_prs == 2
        assert member.jira_story_points == 5
        assert member.meeting_hours_this_week == 15.0
        assert member.email == "carol@company.com"
    
    def test_workload_status_healthy(self):
        """Test healthy workload status."""
        member = TeamMemberWorkload(name="Test", workload_percentage=60.0)
        assert member.status == WorkloadStatus.HEALTHY
        assert member.status_emoji == "🟢"
    
    def test_workload_status_at_capacity(self):
        """Test at-capacity workload status."""
        member = TeamMemberWorkload(name="Test", workload_percentage=90.0)
        assert member.status == WorkloadStatus.AT_CAPACITY
        assert member.status_emoji == "🟡"
    
    def test_workload_status_overloaded(self):
        """Test overloaded workload status."""
        member = TeamMemberWorkload(name="Test", workload_percentage=120.0)
        assert member.status == WorkloadStatus.OVERLOADED
        assert member.status_emoji == "🔴"
    
    def test_analyze_team(self):
        """Test analyzing a full team."""
        analyzer = WorkloadAnalyzer()
        
        github_data = [
            GitHubUser(login="alice", open_prs=5, pending_reviews=8, assigned_issues=10),
            GitHubUser(login="bob", open_prs=1, pending_reviews=2, assigned_issues=2),
        ]
        
        summary = analyzer.analyze(github_data=github_data)
        
        assert len(summary.members) == 2
        assert summary.team_size == 2
        # Alice should be more loaded
        assert summary.members[0].name == "alice"
        assert summary.members[0].workload_percentage > summary.members[1].workload_percentage
    
    def test_team_summary_metrics(self):
        """Test team summary metrics."""
        members = [
            TeamMemberWorkload(name="A", workload_percentage=60),
            TeamMemberWorkload(name="B", workload_percentage=80),
            TeamMemberWorkload(name="C", workload_percentage=110),
        ]
        summary = TeamWorkloadSummary(members=members)
        
        assert summary.team_size == 3
        assert summary.healthy_count == 1
        assert summary.at_capacity_count == 1
        assert summary.overloaded_count == 1
        assert summary.average_workload == pytest.approx(83.33, rel=0.01)
    
    def test_identify_overloaded(self):
        """Test identifying overloaded members."""
        analyzer = WorkloadAnalyzer()
        
        members = [
            TeamMemberWorkload(name="A", workload_percentage=60),
            TeamMemberWorkload(name="B", workload_percentage=100),
            TeamMemberWorkload(name="C", workload_percentage=120),
        ]
        summary = TeamWorkloadSummary(members=members)
        
        overloaded = analyzer.identify_overloaded(summary)
        assert len(overloaded) == 2
        assert overloaded[0].name in ["B", "C"]
        
        overloaded_strict = analyzer.identify_overloaded(summary, threshold=110)
        assert len(overloaded_strict) == 1
    
    def test_suggest_rebalancing(self):
        """Test rebalancing suggestions."""
        analyzer = WorkloadAnalyzer()
        
        members = [
            TeamMemberWorkload(name="Overloaded", workload_percentage=130),
            TeamMemberWorkload(name="Available", workload_percentage=50),
        ]
        summary = TeamWorkloadSummary(members=members)
        
        suggestions = analyzer.suggest_rebalancing(summary)
        
        assert len(suggestions) >= 1
        assert suggestions[0]["from"] == "Overloaded"
        assert suggestions[0]["to"] == "Available"
    
    def test_member_to_dict(self):
        """Test member serialization."""
        member = TeamMemberWorkload(
            name="Test",
            email="test@example.com",
            github_open_prs=3,
            jira_story_points=5,
            workload_score=25.0,
            workload_percentage=75.0
        )
        
        data = member.to_dict()
        
        assert data["name"] == "Test"
        assert data["github"]["open_prs"] == 3
        assert data["jira"]["story_points"] == 5
        assert data["workload"]["percentage"] == 75.0
        assert data["workload"]["status"] == "healthy"


class TestWorkloadWeights:
    """Tests for customizable weights."""
    
    def test_custom_weights(self):
        """Test using custom weights."""
        weights = WorkloadWeights(
            github_open_prs=5.0,  # Higher weight for PRs
            github_pending_reviews=1.0,  # Lower weight for reviews
        )
        
        analyzer = WorkloadAnalyzer(weights=weights)
        
        github = GitHubUser(login="test", open_prs=2, pending_reviews=5)
        member = analyzer.analyze_member("Test", github=github)
        
        # With custom weights: 2*5.0 + 5*1.0 = 15
        # vs default: 2*3.0 + 5*2.0 = 16
        assert member.workload_score > 0


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_analyze_team_workload(self):
        """Test the convenience function."""
        github_data = [
            GitHubUser(login="alice", open_prs=3, pending_reviews=4),
        ]
        
        summary = analyze_team_workload(github_data=github_data)
        
        assert isinstance(summary, TeamWorkloadSummary)
        assert len(summary.members) == 1
