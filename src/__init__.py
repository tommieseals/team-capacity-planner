"""
Team Capacity Planner

A tool for visualizing and predicting team workload from GitHub, Jira, and calendars.
"""

__version__ = "1.0.0"

from .analyzer import (
    WorkloadAnalyzer,
    TeamWorkloadSummary,
    TeamMemberWorkload,
    WorkloadStatus,
    WorkloadWeights,
    analyze_team_workload
)

from .predictor import (
    SprintPredictor,
    SprintPrediction,
    RiskLevel,
    VelocityStats,
    predict_sprint_completion
)

from .visualizer import (
    Visualizer,
    TextReporter,
    SlackFormatter,
    HTMLReporter
)

__all__ = [
    # Version
    "__version__",
    
    # Analyzer
    "WorkloadAnalyzer",
    "TeamWorkloadSummary", 
    "TeamMemberWorkload",
    "WorkloadStatus",
    "WorkloadWeights",
    "analyze_team_workload",
    
    # Predictor
    "SprintPredictor",
    "SprintPrediction",
    "RiskLevel",
    "VelocityStats",
    "predict_sprint_completion",
    
    # Visualizer
    "Visualizer",
    "TextReporter",
    "SlackFormatter",
    "HTMLReporter",
]
