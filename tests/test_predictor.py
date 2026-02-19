"""
Tests for the sprint predictor.
"""

import pytest
from datetime import datetime, timedelta

from src.predictor import (
    SprintPredictor,
    SprintPrediction,
    RiskLevel,
    VelocityStats,
    TicketRisk,
    predict_sprint_completion
)
from src.integrations.jira import Sprint, JiraTicket


class TestVelocityStats:
    """Tests for velocity statistics calculation."""
    
    def test_calculate_basic_stats(self):
        """Test basic velocity statistics."""
        predictor = SprintPredictor()
        
        history = [
            {"completed_points": 20},
            {"completed_points": 25},
            {"completed_points": 22},
            {"completed_points": 28},
            {"completed_points": 25},
        ]
        
        stats = predictor.calculate_velocity_stats(history)
        
        assert stats.average == 24.0
        assert stats.median == 25.0
        assert stats.min == 20
        assert stats.max == 28
        assert stats.sprints_analyzed == 5
        assert stats.std_dev > 0
    
    def test_empty_history(self):
        """Test with no history."""
        predictor = SprintPredictor()
        stats = predictor.calculate_velocity_stats([])
        
        assert stats.average == 0
        assert stats.median == 0
        assert stats.sprints_analyzed == 0
    
    def test_trend_improving(self):
        """Test improving velocity trend."""
        predictor = SprintPredictor()
        
        # First half lower than second half
        history = [
            {"completed_points": 10},
            {"completed_points": 12},
            {"completed_points": 20},
            {"completed_points": 25},
        ]
        
        stats = predictor.calculate_velocity_stats(history)
        assert stats.trend == "improving"
    
    def test_trend_declining(self):
        """Test declining velocity trend."""
        predictor = SprintPredictor()
        
        # First half higher than second half
        history = [
            {"completed_points": 25},
            {"completed_points": 22},
            {"completed_points": 12},
            {"completed_points": 10},
        ]
        
        stats = predictor.calculate_velocity_stats(history)
        assert stats.trend == "declining"


class TestTicketRiskAssessment:
    """Tests for ticket risk assessment."""
    
    def test_not_started_late(self):
        """Test risk for not-started ticket late in sprint."""
        predictor = SprintPredictor()
        
        ticket = JiraTicket(
            key="PROJ-1",
            summary="Late starter",
            status="To Do",
            assignee="Alice",
            story_points=3
        )
        
        risk = predictor.assess_ticket_risk(ticket, days_remaining=2, sprint_progress=0.8)
        
        assert risk.risk_score >= 40  # Should have significant risk
        assert "Not started" in " ".join(risk.risk_factors)
    
    def test_blocked_ticket(self):
        """Test risk for blocked ticket."""
        predictor = SprintPredictor()
        
        ticket = JiraTicket(
            key="PROJ-1",
            summary="Blocked task",
            status="In Progress",
            assignee="Bob",
            story_points=5,
            labels=["blocked"]
        )
        
        risk = predictor.assess_ticket_risk(ticket, days_remaining=5, sprint_progress=0.5)
        
        assert risk.risk_score >= 50
        assert "blocked" in " ".join(risk.risk_factors).lower()
    
    def test_large_ticket_late(self):
        """Test risk for large ticket with little time."""
        predictor = SprintPredictor()
        
        ticket = JiraTicket(
            key="PROJ-1",
            summary="Big feature",
            status="In Progress",
            assignee="Carol",
            story_points=8
        )
        
        risk = predictor.assess_ticket_risk(ticket, days_remaining=2, sprint_progress=0.8)
        
        assert risk.risk_score >= 30
        assert "Large ticket" in " ".join(risk.risk_factors)
    
    def test_unassigned_ticket(self):
        """Test risk for unassigned ticket."""
        predictor = SprintPredictor()
        
        ticket = JiraTicket(
            key="PROJ-1",
            summary="Orphan task",
            status="To Do",
            assignee=None,
            story_points=3
        )
        
        risk = predictor.assess_ticket_risk(ticket, days_remaining=5, sprint_progress=0.5)
        
        assert risk.risk_score >= 20
        assert "No assignee" in risk.risk_factors


