# AWS Cost Optimization Guide

A practical, end-to-end reference for identifying waste, enforcing governance,
and building cost-aware infrastructure on AWS.

---

## 1. Zombie Asset Identification

Zombie assets are provisioned resources that are no longer serving any workload
but continue to accrue charges. They are the easiest category of cost to
eliminate because the fix is deletion, not architecture.

### Common zombie asset types

| Resource | Idle condition | Approx. cost |
|---|---|---|
| EBS volume | `status = available` (not attached) | $0.10/GB/month (gp2) |
| Elastic IP | No `AssociationId` (not attached to an instance) | $3.65/month |
| EC2 instance | t3.large+ with no `Name` or `CostCenter` tag | $60+/month |
| NAT Gateway | Zero bytes processed for 72+ hours | $32/month + data |
| Load balancer | Zero active targets for 7+ days | $16/month |
| RDS snapshot | Older than the retention policy | $0.095/GB/month |

### Finding zombies with scripts/garbage_collect.py

The script scans for the three most common zombie types: unattached EBS
volumes, unassociated Elastic IPs, and idle large EC2 instances.

**Dry run (safe, default):**

```bash
python scripts/garbage_collect.py --region eu-west-1
```

**Delete mode (actually removes resources):**

```bash
python scripts/garbage_collect.py --region eu-west-1 --delete
```

The script prints a summary report at the end showing total estimated
monthly savings across all resource types found.

### Finding zombies with AWS Trusted Advisor

AWS Trusted Advisor > Cost Optimization tab surfaces:

- Idle EC2 instances (CPU < 10% and network < 5 MB for 14 days)
- Unassociated Elastic IPs
- Underutilised EBS volumes
- Idle load balancers
- Reserved instance utilisation below 80%

Trusted Advisor updates daily and requires Business or Enterprise Support for
the full Cost Optimization checks.

### Automating zombie cleanup

Schedule `garbage_collect.py` via AWS Lambda + EventBridge to run weekly in
dry-run mode with results piped to SNS, and monthly in delete mode after a
manual approval step.

```
EventBridge (weekly) → Lambda (dry-run) → SNS → email review
EventBridge (monthly) → Lambda (--delete) → SNS → confirmation
```

---

## 2. Tagging Governance

Tags are the foundation of cost attribution. Without consistent tags you
cannot answer "how much did the staging environment cost this month?" or
"which team owns this resource?"

### Minimum required tag set

| Tag key | Example value | Purpose |
|---|---|---|
| `Name` | `api-server-prod` | Human-readable identity |
| `CostCenter` | `engineering` | Billing attribution |
| `Environment` | `production` | Lifecycle management |
| `Owner` | `platform-team` | Contact for untagged alerts |

### Enforcing tags with AWS Config

The `infrastructure/terraform/config.tf` provisions two `REQUIRED_TAGS` rules:

- `require-costcenter-tag-ec2` — flags any EC2 instance missing `CostCenter`
- `require-costcenter-tag-s3` — flags any S3 bucket missing `CostCenter`

Resources that fail these rules appear as **Noncompliant** in the AWS Config
console. Pair this with an EventBridge rule that publishes Config compliance
changes to SNS so the team gets notified within minutes of a violation.

### Scoping the Config recorder

Recording every resource type in every region is expensive ($0.003 per
configuration item). Scope the recorder to the resource types you actually
govern:

```hcl
recording_group {
  all_supported = false
  resource_types = [
    "AWS::EC2::Instance",
    "AWS::EC2::Volume",
    "AWS::EC2::EIP",
    "AWS::S3::Bucket",
    "AWS::RDS::DBInstance",
    "AWS::IAM::User",
    "AWS::IAM::Role",
  ]
}
```

### Enforcing tags at creation with IAM

Add an IAM policy condition that denies `ec2:RunInstances` unless the request
includes the required tags:

```json
{
  "Effect": "Deny",
  "Action": "ec2:RunInstances",
  "Resource": "arn:aws:ec2:*:*:instance/*",
  "Condition": {
    "Null": {
      "aws:RequestTag/CostCenter": "true"
    }
  }
}
```

This stops the resource from being created at all rather than flagging it after
the fact.

---

## 3. Budget Controls

Budgets are your early-warning system. Set them low enough that a spike is
caught before the end of the billing cycle.

### Alert stages

The `infrastructure/terraform/budget.tf` sets three alert stages on a $50
monthly budget:

| Threshold | Type | Signal |
|---|---|---|
| 50% ($25) | Forecasted | Early warning — investigate unusual spend |
| 80% ($40) | Forecasted | Action required — identify the driver |
| 100% ($50) | Actual | Budget breached — escalate immediately |

Forecasted alerts fire before you hit the threshold based on the current spend
rate. Actual alerts fire when real charges cross the limit.

### Adding a team alert

```hcl
notification {
  comparison_operator       = "GREATER_THAN"
  threshold                 = 80
  threshold_type            = "PERCENTAGE"
  notification_type         = "FORECASTED"
  subscriber_sns_topic_arns = [aws_sns_topic.cost_alerts.arn]
}
```

