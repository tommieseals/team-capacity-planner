"""
Visualizer for Team Capacity Planner

Creates charts, graphs, and reports for team workload data.
"""

import io
from datetime import datetime, date, timedelta
from typing import Optional, Literal
from dataclasses import dataclass

from .analyzer import TeamWorkloadSummary, TeamMemberWorkload, WorkloadStatus
from .predictor import SprintPrediction, RiskLevel


# ASCII art for terminal output
class ASCIICharts:
    """Generate ASCII art charts for terminal/text output."""
    
    @staticmethod
    def horizontal_bar(
        value: float,
        max_value: float = 100,
        width: int = 20,
        filled_char: str = "█",
        empty_char: str = "░"
    ) -> str:
        """Create a horizontal bar chart."""
        if max_value <= 0:
            return empty_char * width
        
        filled = int((value / max_value) * width)
        filled = min(filled, width)
        return filled_char * filled + empty_char * (width - filled)
    
    @staticmethod
    def workload_bar(percentage: float, width: int = 20) -> str:
        """Create a workload bar with color indicators."""
        bar = ASCIICharts.horizontal_bar(percentage, 100, width)
        
        # Add percentage and status
        if percentage >= 100:
            status = "🔴"
        elif percentage >= 80:
            status = "🟡"
        else:
            status = "🟢"
        
        return f"{bar} {percentage:5.1f}% {status}"
    
    @staticmethod
    def burndown_chart(
        total_points: float,
        completed_points: float,
        days_elapsed: int,
        days_remaining: int,
        width: int = 40,
        height: int = 10
    ) -> str:
        """Create ASCII burndown chart."""
        total_days = days_elapsed + days_remaining
        if total_days <= 0:
            return "No sprint data"
        
        lines = []
        lines.append("Sprint Burndown")
        lines.append("═" * width)
        
        remaining = total_points - completed_points
        
        for row in range(height):
            threshold = total_points * (1 - row / height)
            
            # Ideal line point for this row
            ideal_day = int((1 - threshold / total_points) * total_days)
            
            # Actual line point for this row
            if completed_points >= threshold:
                actual_day = days_elapsed
            else:
                actual_day = -1
            
            row_chars = []
            for day in range(total_days + 1):
                col = int(day * (width - 10) / total_days)
                
                if day == ideal_day:
                    row_chars.append("─")
                elif day == actual_day:
                    row_chars.append("●")
                elif day == days_elapsed:
                    row_chars.append("│")
                else:
                    row_chars.append(" ")
            
            # Pad and add label
            row_str = "".join(row_chars[:width - 8])
            points_label = f"{threshold:5.1f}"
            lines.append(f"{points_label} │{row_str}")
        
        # X-axis
        lines.append("      └" + "─" * (width - 7))
        lines.append(f"       Day 1{' ' * (width - 18)}Day {total_days}")
        
        return "\n".join(lines)


