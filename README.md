# Canopy

**Budget & Carbon-Aware Infrastructure Architect**

Canopy scans your cloud infrastructure and produces a unified **EcoWeight** score that combines cost and carbon emissions for every workload. It detects idle resources, recommends right-sizing, and suggests region moves to lower your bill and your carbon footprint.

Organizations waste 30–35% of their cloud spend on overprovisioned resources. At the same time, the EU's Corporate Sustainability Reporting Directive (CSRD) is turning carbon accounting into a legal obligation. Canopy treats these as the same problem: **every watt saved reduces both the bill and the emissions.**

Unlike tools that are either cost-aware (Kubecost, Infracost) or carbon-aware (Cloud Carbon Footprint), Canopy optimizes both in a single loop.

Currently supports **AWS** (EC2). GCP and Azure coming in future phases.

## Features

- **EcoWeight scoring** — a single 0–1+ metric that blends cost and carbon, with configurable weights
- **Idle detection** — flags instances with < 2% avg CPU over 7 days
- **Right-sizing** — suggests instance downgrades for under-utilized workloads (< 15% CPU)
- **Region migration** — recommends greener regions when 50%+ carbon reduction is possible
- **Region tiers** — Platinum/Gold/Silver/Bronze classification for 48 AWS + GCP regions
- **Reports** — JSON and CSV export for dashboards and compliance reporting
- **Configuration** — YAML-based budgets, weights, and thresholds

## Installation

### Requirements

- Python 3.11+
- AWS credentials configured (`aws configure` or environment variables)
- (Optional) [Electricity Maps](https://www.electricitymaps.com/) API key for real-time carbon data

### From source

```bash
git clone https://github.com/mahabubul470/canopy-cloud.git
cd canopy-cloud
python -m venv .venv
source .venv/bin/activate  # or: . .venv/bin/activate.fish
pip install -e ".[dev]"
```

### Verify installation

```bash
canopy --version
```

## Quick start

```bash
# List region efficiency tiers
canopy regions

# Audit your AWS infrastructure
canopy audit --provider aws

# Audit a specific region
canopy audit --provider aws --region us-east-1

# Get JSON output
canopy audit --provider aws --output json

# Export a report
canopy report --provider aws --output json --out report.json
canopy report --provider aws --output csv --out report.csv
```

See [docs/quickstart.md](docs/quickstart.md) for a full walkthrough.

## Configuration

Create a `canopy.yaml` in your project root or `~/.config/canopy/canopy.yaml`:

```yaml
# EcoWeight parameters
alpha: 0.6          # Cost weight (0–1)
beta: 0.4           # Carbon weight (0–1)

# Budget allocations
budget_hourly_usd: 2.0
carbon_hourly_gco2: 150.0

# Detection thresholds
idle_cpu_threshold: 2.0       # % — below this is "idle"
rightsize_cpu_threshold: 15.0 # % — below this triggers right-sizing

# Provider
provider: aws
regions: []  # empty = all regions
```

Pass a custom config path:

```bash
canopy audit --config path/to/canopy.yaml
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `canopy --version` | Show version |
| `canopy regions` | List region efficiency tiers |
| `canopy audit` | Scan infrastructure, compute EcoWeight scores, show recommendations |
| `canopy report` | Export audit results as JSON or CSV |
| `canopy plan` | *(Phase 2)* Preview cost/carbon impact of IaC changes |
| `canopy apply` | *(Phase 3)* Apply recommended optimizations |

### `canopy audit`

```
Options:
  --provider TEXT  Cloud provider (aws, gcp)     [default: aws]
  --region TEXT    Filter by region
  --output TEXT    Output format (table, json)    [default: table]
  --config TEXT    Path to canopy.yaml config file
```

### `canopy report`

```
Options:
  --provider TEXT  Cloud provider (aws, gcp)     [default: aws]
  --region TEXT    Filter by region
  --output TEXT    Output format (json, csv)      [default: json]
  --out TEXT       Output file path
  --config TEXT    Path to canopy.yaml config file
```

### `canopy regions`

```
Options:
  --provider TEXT  Cloud provider (aws, gcp, all) [default: all]
```

## How EcoWeight works

EcoWeight is a normalized score:

```
EcoWeight = α × (hourly_cost / budget_hourly_usd) + β × (hourly_carbon / carbon_hourly_gco2)
```

| Score | Status | Meaning |
|-------|--------|---------|
| ≤ 0.7 | Excellent | Well under budget |
| ≤ 0.9 | Good | Within budget |
| ≤ 1.0 | Warning | Approaching budget |
| ≤ 1.2 | Over | Over budget |
| > 1.2 | Critical | Significantly over budget |

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint and format
ruff check .
ruff format .

# Type checking
mypy canopy
```

## Documentation

- [Quick Start Guide](docs/quickstart.md)
- [Audit Walkthrough](docs/audit-walkthrough.md)

## License

Apache 2.0