Add additional `notification` blocks to the same `aws_budgets_budget` resource
for each threshold.

### Per-service budgets

Set a separate budget for high-variance services (EC2, data transfer) in
addition to the overall account budget:

```hcl
resource "aws_budgets_budget" "ec2" {
  name         = "ec2-monthly"
  budget_type  = "COST"
  limit_amount = "30"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "Service"
    values = ["Amazon Elastic Compute Cloud - Compute"]
  }
  ...
}
```

---

## 4. Spot Instance Optimization

Spot instances offer up to 90% savings over On-Demand for interruption-tolerant
workloads. The key to reliable Spot usage is diversification across instance
types and Availability Zones.

### Mixed Instances Policy (the `asg.tf` approach)

```
On-Demand base: 1 instance   ← always-on minimum capacity
Spot share:     75%           ← cost savings
On-Demand share: 25%          ← buffer against Spot interruptions
Allocation strategy: capacity-optimized ← lowest interruption risk
```

`capacity-optimized` instructs AWS to launch Spot instances from the pool with
the most available capacity, reducing interruption frequency.

### Instance type diversification

Never rely on a single instance type for Spot. If the `t3.micro` pool is
exhausted, the ASG has nowhere to launch and scaling events fail. The ASG in
this project overrides two types (`t3.micro`, `t3.small`). In production, use
5+ types across at least two size-equivalent families:

```hcl
override { instance_type = "t3.micro" }
override { instance_type = "t3a.micro" }
override { instance_type = "t2.micro"  }
```

### Handling interruptions

When AWS reclaims a Spot instance it sends a two-minute interruption notice via
the EC2 metadata endpoint and EventBridge. Wire up a handler:

1. EventBridge rule: `source = ["aws.ec2"]`, `detail-type = ["EC2 Spot Instance Interruption Warning"]`
2. Target: Lambda that drains the instance from the load balancer target group
3. The ASG replaces the terminated instance automatically

### Workloads suited to Spot

| Suitable | Not suitable |
|---|---|
| Stateless web/API servers (behind ALB) | Databases with persistent state |
| Batch jobs and data pipelines | Active leader nodes (Kafka, ZooKeeper) |
| CI/CD build runners | Sessions requiring sticky connections |
| Development and testing environments | Single-instance deployments with no redundancy |

---

## 5. Right-Sizing Recommendations

Right-sizing reduces waste without deleting anything. The goal is to match
instance size to actual workload requirements.

### AWS Compute Optimizer

Compute Optimizer analyses CloudWatch CPU, memory (requires CloudWatch agent),
and network metrics over a 14-day lookback and produces recommendations with
projected savings.

Enable it organisation-wide:

```bash
aws compute-optimizer update-enrollment-status \
  --status Active \
  --include-member-accounts
```

Recommendations are available in the console at
**AWS Compute Optimizer > EC2 instances**.

### Identifying over-provisioned instances

An instance is a right-sizing candidate when:

- CPU utilisation < 20% average over 14 days
- Memory utilisation < 40% average (requires CloudWatch agent)
- Network < 5 MB/s sustained

Use the AWS CLI to list CloudWatch metrics quickly:

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value=i-0abc123 \
  --start-time $(date -u -d '14 days ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Average
```

### Instance size ladder

When stepping down, move one size at a time and monitor for 48 hours before
stepping down again:

```
t3.2xlarge → t3.xlarge → t3.large → t3.medium → t3.small → t3.micro
```

### EBS volume right-sizing

1. Check `VolumeReadOps` and `VolumeWriteOps` CloudWatch metrics.
2. Volumes with zero I/O for 30+ days are candidates for snapshot + deletion.
3. Migrate gp2 volumes to gp3 for a 20% price reduction with better baseline
   performance (`aws ec2 modify-volume --volume-type gp3 --volume-id vol-xxx`).

### Storage class optimisation

- **S3 Intelligent-Tiering**: automatically moves objects between frequent and
  infrequent access tiers. Zero retrieval fees. Apply to buckets where access
  patterns are unknown or variable.
- **EBS snapshots**: set a lifecycle policy to delete snapshots older than 90
  days unless tagged `retain = true`.
- **RDS**: enable automated backups with a 7-day retention window; do not keep
  manual snapshots beyond the compliance requirement.

---

## Quick-reference checklist

- [ ] Run `garbage_collect.py --dry-run` weekly; review output before deleting
- [ ] All EC2 instances tagged with `Name`, `CostCenter`, `Environment`, `Owner`
- [ ] AWS Config recording scoped (not `all_supported = true`)
- [ ] Budget alerts set at 50%, 80%, 100%
- [ ] ASG uses Mixed Instances Policy with ≥ 3 instance type overrides
- [ ] Launch templates have `http_tokens = required` (IMDSv2) and `encrypted = true`
- [ ] Compute Optimizer enabled and recommendations reviewed monthly
- [ ] gp2 volumes migrated to gp3
- [ ] S3 Intelligent-Tiering enabled on variable-access buckets
