# AWS Cost Optimization Guide

## 1. Identify Zombie Assets

Zombie assets are resources that exist but serve no purpose.

Common zombie assets: unattached EBS volumes, unassociated Elastic IPs, idle EC2 instances, unused load balancers and NAT gateways.

Detection tools: AWS Trusted Advisor Cost Optimization tab, AWS Cost Explorer, and custom scripts (see scripts/garbage_collect.py).

Automated cleanup: Run garbage_collect.py on a schedule via AWS Lambda and EventBridge to automatically delete unattached EBS volumes daily.

## 2. Implement Cost Governance

Budgets and alerts: Set monthly budget limits with SNS email alerts at 80% forecasted spend for early warning before bills spiral.

Tagging policy: Enforce a CostCenter tag on all EC2 instances using AWS Config REQUIRED_TAGS rule. Untagged instances are flagged Noncompliant, making cost attribution possible.

Tag everything: Without tags you cannot answer which team owns this resource or how much did project X cost this month.

## 3. Optimize with Spot Instances

Mixed Instances Policy in Auto Scaling Groups: set 1 On-Demand instance as base capacity, remaining capacity 75% Spot and 25% On-Demand, use multiple instance types so AWS has more Spot pools, use capacity-optimized allocation strategy.

Spot instances are up to 90% cheaper than On-Demand. Best for stateless workloads. Do not use for databases or stateful services that cannot tolerate interruption.

## 4. Additional Recommendations

Use Savings Plans or Reserved Instances for predictable baseline workloads. Enable S3 Intelligent Tiering. Set lifecycle policies on EBS snapshots. Use AWS Compute Optimizer to right-size over-provisioned instances. Review and delete unused AMIs monthly.