class TextReporter:
    """Generate text-based reports."""
    
    @staticmethod
    def team_workload_report(summary: TeamWorkloadSummary) -> str:
        """Generate a text report of team workload."""
        lines = []
        
        # Header
        lines.append("╔" + "═" * 60 + "╗")
        lines.append("║" + "TEAM CAPACITY REPORT".center(60) + "║")
        lines.append("║" + f"Generated: {summary.calculated_at.strftime('%Y-%m-%d %H:%M')}".center(60) + "║")
        lines.append("╠" + "═" * 60 + "╣")
        
        # Summary stats
        lines.append("║ SUMMARY".ljust(61) + "║")
        lines.append("║" + "─" * 60 + "║")
        lines.append(f"║  Team Size: {summary.team_size}".ljust(61) + "║")
        lines.append(f"║  Average Workload: {summary.average_workload:.1f}%".ljust(61) + "║")
        lines.append(f"║  🟢 Healthy: {summary.healthy_count}  🟡 At Capacity: {summary.at_capacity_count}  🔴 Overloaded: {summary.overloaded_count}".ljust(61) + "║")
        lines.append(f"║  Balance: {'✓ Balanced' if summary.is_balanced else '⚠ Unbalanced'}".ljust(61) + "║")
        lines.append("╠" + "═" * 60 + "╣")
        
        # Individual workloads
        lines.append("║ INDIVIDUAL WORKLOADS".ljust(61) + "║")
        lines.append("║" + "─" * 60 + "║")
        
        for member in summary.members:
            name = member.name[:15].ljust(15)
            bar = ASCIICharts.workload_bar(member.workload_percentage, 15)
            lines.append(f"║  {name} {bar}".ljust(61) + "║")
        
        # Footer
        lines.append("╚" + "═" * 60 + "╝")
        
        return "\n".join(lines)
    
    @staticmethod
    def sprint_prediction_report(prediction: SprintPrediction) -> str:
        """Generate a text report of sprint prediction."""
        lines = []
        
        # Header
        lines.append("╔" + "═" * 60 + "╗")
        lines.append("║" + f"SPRINT PREDICTION: {prediction.sprint_name}".center(60) + "║")
        lines.append("╠" + "═" * 60 + "╣")
        
        # Progress
        progress_bar = ASCIICharts.horizontal_bar(
            prediction.completed_points, 
            prediction.total_points, 
            30
        )
        lines.append(f"║  Progress: {progress_bar} {prediction.completion_percentage:.0f}%".ljust(61) + "║")
        lines.append(f"║  Points: {prediction.completed_points:.0f} / {prediction.total_points:.0f}".ljust(61) + "║")
        lines.append(f"║  Days Remaining: {prediction.days_remaining}".ljust(61) + "║")
        lines.append("║" + "─" * 60 + "║")
        
        # Prediction
        prob_emoji = "✓" if prediction.on_track else "⚠"
        lines.append(f"║  {prob_emoji} Completion Probability: {prediction.completion_probability:.0f}%".ljust(61) + "║")
        lines.append(f"║  Risk Level: {prediction.risk_level.value.upper()}".ljust(61) + "║")
        
        # At-risk tickets
        if prediction.at_risk_tickets:
            lines.append("║" + "─" * 60 + "║")
            lines.append("║  AT-RISK TICKETS:".ljust(61) + "║")
            for ticket in prediction.at_risk_tickets[:3]:
                risk_indicator = "🔴" if ticket.risk_level == RiskLevel.CRITICAL else "🟡"
                line = f"║    {risk_indicator} {ticket.ticket_key}: {ticket.ticket_title[:30]}..."
                lines.append(line.ljust(61) + "║")
        
        # Recommendations
        if prediction.recommendations:
            lines.append("║" + "─" * 60 + "║")
            lines.append("║  RECOMMENDATIONS:".ljust(61) + "║")
            for rec in prediction.recommendations:
                lines.append(f"║    • {rec[:50]}".ljust(61) + "║")
        
        lines.append("╚" + "═" * 60 + "╝")
        
        return "\n".join(lines)
    
    @staticmethod
    def pto_conflicts_report(conflicts: list[dict], team_size: int) -> str:
        """Generate a text report of PTO conflicts."""
        lines = []
        
        lines.append("╔" + "═" * 60 + "╗")
        lines.append("║" + "PTO CONFLICT REPORT".center(60) + "║")
        lines.append("╠" + "═" * 60 + "╣")
        
        if not conflicts:
            lines.append("║  ✓ No PTO conflicts detected in upcoming period".ljust(61) + "║")
        else:
            lines.append(f"║  ⚠ {len(conflicts)} potential conflicts found:".ljust(61) + "║")
            lines.append("║" + "─" * 60 + "║")
            
            for conflict in conflicts:
                severity_emoji = "🔴" if conflict["severity"] == "critical" else "🟡"
                date_str = conflict["date"]
                people = ", ".join(conflict["people_out"][:3])
                if len(conflict["people_out"]) > 3:
                    people += f" +{len(conflict['people_out']) - 3} more"
                
                lines.append(f"║  {severity_emoji} {date_str}: {people}".ljust(61) + "║")
                lines.append(f"║     Available: {conflict['available_count']}/{team_size}".ljust(61) + "║")
        
        lines.append("╚" + "═" * 60 + "╝")
        
        return "\n".join(lines)


