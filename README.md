# Cost Detective

An AWS cost-auditing lab that provisions intentionally wasteful resources,
detects them with a Python script and AWS Trusted Advisor, enforces governance
controls with AWS Config and Budgets, and builds a cost-optimized Auto Scaling
Group using Spot instances.

---

## Lab Objectives

### Objective 1 — Identify Zombie Assets

Provision three demonstrably wasteful resources and detect them using AWS
Trusted Advisor and a custom Python script.

**Resources provisioned** (`infrastructure/terraform/wasteful.tf`):
- Unattached EBS volume (50 GB gp2, ~$5/month)
- Unassociated Elastic IP (~$3.65/month)
- Idle t3.large EC2 instance with no `CostCenter` tag (~$60/month)

**Detection script** — `scripts/garbage_collect.py`:

```bash
# Safe dry run — lists resources and estimated savings, deletes nothing
python scripts/garbage_collect.py --region eu-west-1

# Delete mode — actually removes unattached EBS volumes, releases EIPs,
# and stops idle instances
python scripts/garbage_collect.py --region eu-west-1 --delete
```

The script detects:
- Unattached EBS volumes (`status = available`)
- Unassociated Elastic IPs (no `AssociationId`)
- Running t3.large-or-larger instances missing a `Name` or `CostCenter` tag

It prints a summary report at the end with estimated monthly savings per
resource type.

**Screenshots:**

![Trusted Advisor cost findings](docs/Screenshot%202026-05-29%20114037.png)

![EBS volume identified as unattached](docs/Screenshot%202026-05-29%20124723.png)

![Elastic IP identified as unassociated](docs/Screenshot%202026-05-29%20124920.png)

![EC2 console in eu-west-1 listing the running t3.large idle instance alongside two t3.micro instances](docs/screenshots/Screenshot%202026-07-01%20161241.png)

![garbage_collect.py dry run output listing an unattached EBS volume, an unassociated Elastic IP, and an idle t3.large instance with a ~$69.39/mo estimated savings summary](docs/screenshots/Screenshot%202026-07-01%20165901.png)

---

### Objective 2 — Implement Cost Governance

Enforce tagging policy and set up budget alerts using AWS Config and AWS
Budgets.

**Budget** (`infrastructure/terraform/budget.tf`):
- $50/month limit with SNS email alerts at:
  - 50% forecasted — early warning
  - 80% forecasted — action required
  - 100% actual — budget breached

**Tagging rules** (`infrastructure/terraform/config.tf`):
- `require-costcenter-tag-ec2` — flags EC2 instances missing `CostCenter` as
  Noncompliant
- `require-costcenter-tag-s3` — flags S3 buckets missing `CostCenter` as
  Noncompliant
- Config recorder scoped to EC2, EBS, EIP, S3, RDS, and IAM only (not all
  resources) to minimise Config costs

**Screenshots:**

![AWS Budget with staged alerts configured](docs/Screenshot%202026-05-29%20140524.png)

![AWS Config rule showing Noncompliant EC2 instance](docs/Screenshot%202026-05-29%20141305.png)

![AWS Config Rules page showing require-costcenter-tag-ec2 and require-costcenter-tag-s3, each with 1 Noncompliant resource](docs/screenshots/Screenshot%202026-07-01%20165958.png)

![AWS Budget alert detail page showing the three staged thresholds: 50% forecasted ($25), 80% forecasted ($40), and 100% actual ($50), all Not exceeded](docs/screenshots/Screenshot%202026-07-01%20170544.png)

---

### Objective 3 — Architect a Cost-Optimised Solution

Deploy an Auto Scaling Group using a Mixed Instances Policy to achieve Spot
savings while maintaining availability.

**ASG configuration** (`infrastructure/terraform/asg.tf`):
- 1 On-Demand instance as base capacity
- 75% Spot / 25% On-Demand above the base
- `capacity-optimized` Spot allocation strategy (lowest interruption risk)
- Instance type pool: `t3.micro`, `t3.small`
- Launch template with IMDSv2 enforced and encrypted root volume

**Screenshots:**

![Auto Scaling Group with Mixed Instances Policy](docs/Screenshot%202026-05-29%20142523.png)

![Launch template with Spot configuration](docs/Screenshot%202026-05-29%20144404.png)

![Auto Scaling groups list showing cost-detective-asg at 2/2 healthy instances across two Availability Zones](docs/screenshots/Screenshot%202026-07-01%20161313.png)

![cost-detective-asg detail view showing the Mixed Instances Policy: t3.micro/t3.small instance types, 1 On-Demand base instance, and 25% On-Demand / 75% Spot distribution above base](docs/screenshots/Screenshot%202026-07-01%20165734.png)

---

## Infrastructure

All infrastructure is managed with Terraform in `infrastructure/terraform/`.

| File | Description |
|---|---|
| `main.tf` | Provider configuration |
| `variables.tf` | Input variables (region, project name, alert email) |
| `wasteful.tf` | Intentionally wasteful resources for lab demonstration |
| `budget.tf` | SNS topic and AWS Budget with staged alerts |
| `config.tf` | AWS Config recorder, delivery channel, and tagging rules |
| `asg.tf` | Launch template and Auto Scaling Group |

```bash
cd infrastructure/terraform
terraform init
terraform plan
terraform apply
```

> **Warning:** applying this configuration creates real AWS resources that
> incur charges. Run `terraform destroy` when the lab is complete.

---

## Scripts

| Script | Description |
|---|---|
| `scripts/garbage_collect.py` | Detects unattached EBS volumes, unassociated EIPs, and idle large instances. Dry-run by default. |
| `scripts/test_garbage_collect.py` | pytest unit tests using `unittest.mock` |

Run tests:

```bash
pip install pytest boto3
pytest scripts/test_garbage_collect.py -v
```

---

## Docs

- `docs/cost-optimization-guide.md` — practical end-to-end guide covering
  zombie asset identification, tagging governance, budget controls, Spot
  optimisation, and right-sizing

---

## CI

GitHub Actions workflow at `.github/workflows/ci.yml` runs on every push and
pull request:

- `terraform fmt -check` — format check
- `terraform validate` — syntax and consistency check
- `tflint` — Terraform linting
- `flake8` — Python style check
- `pytest` — unit tests

![GitHub Actions code-quality run passing with a green checkmark after fixing tflint warnings](docs/screenshots/Screenshot%202026-07-01%20160454.png)
