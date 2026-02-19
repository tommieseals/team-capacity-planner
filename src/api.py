"""
FastAPI Backend for Team Capacity Planner

Provides REST API for the dashboard and integrations.
"""

import os
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

import yaml
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .integrations import (
    GitHubClient,
    JiraClient,
    CalendarClient,
    get_github_workload,
    get_jira_workload,
    get_team_pto_conflicts
)
from .analyzer import WorkloadAnalyzer, TeamWorkloadSummary, WorkloadWeights
from .predictor import SprintPredictor, SprintPrediction
from .visualizer import Visualizer


# Configuration
class Config:
    """Load configuration from config.yaml and environment."""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        self.config = {}
        
        if os.path.exists(config_path):
            with open(config_path) as f:
                self.config = yaml.safe_load(f) or {}
        
        # Override with environment variables
        self._load_env()
    
    def _load_env(self):
        """Load configuration from environment variables."""
        env_mapping = {
            "GITHUB_TOKEN": ("github", "token"),
            "GITHUB_ORG": ("github", "org"),
            "JIRA_URL": ("jira", "url"),
            "JIRA_EMAIL": ("jira", "email"),
            "JIRA_TOKEN": ("jira", "token"),
            "JIRA_PROJECT": ("jira", "project"),
            "SLACK_WEBHOOK": ("slack", "webhook_url"),
            "CALENDAR_PROVIDER": ("calendar", "provider"),
            "GOOGLE_CALENDAR_TOKEN": ("calendar", "google_token"),
            "OUTLOOK_TOKEN": ("calendar", "outlook_token"),
        }
        
        for env_var, (section, key) in env_mapping.items():
            value = os.getenv(env_var)
            if value:
                if section not in self.config:
                    self.config[section] = {}
                self.config[section][key] = value
    
    def get(self, section: str, key: str, default=None):
        """Get configuration value."""
        return self.config.get(section, {}).get(key, default)
    
    @property
    def github_token(self) -> Optional[str]:
        return self.get("github", "token")
    
    @property
    def github_org(self) -> Optional[str]:
        return self.get("github", "org")
    
    @property
    def github_repos(self) -> list[str]:
        return self.get("github", "repos", [])
    
    @property
    def jira_url(self) -> Optional[str]:
        return self.get("jira", "url")
    
    @property
    def jira_email(self) -> Optional[str]:
        return self.get("jira", "email")
    
    @property
    def jira_token(self) -> Optional[str]:
        return self.get("jira", "token")
    
    @property
    def jira_project(self) -> Optional[str]:
        return self.get("jira", "project")
    
    @property
    def slack_webhook(self) -> Optional[str]:
        return self.get("slack", "webhook_url")
    
    @property
    def team_members(self) -> list[str]:
        return self.get("team", "members", [])
    
    @property
    def thresholds(self) -> dict:
        return self.config.get("thresholds", {
            "overload": 100,
            "at_risk": 80,
            "balance_variance": 30
        })


# Global instances
config = Config()
analyzer = WorkloadAnalyzer()
predictor = SprintPredictor()
visualizer = Visualizer()

# Cached data
_cache = {
    "team_workload": None,
    "sprint_prediction": None,
    "last_update": None
}


# Pydantic models for API
class TeamMember(BaseModel):
    name: str
    email: Optional[str] = None


class WhatIfRequest(BaseModel):
    scenario_type: str  # "remove_person", "add_scope"
    person_name: Optional[str] = None
    additional_points: Optional[float] = None


class AlertSettings(BaseModel):
    overload_threshold: float = 100
    at_risk_threshold: float = 80
    slack_enabled: bool = True


# Lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print("🚀 Team Capacity Planner API starting up...")
    yield
    print("👋 Team Capacity Planner API shutting down...")


# Create FastAPI app
app = FastAPI(
    title="Team Capacity Planner",
    description="API for team workload analysis and sprint predictions",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "integrations": {
            "github": config.github_token is not None,
            "jira": config.jira_token is not None,
            "slack": config.slack_webhook is not None
        }
    }


# Team workload endpoints
@app.get("/api/workload")
async def get_team_workload():
    """Get current team workload summary."""
    try:
        github_data = None
        jira_data = None
        
        # Fetch GitHub data
        if config.github_token and config.github_repos:
            github_client = GitHubClient(
                token=config.github_token,
                org=config.github_org,
                repos=config.github_repos
            )
            github_data = await github_client.get_team_workload(
                members=config.team_members
            )
        
        # Fetch Jira data
        if all([config.jira_url, config.jira_email, config.jira_token]):
            jira_client = JiraClient(
                url=config.jira_url,
                email=config.jira_email,
                token=config.jira_token,
                project=config.jira_project
            )
            jira_data = await jira_client.get_team_workload(
                users=config.team_members
            )
        
        # Analyze workload
        summary = analyzer.analyze(
            github_data=github_data,
            jira_data=jira_data,
            team_members=config.team_members
        )
        
        # Cache result
        _cache["team_workload"] = summary
        _cache["last_update"] = datetime.now()
        
        return summary.to_dict()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workload/{member_name}")