class SlackFormatter:
    """Format messages for Slack."""
    
    @staticmethod
    def workload_alert(member: TeamMemberWorkload) -> dict:
        """Create Slack alert for overloaded team member."""
        color = "#FF0000" if member.status == WorkloadStatus.OVERLOADED else "#FFA500"
        
        return {
            "attachments": [{
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"⚠️ Workload Alert: {member.name}",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Workload:*\n{member.workload_percentage:.0f}%"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Status:*\n{member.status.value.replace('_', ' ').title()}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Open PRs:*\n{member.github_open_prs}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Pending Reviews:*\n{member.github_pending_reviews}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Story Points:*\n{member.jira_story_points:.0f}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Meeting Hours:*\n{member.meeting_hours_this_week:.1f}h"
                            }
                        ]
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": "Consider redistributing work to team members with capacity."
                            }
                        ]
                    }
                ]
            }]
        }
    
    @staticmethod
    def daily_summary(summary: TeamWorkloadSummary) -> dict:
        """Create Slack daily summary message."""
        # Status indicators
        status_line = f"🟢 {summary.healthy_count} healthy • 🟡 {summary.at_capacity_count} at capacity • 🔴 {summary.overloaded_count} overloaded"
        
        # Build member list
        member_lines = []
        for member in summary.members[:10]:
            emoji = member.status_emoji
            bar = "█" * int(member.workload_percentage / 10) + "░" * (10 - int(member.workload_percentage / 10))
            member_lines.append(f"{emoji} {member.name}: `{bar}` {member.workload_percentage:.0f}%")
        
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": "📊 Daily Team Capacity Report",
                        "emoji": True
                    }
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Team Average:* {summary.average_workload:.0f}%\n{status_line}"
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "\n".join(member_lines)
                    }
                }
            ]
        }
    
    @staticmethod
    def sprint_alert(prediction: SprintPrediction) -> dict:
        """Create Slack alert for sprint at risk."""
        color = {
            RiskLevel.CRITICAL: "#FF0000",
            RiskLevel.HIGH: "#FFA500",
            RiskLevel.MEDIUM: "#FFFF00",
            RiskLevel.LOW: "#00FF00"
        }[prediction.risk_level]
        
        risk_tickets = "\n".join([
            f"• {t.ticket_key}: {t.ticket_title[:40]}..." 
            for t in prediction.at_risk_tickets[:3]
        ])
        
        recommendations = "\n".join([f"• {r}" for r in prediction.recommendations[:3]])
        
        return {
            "attachments": [{
                "color": color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": f"🎯 Sprint Alert: {prediction.sprint_name}",
                            "emoji": True
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {
                                "type": "mrkdwn",
                                "text": f"*Completion Probability:*\n{prediction.completion_probability:.0f}%"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Risk Level:*\n{prediction.risk_level.value.upper()}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Days Remaining:*\n{prediction.days_remaining}"
                            },
                            {
                                "type": "mrkdwn",
                                "text": f"*Progress:*\n{prediction.completed_points:.0f}/{prediction.total_points:.0f} points"
                            }
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*At-Risk Tickets:*\n{risk_tickets}" if risk_tickets else "*No at-risk tickets*"
                        }
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"*Recommendations:*\n{recommendations}" if recommendations else "*Sprint looks good!*"
                        }
                    }
                ]
            }]
        }


