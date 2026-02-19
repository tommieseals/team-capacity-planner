# Workload Metrics Documentation

This document explains how Team Capacity Planner calculates workload scores and makes predictions.

## Workload Scoring

### Overview

Each team member receives a **workload score** calculated from multiple data sources:
- GitHub (PRs, reviews, issues)
- Jira (story points, ticket status)
- Calendar (meeting hours)

The score is normalized to a percentage where **100% = fully utilized**.

### Scoring Formula

```
Workload Score = Σ (metric × weight) / max_score × 100
```

### Default Weights

| Metric | Weight | Rationale |
|--------|--------|-----------|
| **GitHub** | | |
| Open PRs authored | 3.0 | Authored PRs require attention (responding to reviews, fixing issues) |
| Pending reviews | 2.0 | Reviews are time-boxed but important |
| Assigned issues | 2.0 | Issues represent committed work |
| Recent commits | 0.5 | Commits indicate activity but not burden |
| **Jira** | | |
| Story points | 1.0 | Direct measure of sprint commitment |
| In-progress tickets | 2.0 | Active work requiring focus |
| Blocked tickets | 3.0 | Blocked items are stressful and need attention |
| **Calendar** | | |
| Meeting hours | 0.5 | Meetings reduce available coding time |

### Normalization Factors

What constitutes 100% capacity:

| Metric | Max Value | Notes |
|--------|-----------|-------|
| Open PRs | 5 | More than 5 PRs = overloaded |
| Pending reviews | 8 | 8+ reviews = review bottleneck |
| Assigned issues | 10 | Reasonable issue load |
| Story points | 13 | Standard sprint commitment |
| Meeting hours | 20 | Half the week in meetings |

### Status Thresholds

| Status | Percentage | Indicator |
|--------|-----------|-----------|
| 🟢 Healthy | 0-80% | Sustainable workload |
| 🟡 At Capacity | 80-100% | Near limit, watch closely |
| 🔴 Overloaded | 100%+ | Needs immediate attention |

## Sprint Predictions

### Methodology

Sprint completion probability uses:
1. **Historical velocity** - Average points completed per sprint
2. **Current progress** - Points done vs. remaining
3. **Time remaining** - Days left in sprint
4. **Ticket analysis** - Individual ticket risk factors

### Prediction Formula

```
Predicted Completion = current_done + (daily_velocity × days_remaining)

Probability = f(remaining_points, expected_velocity, historical_variance)
```

### Ticket Risk Assessment

Each incomplete ticket is scored for risk:

| Factor | Risk Score | Trigger |
|--------|-----------|---------|
| Not started, >50% sprint elapsed | +40 | Todo status after midpoint |
| Not started, >75% sprint elapsed | +20 | Additional risk near end |
| Large ticket (5+ points), <3 days left | +30 | Big tickets need time |
| Large ticket, <5 days left | +15 | Warning level |
| Ticket is blocked | +50 | Blockers are critical |
| No assignee | +20 | Unassigned = risky |

**Risk Levels:**
- 🟢 Low: 0-40
- 🟡 Medium: 40-60
- 🟠 High: 60-80
- 🔴 Critical: 80-100

### Velocity Statistics

We track:
- **Average velocity**: Mean points completed per sprint
- **Median velocity**: Middle value (less affected by outliers)
- **Standard deviation**: Consistency measure
- **Trend**: Improving, stable, or declining

## What-If Scenarios

### Remove Person

Simulates someone going on PTO:
1. Identifies their assigned tickets
2. Marks unfinished tickets as "blocked" (no instant reassignment)
3. Recalculates sprint prediction
4. Shows impact on completion probability

### Add Scope

Simulates adding work mid-sprint:
1. Adds new story points to sprint total
2. Recalculates prediction
3. Shows probability change

## PTO Conflict Detection

### Algorithm

1. Collect all PTO events from calendars
2. For each workday in the analysis period:
   - Count who's available
   - Flag days below minimum coverage
3. Severity levels:
   - **Critical**: 0 people available
   - **Warning**: Below minimum (configurable)

### Coverage Calculation

```python
available = team_size - len(people_on_pto)
is_conflict = available < min_coverage
```

Default minimum coverage: 2 people

## Customization

### Adjusting Weights

Edit `config/config.yaml`:

```yaml
weights:
  github_open_prs: 3.0  # Increase if PRs are taking too long
  github_pending_reviews: 4.0  # Increase if reviews are bottleneck
  jira_story_points: 2.0  # Increase if story points are accurate
```

### Per-Team Settings

Different teams can have different thresholds:

```yaml
teams:
  platform:
    thresholds:
      overload: 120  # Platform team can handle more
  frontend:
    thresholds:
      overload: 80  # Frontend team has more meetings
```

## Limitations

1. **Qualitative factors not captured**: Complexity, context switching, emotional toll
2. **Historical data dependency**: Predictions improve with more history
3. **Username matching**: Requires consistent usernames across systems
4. **Meeting quality**: All meetings weighted equally
5. **Individual variation**: One person's 100% might be another's 80%

## Best Practices

1. **Calibrate weights** for your team's reality
2. **Review predictions** weekly and adjust
3. **Don't treat scores as absolute** - use for trends and comparison
4. **Combine with 1:1s** - numbers don't capture everything
5. **Update minimum coverage** based on team needs
