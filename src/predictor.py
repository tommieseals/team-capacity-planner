"""
Sprint Completion Predictor

Uses historical data and current progress to predict sprint outcomes.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Optional
from enum import Enum

from .integrations import Sprint, JiraTicket


class RiskLevel(Enum):
    """Sprint risk level."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class VelocityStats:
    """Historical velocity statistics."""
    average: float
    median: float
    std_dev: float
    min: float
    max: float
    trend: str  # "improving", "stable", "declining"
    sprints_analyzed: int
    
    @property
    def confidence_range(self) -> tuple[float, float]:
        """95% confidence interval."""
        margin = 1.96 * self.std_dev
        return (max(0, self.average - margin), self.average + margin)


@dataclass
class TicketRisk:
    """Risk assessment for a single ticket."""
    ticket_key: str
    ticket_title: str
    story_points: float
    status: str
    risk_score: float  # 0-100
    risk_factors: list[str] = field(default_factory=list)
    recommendation: Optional[str] = None
    
    @property
    def risk_level(self) -> RiskLevel:
        if self.risk_score >= 80:
            return RiskLevel.CRITICAL
        elif self.risk_score >= 60:
            return RiskLevel.HIGH
        elif self.risk_score >= 40:
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
    
    def to_dict(self) -> dict:
        return {
            "key": self.ticket_key,
            "title": self.ticket_title,
            "story_points": self.story_points,
            "status": self.status,
            "risk_score": round(self.risk_score, 1),
            "risk_level": self.risk_level.value,
            "risk_factors": self.risk_factors,
            "recommendation": self.recommendation
        }


@dataclass
class SprintPrediction:
    """Sprint completion prediction."""
    sprint_name: str
    sprint_id: int
    predicted_at: datetime = field(default_factory=datetime.now)
    
    # Current state
    total_points: float = 0
    completed_points: float = 0
    in_progress_points: float = 0
    remaining_points: float = 0
    
    days_remaining: int = 0
    days_elapsed: int = 0
    
    # Predictions
    completion_probability: float = 0  # 0-100%
    predicted_completion_points: float = 0
    predicted_remaining_points: float = 0
    
    # Risk assessment
    risk_level: RiskLevel = RiskLevel.LOW
    at_risk_tickets: list[TicketRisk] = field(default_factory=list)
    
    # Recommendations
    recommendations: list[str] = field(default_factory=list)
    
    @property
    def on_track(self) -> bool:
        """Is sprint on track to complete?"""
        return self.completion_probability >= 70
    
    @property
    def completion_percentage(self) -> float:
        """Current completion percentage."""
        if self.total_points == 0:
            return 0
        return (self.completed_points / self.total_points) * 100
    
    def to_dict(self) -> dict:
        return {
            "sprint": {
                "name": self.sprint_name,
                "id": self.sprint_id,
                "days_remaining": self.days_remaining,
                "days_elapsed": self.days_elapsed
            },
            "points": {
                "total": self.total_points,
                "completed": self.completed_points,
                "in_progress": self.in_progress_points,
                "remaining": self.remaining_points
            },
            "prediction": {
                "completion_probability": round(self.completion_probability, 1),
                "predicted_completion": round(self.predicted_completion_points, 1),
                "predicted_remaining": round(self.predicted_remaining_points, 1),
                "on_track": self.on_track
            },
            "risk": {
                "level": self.risk_level.value,
                "at_risk_tickets": [t.to_dict() for t in self.at_risk_tickets]
            },
            "recommendations": self.recommendations,
            "predicted_at": self.predicted_at.isoformat()
        }


@dataclass
class WhatIfScenario:
    """What-if scenario analysis."""
    scenario_name: str
    original_prediction: SprintPrediction
    modified_prediction: SprintPrediction
    impact_description: str
    
    @property
    def probability_change(self) -> float:
        return self.modified_prediction.completion_probability - self.original_prediction.completion_probability
    
    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario_name,
            "impact": self.impact_description,
            "probability_change": round(self.probability_change, 1),
            "original": self.original_prediction.to_dict(),
            "modified": self.modified_prediction.to_dict()
        }


