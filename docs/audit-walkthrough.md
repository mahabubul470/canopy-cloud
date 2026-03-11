# Audit Walkthrough

A detailed look at what happens when you run `canopy audit`, how the scoring works, and how to act on the results.

## The audit pipeline

```
canopy audit --provider aws --region us-east-1
       │
       ▼
┌─────────────────┐
│  1. Discover     │  EC2 DescribeInstances → list of Workloads
└────────┬────────┘
         ▼
┌─────────────────┐
│  2. Metrics      │  CloudWatch GetMetricStatistics → 7-day avg CPU
└────────┬────────┘
         ▼
┌─────────────────┐
│  3. Cost         │  AWS Pricing API (or static fallback) → CostSnapshot
└────────┬────────┘
         ▼
┌─────────────────┐
│  4. Carbon       │  Power model × grid intensity → CarbonSnapshot
└────────┬────────┘
         ▼
┌─────────────────┐
│  5. EcoWeight    │  α × norm_cost + β × norm_carbon → score + status
└────────┬────────┘
         ▼
┌─────────────────┐
│  6. Detect       │  Idle / Rightsize / Region-move detectors
└────────┬────────┘
         ▼
┌─────────────────┐
│  7. Report       │  Rich table or JSON/CSV output
└─────────────────┘
```

## Step 1: Discovery

Canopy calls `ec2:DescribeInstances` and builds a `Workload` for each running instance:

- **id** — the EC2 instance ID
- **name** — from the `Name` tag, or the instance ID if untagged
- **region** — the AWS region
- **instance_type** — e.g., `m5.xlarge`
- **vcpus / memory_gb** — from a built-in spec table (25+ instance types)
- **tags** — all EC2 tags

If you pass `--region us-east-1`, only that region is scanned. Without it, Canopy scans the default region configured in your AWS profile.

## Step 2: Metrics

For each instance, Canopy pulls the `CPUUtilization` metric from CloudWatch:

- **Period:** 7 days
- **Statistic:** Average
- **Granularity:** 1 data point (rolling average over the full period)

The result is stored as `avg_cpu_percent` on the Workload. This value drives the idle and right-sizing detectors.

## Step 3: Cost estimation

Canopy estimates cost using a two-tier approach:

1. **AWS Pricing API** — queries `pricing:GetProducts` for the instance type's on-demand Linux hourly rate
2. **Static fallback** — if the API call fails or the instance type isn't found, Canopy uses a built-in table of 25+ common instance types

Monthly cost = hourly rate × 730 hours.

## Step 4: Carbon estimation

The carbon model:

```
power_kw = (vcpus × tdp_per_core × cpu_utilization) + memory_component + gpu_component
hourly_gco2 = power_kw × PUE × grid_intensity_gco2_kwh
monthly_kg_co2 = hourly_gco2 × 730 / 1000
```

Where:
- **TDP per core** — estimated thermal design power per vCPU
- **PUE** — Power Usage Effectiveness (data center overhead), varies by provider
- **Grid intensity** — grams CO₂ per kWh, from Electricity Maps API or static data

### Carbon data sources

- **Electricity Maps API** — real-time grid carbon intensity (requires `ELECTRICITY_MAPS_API_KEY`)
- **Static fallback** — built-in intensity data for 24 AWS regions and 24 GCP regions, sourced from public grid data

## Step 5: EcoWeight scoring

The EcoWeight formula:

```
EcoWeight = α × (hourly_cost / budget_hourly_usd) + β × (hourly_carbon / carbon_hourly_gco2)
```

**Default parameters:**
- α = 0.5, β = 0.5 (equal weight to cost and carbon)
- budget_hourly_usd = $1.00
- carbon_hourly_gco2 = 100 g

**Interpretation:**

| Score | Status | What it means |
|-------|--------|---------------|
| 0.0–0.7 | Excellent | Well within budget on both dimensions |
| 0.7–0.9 | Good | Healthy, some headroom |
| 0.9–1.0 | Warning | Approaching budget limits |
| 1.0–1.2 | Over | Exceeding allocated budget |
| > 1.2 | Critical | Significantly over budget — action needed |

