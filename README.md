# 🎯 Team Capacity Planner

> Visual team workload analyzer with GitHub/Jira integration, PTO tracking, and sprint predictions.

![Python](https://img.shields.io/badge/python-3.9+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)
![License](https://img.shields.io/badge/license-MIT-blue.svg)

## 📊 What It Does

Team Capacity Planner helps engineering managers visualize and predict team workload:

- **🔥 Overload Detection** - See who's drowning in PRs, reviews, and issues
- **🏖️ PTO Conflicts** - Spot coverage gaps before they happen
- **📈 Sprint Predictions** - Will you hit your sprint goals? ML-powered forecasts
- **⚖️ Workload Distribution** - Balance work across your team fairly
- **🔮 What-If Scenarios** - "What if Sarah goes on PTO?" simulation

## 🚀 Quick Start

### Using Docker (Recommended)

```bash
# Clone the repo
git clone https://github.com/tommieseals/team-capacity-planner.git
cd team-capacity-planner

# Configure your integrations
cp config/config.yaml.example config/config.yaml
# Edit config.yaml with your API keys

# Start everything
docker-compose up -d

# Open dashboard
open http://localhost:3000
```

### Manual Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Run the API server
uvicorn src.api:app --reload

# In another terminal, start the frontend
cd frontend && npm install && npm start
```

## 🔌 Integrations

| Service | What We Pull | Setup Guide |
|---------|--------------|-------------|
| **GitHub** | PRs, reviews, issues, commits | [GitHub Setup](docs/github-setup.md) |
| **Jira** | Tickets, sprints, story points | [Jira Setup](docs/jira-setup.md) |
| **Google Calendar** | PTO, meetings, OOO | [Calendar Setup](docs/calendar-setup.md) |
| **Slack** | Send alerts when someone is overloaded | [Slack Setup](docs/slack-setup.md) |

## 📈 Dashboard Preview

```
┌─────────────────────────────────────────────────────────────────┐
│  TEAM CAPACITY DASHBOARD                        Sprint 23      │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  WORKLOAD BY PERSON              SPRINT BURNDOWN               │
│  ═══════════════════             ══════════════════            │
│  Alice   ████████████ 120%  🔴   Ideal ----                    │
│  Bob     ████████░░░░  80%  🟢        ----____                 │
│  Carol   ██████████░░  95%  🟡   Actual --------               │
│  Dave    ████████████ 115%  🔴              --------           │
│  Eve     ██████░░░░░░  60%  🟢                    ----         │
│                                                                 │
│  UPCOMING PTO                    PREDICTION                    │
│  ═══════════════════             ══════════════════            │
│  📅 Carol: Dec 23-27             📊 Sprint Completion: 78%     │
│  📅 Dave: Dec 24-25              ⚠️  Risk: 3 tickets at risk   │
│  ⚠️ Coverage gap: Dec 24                                       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 🎯 Key Features

### 1. Workload Scoring

Each team member gets a workload score based on:

| Factor | Weight | Description |
|--------|--------|-------------|
| Open PRs authored | 3 | PRs they need to shepherd |
| Pending reviews | 2 | Reviews requested from them |
| Assigned issues | 2 | Issues they're responsible for |
| Story points (Jira) | 1 | Current sprint commitments |
| Meeting hours | 0.5 | Time blocked in calendar |

**Score Interpretation:**
- 🟢 0-80: Healthy capacity
- 🟡 80-100: Near capacity
- 🔴 100+: Overloaded!

### 2. Sprint Predictions

Uses historical velocity and current progress to predict:
- Probability of completing all sprint items
- Which tickets are at risk
- Recommended actions (descope, reassign)

### 3. What-If Scenarios

Simulate changes to see impact:
```python
# What if Alice goes on PTO?
scenario = planner.what_if(remove_person="Alice", days=5)
print(scenario.impact)
# Output: "Sprint completion drops from 95% to 72%. 
#          Recommend reassigning PROJ-123, PROJ-456 to Bob"
```

### 4. Slack Alerts

Automated alerts when:
- Someone exceeds 100% capacity
- Sprint is at risk (<70% predicted completion)
- PTO creates coverage gaps
- Workload is unbalanced (>30% variance)

## 📁 Project Structure

```
team-capacity-planner/
├── src/
│   ├── integrations/
│   │   ├── github.py      # GitHub API integration
│   │   ├── jira.py        # Jira API integration
│   │   └── calendar.py    # Google/Outlook calendar
│   ├── analyzer.py        # Workload scoring engine
│   ├── predictor.py       # Sprint completion predictions
│   ├── visualizer.py      # Charts and reports
│   └── api.py             # FastAPI backend
├── frontend/              # React dashboard
├── config/
│   └── config.yaml        # Configuration
├── docs/                  # Documentation
└── tests/                 # Test suite
```

## ⚙️ Configuration

```yaml
# config/config.yaml
github:
  token: ${GITHUB_TOKEN}
  org: your-org
  
jira:
  url: https://yourcompany.atlassian.net
  email: ${JIRA_EMAIL}
  token: ${JIRA_TOKEN}
  project: PROJ

calendar:
  provider: google  # or outlook
  credentials_file: credentials.json

slack:
  webhook_url: ${SLACK_WEBHOOK}
  channel: "#engineering-capacity"

thresholds:
  overload: 100      # Percentage to trigger alert
  at_risk: 80        # Sprint completion below this = risk
  balance_variance: 30  # Max acceptable workload variance
```

## 🤝 Contributing

Contributions welcome! Please read our [Contributing Guide](CONTRIBUTING.md).

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

Built with ❤️ for engineering managers who care about their team's wellbeing.
