# Cost Detective

An AWS cost audit project that identifies wasteful resources, implements governance controls, and architects cost-optimized infrastructure.

## Objectives

- Analyze existing spend to identify zombie assets
- Implement active cost controls via Budgets and Alerts
- Architect a cost-aware solution using Spot Instances

## What Was Done

**Analysis and Cleanup:** Created intentionally wasteful resources (unattached EBS volume, unassociated Elastic IP, idle t3.large EC2 instance) then detected them using AWS Trusted Advisor and a custom Python script that automatically garbage collects unattached EBS volumes.

**Governance:** Created an AWS Budget with SNS email alerts triggered at 80% of a $50 monthly limit. Implemented a tagging policy using AWS Config REQUIRED_TAGS rule that flags any EC2 instance missing a CostCenter tag as Noncompliant.

**Optimization:** Created an Auto Scaling Group with a Mixed Instances Policy combining On-Demand base capacity with 75% Spot instances across t3.micro and t3.small instance types, using capacity-optimized Spot allocation strategy.

## Infrastructure (Terraform)

- Wasteful resources for demonstration
- SNS topic and AWS Budget with email alerts
- AWS Config recorder, delivery channel, and tagging rule
- Auto Scaling Group with Mixed Instances Policy and Launch Template

## Scripts

- `scripts/garbage_collect.py` — detects and deletes unattached EBS volumes. Run with `--delete` flag to actually delete, dry run by default.

## Docs

- `docs/cost-optimization-guide.md` — end-to-end guide on AWS cost optimization
- `docs/` — screenshots of all findings and configurations