Workloads are ranked by EcoWeight score (highest first) so the most urgent issues appear at the top.

### Tuning the weights

If your organization prioritizes cost over carbon (or vice versa), adjust α and β in `canopy.yaml`:

```yaml
# Cost-focused: 70% cost, 30% carbon
alpha: 0.7
beta: 0.3

# Carbon-focused: 30% cost, 70% carbon
alpha: 0.3
beta: 0.7
```

Adjust the budget parameters to match your team's actual hourly allocations:

```yaml
budget_hourly_usd: 10.0      # $10/hr budget per workload
carbon_hourly_gco2: 500.0    # 500g CO₂/hr per workload
```

## Step 6: Optimization detectors

Three detectors run against each workload:

### Idle detector

- **Trigger:** avg CPU < 2% over 7 days (configurable via `idle_cpu_threshold`)
- **Recommendation:** Terminate the instance
- **Savings:** Full monthly cost + full monthly carbon

Idle detection takes priority — if a workload is idle, Canopy won't also suggest right-sizing it.

### Right-sizing detector

- **Trigger:** avg CPU < 15% over 7 days (configurable via `rightsize_cpu_threshold`)
- **Recommendation:** Downsize to the next smaller instance in the same family
- **Savings:** Cost delta between current and suggested instance × 730 hours; carbon savings proportional to vCPU reduction

Supported downgrade paths:

```
t3.xlarge  → t3.large   → t3.medium  → t3.small → t3.micro
m5.4xlarge → m5.2xlarge → m5.xlarge  → m5.large
c5.4xlarge → c5.2xlarge → c5.xlarge  → c5.large
r5.2xlarge → r5.xlarge  → r5.large
g5.2xlarge → g5.xlarge
```

### Region move detector

- **Trigger:** A same-provider region has 50%+ lower grid carbon intensity
- **Recommendation:** Migrate to the greener region
- **Savings:** Carbon reduction based on the intensity difference (re-estimated with the full power model in the target region)

Region move recommendations are independent — a workload can be flagged for both right-sizing and a region move.

## Step 7: Reading the output

### Table output (default)

```bash
canopy audit --provider aws
```

Produces two Rich tables:

1. **Audit Results** — every workload with cost, carbon, EcoWeight, and status
2. **Optimization Recommendations** — actionable suggestions with per-item savings

Plus a summary line:

```
Total potential savings: $1,234.56/mo | 45.2 kg CO₂/mo (7 recommendations)
```

### JSON output

```bash
canopy audit --provider aws --output json
```

Returns a JSON object with:
- `workloads[]` — array of scored workloads
- `savings_summary` — totals and full recommendation list

### CSV/JSON report export

```bash
canopy report --provider aws --output csv --out report.csv
```

The CSV has two sections (separated by a blank row):
1. Workload scores (id, name, region, cost, carbon, EcoWeight, status)
2. Recommendations (type, reason, current/suggested instance, savings)

## Example: interpreting results

Suppose you see:

| Workload | EcoWeight | Status | Recommendation |
|----------|-----------|--------|----------------|
| api-server | 1.35 | CRITICAL | RIGHTSIZE: m5.2xlarge → m5.xlarge |
| batch-worker | 0.15 | EXCELLENT | REGION_MOVE: us-east-1 → ca-central-1 |
| staging-db | 0.02 | EXCELLENT | IDLE: 0.3% CPU — consider terminating |

**Actions:**
1. **api-server** is critically over budget — right-sizing from m5.2xlarge to m5.xlarge saves both cost and carbon immediately
2. **batch-worker** is cheap but runs in a dirty grid — migrating to ca-central-1 (cleaner grid) cuts carbon with minimal cost impact
3. **staging-db** is essentially idle — terminate it or schedule it to run only during business hours