class SprintPredictor:
    """
    Predicts sprint completion using historical velocity and current progress.
    
    Usage:
        predictor = SprintPredictor()
        prediction = predictor.predict(
            sprint=current_sprint,
            tickets=sprint_tickets,
            velocity_history=[...]
        )
    """
    
    def __init__(
        self,
        confidence_threshold: float = 0.8,
        risk_threshold: float = 70.0
    ):
        self.confidence_threshold = confidence_threshold
        self.risk_threshold = risk_threshold
    
    def calculate_velocity_stats(
        self,
        velocity_history: list[dict]
    ) -> VelocityStats:
        """
        Calculate velocity statistics from historical data.
        
        Args:
            velocity_history: List of sprint velocity data with 'completed_points'
        """
        if not velocity_history:
            return VelocityStats(
                average=0, median=0, std_dev=0, min=0, max=0,
                trend="unknown", sprints_analyzed=0
            )
        
        points = [v["completed_points"] for v in velocity_history]
        n = len(points)
        
        # Basic stats
        average = sum(points) / n
        sorted_points = sorted(points)
        median = sorted_points[n // 2] if n % 2 == 1 else (sorted_points[n//2 - 1] + sorted_points[n//2]) / 2
        
        # Standard deviation
        variance = sum((p - average) ** 2 for p in points) / n
        std_dev = math.sqrt(variance)
        
        # Trend (compare first half to second half)
        if n >= 4:
            first_half_avg = sum(points[:n//2]) / (n//2)
            second_half_avg = sum(points[n//2:]) / (n - n//2)
            
            if second_half_avg > first_half_avg * 1.1:
                trend = "improving"
            elif second_half_avg < first_half_avg * 0.9:
                trend = "declining"
            else:
                trend = "stable"
        else:
            trend = "unknown"
        
        return VelocityStats(
            average=average,
            median=median,
            std_dev=std_dev,
            min=min(points),
            max=max(points),
            trend=trend,
            sprints_analyzed=n
        )
    
    def assess_ticket_risk(
        self,
        ticket: JiraTicket,
        days_remaining: int,
        sprint_progress: float
    ) -> TicketRisk:
        """
        Assess risk of a single ticket not completing.
        
        Args:
            ticket: Jira ticket
            days_remaining: Days left in sprint
            sprint_progress: How far through sprint (0-1)
        """
        risk_score = 0.0
        risk_factors = []
        
        # Not started late in sprint
        if ticket.status.lower() in ["to do", "backlog", "open"]:
            if sprint_progress > 0.5:
                risk_score += 40
                risk_factors.append("Not started, sprint >50% complete")
            if sprint_progress > 0.75:
                risk_score += 20
                risk_factors.append("Not started, sprint >75% complete")
        
        # Large ticket late in sprint
        if ticket.story_points and ticket.story_points >= 5:
            if days_remaining < 3:
                risk_score += 30
                risk_factors.append(f"Large ticket ({ticket.story_points} points) with {days_remaining} days left")
            elif days_remaining < 5:
                risk_score += 15
                risk_factors.append(f"Large ticket with limited time")
        
        # Blocked ticket
        if ticket.is_blocked:
            risk_score += 50
            risk_factors.append("Ticket is blocked")
        
        # No assignee
        if not ticket.assignee:
            risk_score += 20
            risk_factors.append("No assignee")
        
        # Generate recommendation
        recommendation = None
        if risk_score >= 60:
            if ticket.is_blocked:
                recommendation = "Unblock immediately or move to next sprint"
            elif not ticket.assignee:
                recommendation = "Assign to team member with capacity"
            elif ticket.status.lower() in ["to do", "backlog"]:
                recommendation = "Consider descoping to next sprint"
            else:
                recommendation = "Monitor closely, may need descoping"
        
        return TicketRisk(
            ticket_key=ticket.key,
            ticket_title=ticket.summary,
            story_points=ticket.story_points or 0,
            status=ticket.status,
            risk_score=min(100, risk_score),
            risk_factors=risk_factors,
            recommendation=recommendation
        )
    
    def predict(
        self,
        sprint: Sprint,
        tickets: list[JiraTicket],
        velocity_history: Optional[list[dict]] = None
    ) -> SprintPrediction:
        """
        Predict sprint completion.
        
        Args:
            sprint: Current sprint
            tickets: Tickets in the sprint
            velocity_history: Historical velocity data
            
        Returns:
            SprintPrediction with completion probability and risks
        """
        # Calculate points
        total_points = sum(t.story_points or 0 for t in tickets)
        completed_points = sum(t.story_points or 0 for t in tickets if t.is_done)
        in_progress_points = sum(t.story_points or 0 for t in tickets if t.is_in_progress)
        remaining_points = total_points - completed_points
        
        # Calculate time
        days_remaining = sprint.days_remaining
        if sprint.start_date and sprint.end_date:
            total_days = (sprint.end_date - sprint.start_date).days
            days_elapsed = total_days - days_remaining
            sprint_progress = days_elapsed / total_days if total_days > 0 else 0
        else:
            days_elapsed = 0
            sprint_progress = 0.5  # Assume midpoint if unknown
        
        # Calculate velocity stats
        velocity_stats = self.calculate_velocity_stats(velocity_history or [])
        
        # Predict completion
        if velocity_stats.sprints_analyzed >= 3:
            # Use historical velocity
            expected_velocity = velocity_stats.average
            points_per_day = expected_velocity / 10  # Assume 10-day sprint
            predicted_completion = completed_points + (points_per_day * days_remaining)
            
            # Calculate probability using normal distribution approximation
            if velocity_stats.std_dev > 0:
                z_score = (remaining_points - (points_per_day * days_remaining)) / velocity_stats.std_dev
                # Simplified probability calculation
                completion_probability = max(0, min(100, 50 - (z_score * 25)))
            else:
                completion_probability = 50
        else:
            # Use linear projection
            if sprint_progress > 0:
                projected_rate = completed_points / sprint_progress
                predicted_completion = projected_rate
                completion_probability = min(100, (predicted_completion / total_points) * 100) if total_points > 0 else 100
            else:
                predicted_completion = total_points
                completion_probability = 50  # Unknown at sprint start
        
        # Assess ticket risks
        at_risk_tickets = []
        for ticket in tickets:
            if not ticket.is_done:
                risk = self.assess_ticket_risk(ticket, days_remaining, sprint_progress)
                if risk.risk_score >= 40:
                    at_risk_tickets.append(risk)
        
        # Sort by risk score
        at_risk_tickets.sort(key=lambda t: t.risk_score, reverse=True)
        
        # Determine overall risk level
        if completion_probability < 50 or any(t.risk_level == RiskLevel.CRITICAL for t in at_risk_tickets):
            risk_level = RiskLevel.CRITICAL
        elif completion_probability < 70 or len([t for t in at_risk_tickets if t.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]]) >= 2:
            risk_level = RiskLevel.HIGH
        elif completion_probability < 85:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
        
        # Generate recommendations
        recommendations = []
        if risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]:
            if len(at_risk_tickets) > 0:
                recommendations.append(f"Review {len(at_risk_tickets)} at-risk tickets for descoping")
            
            blocked = [t for t in at_risk_tickets if "blocked" in " ".join(t.risk_factors).lower()]
            if blocked:
                recommendations.append(f"Unblock {len(blocked)} blocked tickets immediately")
            
            unassigned = [t for t in at_risk_tickets if "No assignee" in t.risk_factors]
            if unassigned:
                recommendations.append(f"Assign {len(unassigned)} unassigned tickets")
        
        if velocity_stats.trend == "declining":
            recommendations.append("Team velocity is declining - investigate root cause")
        
        return SprintPrediction(
            sprint_name=sprint.name,
            sprint_id=sprint.id,
            total_points=total_points,
            completed_points=completed_points,
            in_progress_points=in_progress_points,
            remaining_points=remaining_points,
            days_remaining=days_remaining,
            days_elapsed=days_elapsed,
            completion_probability=completion_probability,
            predicted_completion_points=min(predicted_completion, total_points),
            predicted_remaining_points=max(0, total_points - predicted_completion),
            risk_level=risk_level,
            at_risk_tickets=at_risk_tickets[:5],  # Top 5 risks
            recommendations=recommendations
        )
    
    def what_if_remove_person(
        self,
        original: SprintPrediction,
        person_name: str,
        tickets: list[JiraTicket],
        sprint: Sprint,
        velocity_history: Optional[list[dict]] = None
    ) -> WhatIfScenario:
        """
        Simulate what happens if a person goes on PTO.
        
        Args:
            original: Original prediction
            person_name: Person to remove
            tickets: All sprint tickets
            sprint: Sprint data
            velocity_history: Historical velocity
        """
        # Filter tickets to exclude person's work (assume unassigned tickets become blocked)
        person_tickets = [t for t in tickets if t.assignee and person_name.lower() in t.assignee.lower()]
        
        # Create modified ticket list
        modified_tickets = []
        for ticket in tickets:
            if ticket in person_tickets and not ticket.is_done:
                # Mark as blocked (simulate reassignment challenge)
                modified = JiraTicket(
                    key=ticket.key,
                    summary=ticket.summary,
                    status=ticket.status,
                    assignee=None,
                    story_points=ticket.story_points,
                    labels=ticket.labels + ["blocked"]
                )
                modified_tickets.append(modified)
            else:
                modified_tickets.append(ticket)
        
        # Calculate new prediction
        modified_prediction = self.predict(sprint, modified_tickets, velocity_history)
        
        # Calculate impact
        points_affected = sum(t.story_points or 0 for t in person_tickets if not t.is_done)
        
        impact_description = (
            f"Removing {person_name} affects {len(person_tickets)} tickets "
            f"({points_affected} points). Sprint completion drops from "
            f"{original.completion_probability:.0f}% to {modified_prediction.completion_probability:.0f}%."
        )
        
        if points_affected > 0:
            impact_description += f" Recommend reassigning to team members with capacity."
        
        return WhatIfScenario(
            scenario_name=f"Remove {person_name}",
            original_prediction=original,
            modified_prediction=modified_prediction,
            impact_description=impact_description
        )
    
    def what_if_add_scope(
        self,
        original: SprintPrediction,
        additional_points: float,
        tickets: list[JiraTicket],
        sprint: Sprint,
        velocity_history: Optional[list[dict]] = None
    ) -> WhatIfScenario:
        """
        Simulate adding scope to the sprint.
        """
        # Add a fake ticket with the additional points
        new_ticket = JiraTicket(
            key="SCOPE-NEW",
            summary="Additional scope",
            status="To Do",
            assignee=None,
            story_points=additional_points
        )
        
        modified_tickets = tickets + [new_ticket]
        modified_prediction = self.predict(sprint, modified_tickets, velocity_history)
        
        impact_description = (
            f"Adding {additional_points} points reduces completion probability from "
            f"{original.completion_probability:.0f}% to {modified_prediction.completion_probability:.0f}%."
        )
        
        return WhatIfScenario(
            scenario_name=f"Add {additional_points} points",
            original_prediction=original,
            modified_prediction=modified_prediction,
            impact_description=impact_description
        )


# Convenience function
def predict_sprint_completion(
    sprint: Sprint,
    tickets: list[JiraTicket],
    velocity_history: Optional[list[dict]] = None
) -> SprintPrediction:
    """
    Quick function to predict sprint completion.
    
    Example:
        prediction = predict_sprint_completion(
            sprint=current_sprint,
            tickets=sprint_tickets,
            velocity_history=past_velocities
        )
        
        print(f"Completion probability: {prediction.completion_probability}%")
        print(f"Risk level: {prediction.risk_level.value}")
    """
    predictor = SprintPredictor()
    return predictor.predict(sprint, tickets, velocity_history)
