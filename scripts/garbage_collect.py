import boto3

def find_and_delete_unattached_volumes(region="eu-west-1", dry_run=True):
    ec2 = boto3.client("ec2", region_name=region)

    response = ec2.describe_volumes(
        Filters=[{"Name": "status", "Values": ["available"]}]
    )

    volumes = response["Volumes"]
    print(f"Found {len(volumes)} unattached EBS volumes in {region}")

    for vol in volumes:
        vol_id = vol["VolumeId"]
        size = vol["Size"]
        name = next((t["Value"] for t in vol.get("Tags", []) if t["Key"] == "Name"), "unnamed")
        print(f"  - {vol_id} | {size}GB | {name}")

        if not dry_run:
            ec2.delete_volume(VolumeId=vol_id)
            print(f"    DELETED {vol_id}")
        else:
            print(f"    [DRY RUN] Would delete {vol_id}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--delete", action="store_true", help="Actually delete volumes")
    parser.add_argument("--region", default="eu-west-1")
    args = parser.parse_args()

    find_and_delete_unattached_volumes(region=args.region, dry_run=not args.delete)
