# Quick Start Guide

This guide gets you from zero to your first Canopy audit in under five minutes.

## Prerequisites

- **Python 3.11+**
- **AWS credentials** — Canopy needs read access to EC2, CloudWatch, and the Pricing API. Configure via `aws configure` or export `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.
- **(Optional) Electricity Maps API key** — set `ELECTRICITY_MAPS_API_KEY` for real-time carbon intensity data. Without it, Canopy falls back to built-in static data for 48 regions.

### Required AWS permissions

For audit (read-only):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeInstances",
        "ec2:DescribeRegions",
        "cloudwatch:GetMetricStatistics",
        "pricing:GetProducts"
      ],
      "Resource": "*"
    }
  ]
}
```

For `canopy apply` (requires write access):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ec2:TerminateInstances",
        "ec2:StopInstances",
        "ec2:StartInstances",
        "ec2:ModifyInstanceAttribute"
      ],
      "Resource": "*"
    }
  ]
}
```

## Install

```bash
git clone https://github.com/mahabubul470/canopy-cloud.git
cd canopy-cloud
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Verify:

```bash
canopy --version
# canopy v0.3.0
```

## Step 1: Explore region efficiency

Before auditing, see which regions are cleanest:

```bash
canopy regions
```

This shows all 48 AWS + GCP regions ranked by grid carbon intensity, with efficiency tiers:

| Tier | Criteria |
|------|----------|
| Platinum | CFE% ≥ 95% or grid intensity ≤ 20 gCO₂/kWh |
| Gold | CFE% ≥ 75% or grid intensity ≤ 100 gCO₂/kWh |
| Silver | CFE% ≥ 50% or grid intensity ≤ 300 gCO₂/kWh |
| Bronze | Everything else |

Filter by provider:

```bash
canopy regions --provider aws
canopy regions --provider gcp
```

## Step 2: Run your first audit

```bash
canopy audit --provider aws
```

Canopy will:

1. **Discover** all running EC2 instances (across all regions, or a specific one with `--region`)
2. **Fetch metrics** — 7-day rolling average CPU utilization from CloudWatch
3. **Estimate cost** — via the AWS Pricing API, with a static fallback for 25+ common instance types
4. **Estimate carbon** — using a power model (CPU draw + PUE) multiplied by the region's grid intensity
5. **Compute EcoWeight** — a normalized 0–1+ score blending cost and carbon
6. **Detect optimizations** — idle resources, right-sizing opportunities, and greener regions
7. **Display results** — a ranked table of workloads and a list of recommendations with estimated savings

### Audit a single region

```bash
canopy audit --provider aws --region us-east-1
```

### Get JSON output

```bash
canopy audit --provider aws --output json
```

## Step 3: Read the results

The audit produces two tables:

### Audit Results table

Each workload shows:

- **Cost/mo** — estimated monthly cost in USD
- **Carbon/mo** — estimated monthly emissions in kg CO₂
- **EcoWeight** — the combined efficiency score
- **Status** — Excellent (≤ 0.7), Good (≤ 0.9), Warning (≤ 1.0), Over (≤ 1.2), Critical (> 1.2)

### Optimization Recommendations table

Three types of recommendations:

| Type | Trigger | Action |
|------|---------|--------|
| **IDLE** | Avg CPU < 2% over 7 days | Consider terminating the instance |
| **RIGHTSIZE** | Avg CPU < 15% over 7 days | Downsize to a smaller instance in the same family |
| **REGION_MOVE** | A same-provider region is 50%+ cleaner | Migrate the workload to the greener region |

Each recommendation includes estimated monthly savings in both dollars and kg CO₂.

## Step 4: Export a report

For dashboards or compliance:

```bash
# JSON report
canopy report --provider aws --output json --out audit-report.json

# CSV report
canopy report --provider aws --output csv --out audit-report.csv
```

The CSV contains two sections: workload scores and recommendations. Both formats include the full savings summary.

## Step 5: Customize with a config file

Create `canopy.yaml` in your project root:

```yaml
# Weight cost more heavily than carbon
alpha: 0.7
beta: 0.3

# Set budget thresholds
budget_hourly_usd: 5.0
carbon_hourly_gco2: 200.0

# Adjust detection sensitivity
idle_cpu_threshold: 3.0
rightsize_cpu_threshold: 20.0
```

Canopy automatically loads `canopy.yaml` from:
1. The current directory
2. `~/.config/canopy/canopy.yaml`

Or pass it explicitly:

```bash
canopy audit --config canopy.yaml
```

## Step 6: Preview and apply optimizations

Once you've reviewed the audit results, you can act on them:

```bash
# Dry run — see what would happen without changing anything
canopy apply --provider aws --dry-run

# Apply with interactive CLI approval (one-by-one)
canopy apply --provider aws

# Skip confirmation (auto-approve all)
canopy apply --provider aws --yes

# Send approval request to Slack instead
canopy apply --provider aws --approval slack

# Create a GitHub issue for approval
canopy apply --provider aws --approval github
```

The apply engine supports three actions:
- **Terminate** idle instances
- **Rightsize** under-utilized instances (stop, modify type, start)
- **Region move** — creates a tracking issue (too destructive to automate)

All actions are recorded in the audit log at `~/.config/canopy/audit-log/`.

## Step 7: Launch the dashboard

If you installed the dashboard extra (`pip install -e ".[dashboard]"`):

```bash
canopy dashboard --port 8080
```

Open `http://localhost:8080` to see:
- Overview cards (workloads, cost, carbon, savings)
- Workload table with EcoWeight scores
- Region carbon intensity chart
- Recent audit log entries

## Step 8: Use MCP servers

If you installed the MCP extra (`pip install -e ".[mcp]"`), Canopy exposes tools that LLM hosts (like Claude) can call:

```bash
# List available servers
canopy mcp list

# Start a server (communicates over stdio)
canopy mcp serve electricity
canopy mcp serve billing-aws
```

## What's next

- **Phase 4** — ML-based CARL scheduling, multi-cloud policy orchestration, and cost anomaly detection.