async def get_member_workload(member_name: str):
    """Get workload for a specific team member."""
    # Get cached summary or fetch new
    summary = _cache.get("team_workload")
    
    if not summary:
        # Fetch fresh data
        result = await get_team_workload()
        summary = _cache.get("team_workload")
    
    # Find member
    for member in summary.members:
        if member.name.lower() == member_name.lower():
            return member.to_dict()
    
    raise HTTPException(status_code=404, detail=f"Member {member_name} not found")


@app.get("/api/workload/overloaded")
async def get_overloaded_members(threshold: float = 100):
    """Get team members exceeding workload threshold."""
    summary = _cache.get("team_workload")
    
    if not summary:
        await get_team_workload()
        summary = _cache.get("team_workload")
    
    overloaded = analyzer.identify_overloaded(summary, threshold)
    return {
        "threshold": threshold,
        "count": len(overloaded),
        "members": [m.to_dict() for m in overloaded]
    }


@app.get("/api/workload/suggestions")
async def get_rebalancing_suggestions():
    """Get suggestions for rebalancing team workload."""
    summary = _cache.get("team_workload")
    
    if not summary:
        await get_team_workload()
        summary = _cache.get("team_workload")
    
    suggestions = analyzer.suggest_rebalancing(summary)
    return {
        "is_balanced": summary.is_balanced,
        "variance": round(summary.workload_variance, 1),
        "suggestions": suggestions
    }


# Sprint prediction endpoints
@app.get("/api/sprint/current")
async def get_current_sprint():
    """Get current sprint information and prediction."""
    if not all([config.jira_url, config.jira_email, config.jira_token]):
        raise HTTPException(status_code=400, detail="Jira not configured")
    
    try:
        jira_client = JiraClient(
            url=config.jira_url,
            email=config.jira_email,
            token=config.jira_token,
            project=config.jira_project
        )
        
        # Get active sprint
        sprint = await jira_client.get_active_sprint()
        if not sprint:
            return {"message": "No active sprint found"}
        
        # Get sprint tickets
        tickets = await jira_client.get_sprint_tickets(sprint.id)
        
        # Get velocity history
        velocity = await jira_client.get_velocity_history()
        
        # Predict completion
        prediction = predictor.predict(sprint, tickets, velocity)
        
        # Cache
        _cache["sprint_prediction"] = prediction
        
        return prediction.to_dict()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sprint/burndown")