class HTMLReporter:
    """Generate HTML reports (for dashboard or email)."""
    
    @staticmethod
    def team_dashboard(summary: TeamWorkloadSummary) -> str:
        """Generate HTML dashboard for team workload."""
        # Generate member cards
        member_cards = ""
        for member in summary.members:
            status_color = {
                WorkloadStatus.HEALTHY: "#22c55e",
                WorkloadStatus.AT_CAPACITY: "#eab308",
                WorkloadStatus.OVERLOADED: "#ef4444"
            }[member.status]
            
            member_cards += f"""
            <div class="member-card">
                <div class="member-name">{member.name}</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {min(member.workload_percentage, 100)}%; background-color: {status_color};"></div>
                </div>
                <div class="workload-value">{member.workload_percentage:.0f}%</div>
                <div class="member-details">
                    <span>PRs: {member.github_open_prs}</span>
                    <span>Reviews: {member.github_pending_reviews}</span>
                    <span>Points: {member.jira_story_points:.0f}</span>
                </div>
            </div>
            """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Team Capacity Dashboard</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
                .dashboard {{ max-width: 1200px; margin: 0 auto; }}
                .header {{ background: #1e293b; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
                .header h1 {{ margin: 0; }}
                .stats {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 20px; }}
                .stat-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
                .stat-value {{ font-size: 32px; font-weight: bold; }}
                .stat-label {{ color: #64748b; font-size: 14px; }}
                .members {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }}
                .member-card {{ background: white; padding: 16px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
                .member-name {{ font-weight: 600; margin-bottom: 8px; }}
                .progress-bar {{ background: #e2e8f0; height: 8px; border-radius: 4px; overflow: hidden; }}
                .progress-fill {{ height: 100%; transition: width 0.3s; }}
                .workload-value {{ font-size: 24px; font-weight: bold; margin: 8px 0; }}
                .member-details {{ color: #64748b; font-size: 12px; display: flex; gap: 12px; }}
            </style>
        </head>
        <body>
            <div class="dashboard">
                <div class="header">
                    <h1>🎯 Team Capacity Dashboard</h1>
                    <p>Updated: {summary.calculated_at.strftime('%Y-%m-%d %H:%M')}</p>
                </div>
                
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-value">{summary.team_size}</div>
                        <div class="stat-label">Team Members</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value">{summary.average_workload:.0f}%</div>
                        <div class="stat-label">Average Workload</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" style="color: #ef4444;">{summary.overloaded_count}</div>
                        <div class="stat-label">Overloaded</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-value" style="color: #22c55e;">{summary.healthy_count}</div>
                        <div class="stat-label">Healthy</div>
                    </div>
                </div>
                
                <div class="members">
                    {member_cards}
                </div>
            </div>
        </body>
        </html>
        """


# Main visualization class
class Visualizer:
    """
    Main visualizer class that supports multiple output formats.
    
    Usage:
        viz = Visualizer()
        
        # Text report
        print(viz.team_report(summary, format="text"))
        
        # Slack message
        slack_payload = viz.team_report(summary, format="slack")
        
        # HTML dashboard
        html = viz.team_report(summary, format="html")
    """
    
    def __init__(self):
        self.text = TextReporter()
        self.slack = SlackFormatter()
        self.html = HTMLReporter()
        self.ascii = ASCIICharts()
    
    def team_report(
        self,
        summary: TeamWorkloadSummary,
        format: Literal["text", "slack", "html"] = "text"
    ):
        """Generate team workload report in specified format."""
        if format == "text":
            return self.text.team_workload_report(summary)
        elif format == "slack":
            return self.slack.daily_summary(summary)
        elif format == "html":
            return self.html.team_dashboard(summary)
        else:
            raise ValueError(f"Unknown format: {format}")
    
    def sprint_report(
        self,
        prediction: SprintPrediction,
        format: Literal["text", "slack"] = "text"
    ):
        """Generate sprint prediction report."""
        if format == "text":
            return self.text.sprint_prediction_report(prediction)
        elif format == "slack":
            return self.slack.sprint_alert(prediction)
        else:
            raise ValueError(f"Unknown format: {format}")
    
    def workload_alert(
        self,
        member: TeamMemberWorkload,
        format: Literal["text", "slack"] = "slack"
    ):
        """Generate workload alert for overloaded member."""
        if format == "slack":
            return self.slack.workload_alert(member)
        else:
            return f"⚠️ ALERT: {member.name} is {member.status.value} at {member.workload_percentage:.0f}%"
