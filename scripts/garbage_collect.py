import boto3
from botocore.exceptions import ClientError

LARGE_INSTANCE_SIZES = {
    "large", "xlarge", "2xlarge", "3xlarge", "4xlarge", "6xlarge",
    "8xlarge", "9xlarge", "10xlarge", "12xlarge", "16xlarge", "18xlarge",
    "24xlarge", "32xlarge", "48xlarge", "metal",
}

EBS_PRICE_PER_GB = 0.10       # gp2/gp3 approximate, USD/GB/month
EIP_PRICE_PER_MONTH = 3.65    # ~$0.005/hr * 730 hrs
EC2_LARGE_PRICE_PER_MONTH = 60.74  # t3.large on-demand eu-west-1 approximate


def _is_large_or_larger(instance_type):
    parts = instance_type.split(".")
    return len(parts) >= 2 and parts[-1] in LARGE_INSTANCE_SIZES


def find_unattached_volumes(ec2_client, dry_run=True):
    """Finds and optionally deletes unattached EBS volumes.

    Returns (volumes, deleted_ids, estimated_monthly_savings_usd).
    """
    try:
        response = ec2_client.describe_volumes(
            Filters=[{"Name": "status", "Values": ["available"]}]
        )
    except ClientError as e:
        print(f"[ERROR] describe_volumes failed: {e}")
        return [], [], 0.0

    volumes = response["Volumes"]
    print(f"\nFound {len(volumes)} unattached EBS volume(s):")
    deleted_ids = []
    total_gb = 0

    for vol in volumes:
        vol_id = vol["VolumeId"]
        size = vol["Size"]
        vol_type = vol.get("VolumeType", "gp2")
        name = next(
            (t["Value"] for t in vol.get("Tags", []) if t["Key"] == "Name"),
            "unnamed",
        )
        total_gb += size
        print(f"  - {vol_id} | {size} GB | {vol_type} | {name}")

        if dry_run:
            print(f"    [DRY RUN] Would delete {vol_id}")
        else:
            try:
                ec2_client.delete_volume(VolumeId=vol_id)
                deleted_ids.append(vol_id)
                print(f"    DELETED {vol_id}")
            except ClientError as e:
                print(f"    [ERROR] Could not delete {vol_id}: {e}")

    monthly_savings = round(total_gb * EBS_PRICE_PER_GB, 2)
    return volumes, deleted_ids, monthly_savings


def find_unassociated_eips(ec2_client, dry_run=True):
    """Finds and optionally releases unassociated Elastic IPs.

    Returns (eips, released_ids, estimated_monthly_savings_usd).
    """
    try:
        response = ec2_client.describe_addresses()
    except ClientError as e:
        print(f"[ERROR] describe_addresses failed: {e}")
        return [], [], 0.0

    eips = [a for a in response["Addresses"] if "AssociationId" not in a]
    print(f"\nFound {len(eips)} unassociated Elastic IP(s):")
    released_ids = []

    for addr in eips:
        alloc_id = addr.get("AllocationId", "N/A")
        public_ip = addr.get("PublicIp", "N/A")
        print(f"  - {public_ip} | alloc: {alloc_id}")

        if dry_run:
            print(f"    [DRY RUN] Would release {public_ip}")
        else:
            try:
                ec2_client.release_address(AllocationId=alloc_id)
                released_ids.append(alloc_id)
                print(f"    RELEASED {public_ip}")
            except ClientError as e:
                print(f"    [ERROR] Could not release {public_ip}: {e}")

    monthly_savings = round(len(eips) * EIP_PRICE_PER_MONTH, 2)
    return eips, released_ids, monthly_savings


def find_idle_instances(ec2_client, dry_run=True):
    """Finds t3.large-or-larger instances missing a Name or CostCenter tag.

    Returns (instances, stopped_ids, estimated_monthly_savings_usd).
    """
    try:
        response = ec2_client.describe_instances(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        )
    except ClientError as e:
        print(f"[ERROR] describe_instances failed: {e}")
        return [], [], 0.0

    idle = []
    for reservation in response.get("Reservations", []):
        for instance in reservation["Instances"]:
            if not _is_large_or_larger(instance["InstanceType"]):
                continue
            tags = {t["Key"]: t["Value"] for t in instance.get("Tags", [])}
            if "Name" not in tags or "CostCenter" not in tags:
                idle.append(instance)

    print(f"\nFound {len(idle)} idle large EC2 instance(s) (missing Name or CostCenter tag):")
    stopped_ids = []

    for inst in idle:
        inst_id = inst["InstanceId"]
        itype = inst["InstanceType"]
        tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
        name = tags.get("Name", "unnamed")
        print(f"  - {inst_id} | {itype} | {name}")

        if dry_run:
            print(f"    [DRY RUN] Would stop {inst_id}")
        else:
            try:
                ec2_client.stop_instances(InstanceIds=[inst_id])
                stopped_ids.append(inst_id)
                print(f"    STOPPED {inst_id}")
            except ClientError as e:
                print(f"    [ERROR] Could not stop {inst_id}: {e}")

    monthly_savings = round(len(idle) * EC2_LARGE_PRICE_PER_MONTH, 2)
    return idle, stopped_ids, monthly_savings


def print_summary(volumes_result, eips_result, instances_result):
    volumes, _, vol_savings = volumes_result
    eips, _, eip_savings = eips_result
    instances, _, inst_savings = instances_result
    total_savings = vol_savings + eip_savings + inst_savings

    print("\n" + "=" * 50)
    print("SUMMARY REPORT")
    print("=" * 50)
    print(f"  Unattached EBS volumes : {len(volumes):3d}  (~${vol_savings:.2f}/mo)")
    print(f"  Unassociated EIPs      : {len(eips):3d}  (~${eip_savings:.2f}/mo)")
    print(f"  Idle large instances   : {len(instances):3d}  (~${inst_savings:.2f}/mo)")
    print("-" * 50)
    print(f"  TOTAL potential savings: ~${total_savings:.2f}/mo")
    print("=" * 50)


def run(region="eu-west-1", dry_run=True):
    ec2 = boto3.client("ec2", region_name=region)
    mode = "DRY RUN" if dry_run else "DELETE MODE"
    print(f"Running garbage collector [{mode}] in {region}")

    vol_result = find_unattached_volumes(ec2, dry_run)
    eip_result = find_unassociated_eips(ec2, dry_run)
    inst_result = find_idle_instances(ec2, dry_run)
    print_summary(vol_result, eip_result, inst_result)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Detect and optionally remove wasteful AWS resources."
    )
    parser.add_argument("--delete", action="store_true", help="Actually delete/stop resources")
    parser.add_argument("--region", default="eu-west-1", help="AWS region")
    args = parser.parse_args()

    run(region=args.region, dry_run=not args.delete)