class TestSprintPrediction:
    """Tests for sprint predictions."""
    
    def test_predict_healthy_sprint(self):
        """Test prediction for a sprint on track."""
        predictor = SprintPredictor()
        
        sprint = Sprint(
            id=1,
            name="Sprint 1",
            state="active",
            start_date=datetime.now() - timedelta(days=7),
            end_date=datetime.now() + timedelta(days=3)
        )
        
        tickets = [
            JiraTicket(key="P-1", summary="Done 1", status="Done", assignee="A", story_points=5),
            JiraTicket(key="P-2", summary="Done 2", status="Done", assignee="B", story_points=5),
            JiraTicket(key="P-3", summary="WIP", status="In Progress", assignee="A", story_points=3),
            JiraTicket(key="P-4", summary="Todo", status="To Do", assignee="B", story_points=2),
        ]
        
        velocity = [
            {"completed_points": 15},
            {"completed_points": 14},
            {"completed_points": 16},
        ]
        
        prediction = predictor.predict(sprint, tickets, velocity)
        
        assert prediction.total_points == 15
        assert prediction.completed_points == 10
        assert prediction.remaining_points == 5
        assert prediction.completion_probability > 0
        assert prediction.risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]
    
    def test_predict_risky_sprint(self):
        """Test prediction for sprint at risk."""
        predictor = SprintPredictor()
        
        sprint = Sprint(
            id=1,
            name="Sprint 1",
            state="active",
            start_date=datetime.now() - timedelta(days=9),
            end_date=datetime.now() + timedelta(days=1)  # Only 1 day left
        )
        
        # Lots of work not done
        tickets = [
            JiraTicket(key="P-1", summary="Done", status="Done", assignee="A", story_points=5),
            JiraTicket(key="P-2", summary="Not done", status="To Do", assignee="B", story_points=8),
            JiraTicket(key="P-3", summary="Not done", status="To Do", assignee="A", story_points=8),
            JiraTicket(key="P-4", summary="Blocked", status="In Progress", assignee="B", story_points=5, labels=["blocked"]),
        ]
        
        prediction = predictor.predict(sprint, tickets, [])
        
        assert prediction.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
        assert len(prediction.at_risk_tickets) > 0
        assert len(prediction.recommendations) > 0
    
    def test_prediction_to_dict(self):
        """Test prediction serialization."""
        prediction = SprintPrediction(
            sprint_name="Test Sprint",
            sprint_id=1,
            total_points=20,
            completed_points=10,
            remaining_points=10,
            days_remaining=5,
            completion_probability=75.0,
            risk_level=RiskLevel.MEDIUM
        )
        
        data = prediction.to_dict()
        
        assert data["sprint"]["name"] == "Test Sprint"
        assert data["points"]["total"] == 20
        assert data["prediction"]["completion_probability"] == 75.0
        assert data["risk"]["level"] == "medium"


class TestWhatIfScenarios:
    """Tests for what-if scenario analysis."""
    
    def test_what_if_remove_person(self):
        """Test removing a person from sprint."""
        predictor = SprintPredictor()
        
        sprint = Sprint(
            id=1,
            name="Sprint 1",
            state="active",
            start_date=datetime.now() - timedelta(days=5),
            end_date=datetime.now() + timedelta(days=5)
        )
        
        tickets = [
            JiraTicket(key="P-1", summary="Done", status="Done", assignee="Alice", story_points=5),
            JiraTicket(key="P-2", summary="WIP", status="In Progress", assignee="Alice", story_points=5),
            JiraTicket(key="P-3", summary="WIP", status="In Progress", assignee="Bob", story_points=5),
        ]
        
        original = predictor.predict(sprint, tickets, [])
        scenario = predictor.what_if_remove_person(original, "Alice", tickets, sprint, [])
        
        assert "Alice" in scenario.scenario_name
        assert scenario.probability_change <= 0  # Should be worse or same
        assert "Alice" in scenario.impact_description
    
    def test_what_if_add_scope(self):
        """Test adding scope to sprint."""
        predictor = SprintPredictor()
        
        sprint = Sprint(
            id=1,
            name="Sprint 1",
            state="active",
            start_date=datetime.now() - timedelta(days=5),
            end_date=datetime.now() + timedelta(days=5)
        )
        
        tickets = [
            JiraTicket(key="P-1", summary="Task", status="In Progress", assignee="Alice", story_points=5),
        ]
        
        original = predictor.predict(sprint, tickets, [])
        scenario = predictor.what_if_add_scope(original, 10, tickets, sprint, [])
        
        assert "10" in scenario.scenario_name
        assert scenario.modified_prediction.total_points == 15
        assert scenario.probability_change < 0  # Adding scope = worse


class TestConvenienceFunctions:
    """Tests for convenience functions."""
    
    def test_predict_sprint_completion(self):
        """Test the convenience function."""
        sprint = Sprint(
            id=1,
            name="Test",
            state="active",
            start_date=datetime.now() - timedelta(days=5),
            end_date=datetime.now() + timedelta(days=5)
        )
        
        tickets = [
            JiraTicket(key="P-1", summary="Task", status="Done", assignee="A", story_points=5),
        ]
        
        prediction = predict_sprint_completion(sprint, tickets)
        
        assert isinstance(prediction, SprintPrediction)
        assert prediction.total_points == 5
        assert prediction.completed_points == 5