async def get_sprint_burndown():
    """Get burndown data for current sprint."""
    if not all([config.jira_url, config.jira_email, config.jira_token]):
        raise HTTPException(status_code=400, detail="Jira not configured")
    
    try:
        jira_client = JiraClient(
            url=config.jira_url,
            email=config.jira_email,
            token=config.jira_token,
            project=config.jira_project
        )
        
        sprint = await jira_client.get_active_sprint()
        if not sprint:
            return {"message": "No active sprint found"}
        
        burndown = await jira_client.get_sprint_burndown_data(sprint.id)
        return burndown
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/sprint/velocity")
async def get_velocity_history(num_sprints: int = 5):
    """Get historical velocity data."""
    if not all([config.jira_url, config.jira_email, config.jira_token]):
        raise HTTPException(status_code=400, detail="Jira not configured")
    
    try:
        jira_client = JiraClient(
            url=config.jira_url,
            email=config.jira_email,
            token=config.jira_token,
            project=config.jira_project
        )
        
        velocity = await jira_client.get_velocity_history(num_sprints=num_sprints)
        stats = predictor.calculate_velocity_stats(velocity)
        
        return {
            "history": velocity,
            "stats": {
                "average": round(stats.average, 1),
                "median": stats.median,
                "std_dev": round(stats.std_dev, 1),
                "trend": stats.trend,
                "sprints_analyzed": stats.sprints_analyzed
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# What-if scenarios
@app.post("/api/sprint/what-if")
async def run_what_if_scenario(request: WhatIfRequest):
    """Run what-if scenario analysis."""
    prediction = _cache.get("sprint_prediction")
    
    if not prediction:
        # Fetch current sprint first
        await get_current_sprint()
        prediction = _cache.get("sprint_prediction")
    
    if not prediction:
        raise HTTPException(status_code=400, detail="No sprint prediction available")
    
    try:
        jira_client = JiraClient(
            url=config.jira_url,
            email=config.jira_email,
            token=config.jira_token,
            project=config.jira_project
        )
        
        sprint = await jira_client.get_active_sprint()
        tickets = await jira_client.get_sprint_tickets(sprint.id)
        velocity = await jira_client.get_velocity_history()
        
        if request.scenario_type == "remove_person" and request.person_name:
            scenario = predictor.what_if_remove_person(
                prediction, request.person_name, tickets, sprint, velocity
            )
        elif request.scenario_type == "add_scope" and request.additional_points:
            scenario = predictor.what_if_add_scope(
                prediction, request.additional_points, tickets, sprint, velocity
            )
        else:
            raise HTTPException(status_code=400, detail="Invalid scenario parameters")
        
        return scenario.to_dict()
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# PTO and calendar endpoints
@app.get("/api/pto/conflicts")
async def get_pto_conflicts(days_ahead: int = 30, min_coverage: int = 2):
    """Find PTO coverage conflicts."""
    calendar_provider = config.get("calendar", "provider", "google")
    
    try:
        emails = [f"{name}@company.com" for name in config.team_members]  # Customize as needed
        
        conflicts = await get_team_pto_conflicts(
            provider=calendar_provider,
            emails=emails,
            days_ahead=days_ahead,
            min_coverage=min_coverage
        )
        
        return {
            "days_checked": days_ahead,
            "min_coverage_required": min_coverage,
            "conflicts": conflicts
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Visualization endpoints
@app.get("/api/reports/workload", response_class=HTMLResponse)
async def get_workload_html_report():
    """Get HTML dashboard for team workload."""
    summary = _cache.get("team_workload")
    
    if not summary:
        await get_team_workload()
        summary = _cache.get("team_workload")
    
    return visualizer.team_report(summary, format="html")


@app.get("/api/reports/workload/text")
async def get_workload_text_report():
    """Get text report for team workload."""
    summary = _cache.get("team_workload")
    
    if not summary:
        await get_team_workload()
        summary = _cache.get("team_workload")
    
    return {"report": visualizer.team_report(summary, format="text")}


@app.get("/api/reports/sprint/text")
async def get_sprint_text_report():
    """Get text report for sprint prediction."""
    prediction = _cache.get("sprint_prediction")
    
    if not prediction:
        await get_current_sprint()
        prediction = _cache.get("sprint_prediction")
    
    if not prediction:
        return {"report": "No sprint data available"}
    
    return {"report": visualizer.sprint_report(prediction, format="text")}


# Slack integration
@app.get("/api/slack/workload-summary")
async def get_slack_workload_summary():
    """Get Slack-formatted workload summary."""
    summary = _cache.get("team_workload")
    
    if not summary:
        await get_team_workload()
        summary = _cache.get("team_workload")
    
    return visualizer.team_report(summary, format="slack")


@app.get("/api/slack/sprint-alert")
async def get_slack_sprint_alert():
    """Get Slack-formatted sprint alert."""
    prediction = _cache.get("sprint_prediction")
    
    if not prediction:
        await get_current_sprint()
        prediction = _cache.get("sprint_prediction")
    
    if not prediction:
        raise HTTPException(status_code=400, detail="No sprint data available")
    
    return visualizer.sprint_report(prediction, format="slack")


# Sample data endpoint (for testing)
@app.get("/api/sample-data")
async def get_sample_data():
    """Get sample data for testing the dashboard."""
    from .integrations import GitHubUser, JiraUser, JiraTicket
    
    # Generate sample data
    sample_github = [
        GitHubUser(login="alice", open_prs=3, pending_reviews=5, assigned_issues=4, recent_commits=12),
        GitHubUser(login="bob", open_prs=2, pending_reviews=3, assigned_issues=3, recent_commits=8),
        GitHubUser(login="carol", open_prs=5, pending_reviews=8, assigned_issues=6, recent_commits=15),
        GitHubUser(login="dave", open_prs=1, pending_reviews=2, assigned_issues=2, recent_commits=5),
        GitHubUser(login="eve", open_prs=4, pending_reviews=6, assigned_issues=5, recent_commits=10),
    ]
    
    sample_jira = []
    for user in ["Alice", "Bob", "Carol", "Dave", "Eve"]:
        tickets = [
            JiraTicket(key=f"PROJ-{i}", summary=f"Task {i}", status="In Progress", assignee=user, story_points=3)
            for i in range(1, 4)
        ]
        sample_jira.append(JiraUser(account_id=user.lower(), display_name=user, assigned_tickets=tickets))
    
    summary = analyzer.analyze(
        github_data=sample_github,
        jira_data=sample_jira
    )
    
    return summary.to_dict()


# Run with: uvicorn src.api:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
