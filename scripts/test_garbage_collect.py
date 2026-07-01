import os
import sys

from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from garbage_collect import (  # noqa: E402
    find_unattached_volumes,
    find_unassociated_eips,
    find_idle_instances,
)


def _ec2():
    return MagicMock()


# ---------------------------------------------------------------------------
# EBS volume detection
# ---------------------------------------------------------------------------

class TestFindUnattachedVolumes:
    def test_detects_available_volumes(self):
        ec2 = _ec2()
        ec2.describe_volumes.return_value = {
            "Volumes": [
                {"VolumeId": "vol-111", "Size": 50, "VolumeType": "gp2",
                 "Tags": [{"Key": "Name", "Value": "test-vol"}]},
            ]
        }
        volumes, _, _ = find_unattached_volumes(ec2, dry_run=True)
        assert len(volumes) == 1
        assert volumes[0]["VolumeId"] == "vol-111"

    def test_empty_response_returns_no_volumes(self):
        ec2 = _ec2()
        ec2.describe_volumes.return_value = {"Volumes": []}
        volumes, deleted, savings = find_unattached_volumes(ec2, dry_run=True)
        assert volumes == []
        assert deleted == []
        assert savings == 0.0

    def test_savings_calculated_from_volume_size(self):
        ec2 = _ec2()
        ec2.describe_volumes.return_value = {
            "Volumes": [
                {"VolumeId": "vol-333", "Size": 100, "VolumeType": "gp2", "Tags": []},
            ]
        }
        _, _, savings = find_unattached_volumes(ec2, dry_run=True)
        assert savings == 10.0

    # Dry run mode
    def test_dry_run_does_not_call_delete_volume(self):
        ec2 = _ec2()
        ec2.describe_volumes.return_value = {
            "Volumes": [
                {"VolumeId": "vol-111", "Size": 20, "VolumeType": "gp2", "Tags": []},
            ]
        }
        _, deleted, _ = find_unattached_volumes(ec2, dry_run=True)
        ec2.delete_volume.assert_not_called()
        assert deleted == []

    # Delete mode
    def test_delete_mode_calls_delete_volume(self):
        ec2 = _ec2()
        ec2.describe_volumes.return_value = {
            "Volumes": [
                {"VolumeId": "vol-222", "Size": 100, "VolumeType": "gp3", "Tags": []},
            ]
        }
        _, deleted, _ = find_unattached_volumes(ec2, dry_run=False)
        ec2.delete_volume.assert_called_once_with(VolumeId="vol-222")
        assert "vol-222" in deleted

    def test_delete_mode_deletes_all_volumes(self):
        ec2 = _ec2()
        ec2.describe_volumes.return_value = {
            "Volumes": [
                {"VolumeId": "vol-A", "Size": 10, "VolumeType": "gp2", "Tags": []},
                {"VolumeId": "vol-B", "Size": 20, "VolumeType": "gp2", "Tags": []},
            ]
        }
        _, deleted, _ = find_unattached_volumes(ec2, dry_run=False)
        assert set(deleted) == {"vol-A", "vol-B"}
        assert ec2.delete_volume.call_count == 2


# ---------------------------------------------------------------------------
# EIP detection
# ---------------------------------------------------------------------------

class TestFindUnassociatedEips:
    def test_detects_unassociated_eips(self):
        ec2 = _ec2()
        ec2.describe_addresses.return_value = {
            "Addresses": [
                {"AllocationId": "eipalloc-111", "PublicIp": "1.2.3.4"},
                {"AllocationId": "eipalloc-222", "PublicIp": "5.6.7.8",
                 "AssociationId": "eipassoc-111"},
            ]
        }
        eips, _, _ = find_unassociated_eips(ec2, dry_run=True)
        assert len(eips) == 1
        assert eips[0]["AllocationId"] == "eipalloc-111"

    def test_associated_eips_are_ignored(self):
        ec2 = _ec2()
        ec2.describe_addresses.return_value = {
            "Addresses": [
                {"AllocationId": "eipalloc-444", "PublicIp": "1.1.1.1",
                 "AssociationId": "eipassoc-444"},
            ]
        }
        eips, released, savings = find_unassociated_eips(ec2, dry_run=True)
        assert eips == []
        assert savings == 0.0

    # Dry run mode
    def test_dry_run_does_not_call_release_address(self):
        ec2 = _ec2()
        ec2.describe_addresses.return_value = {
            "Addresses": [{"AllocationId": "eipalloc-111", "PublicIp": "1.2.3.4"}]
        }
        _, released, _ = find_unassociated_eips(ec2, dry_run=True)
        ec2.release_address.assert_not_called()
        assert released == []

    # Delete mode
    def test_delete_mode_calls_release_address(self):
        ec2 = _ec2()
        ec2.describe_addresses.return_value = {
            "Addresses": [{"AllocationId": "eipalloc-333", "PublicIp": "9.10.11.12"}]
        }
        _, released, _ = find_unassociated_eips(ec2, dry_run=False)
        ec2.release_address.assert_called_once_with(AllocationId="eipalloc-333")
        assert "eipalloc-333" in released


# ---------------------------------------------------------------------------
# Idle instance detection
# ---------------------------------------------------------------------------

class TestFindIdleInstances:
    def _instance(self, instance_id, instance_type, tags):
        return {
            "InstanceId": instance_id,
            "InstanceType": instance_type,
            "Tags": [{"Key": k, "Value": v} for k, v in tags.items()],
        }

    def _reservations(self, *instances):
        return {"Reservations": [{"Instances": list(instances)}]}

    def test_detects_large_instance_missing_cost_center(self):
        ec2 = _ec2()
        ec2.describe_instances.return_value = self._reservations(
            self._instance("i-111", "t3.large", {"Name": "my-instance"})
        )
        instances, _, _ = find_idle_instances(ec2, dry_run=True)
        assert len(instances) == 1
        assert instances[0]["InstanceId"] == "i-111"

    def test_detects_large_instance_missing_name_tag(self):
        ec2 = _ec2()
        ec2.describe_instances.return_value = self._reservations(
            self._instance("i-222", "t3.large", {"CostCenter": "eng"})
        )
        instances, _, _ = find_idle_instances(ec2, dry_run=True)
        assert len(instances) == 1

    def test_ignores_small_instances_even_when_untagged(self):
        ec2 = _ec2()
        ec2.describe_instances.return_value = self._reservations(
            self._instance("i-333", "t3.micro", {}),
            self._instance("i-334", "t3.small", {}),
        )
        instances, _, _ = find_idle_instances(ec2, dry_run=True)
        assert instances == []

    def test_ignores_large_instance_with_both_tags(self):
        ec2 = _ec2()
        ec2.describe_instances.return_value = self._reservations(
            self._instance("i-444", "t3.large", {"Name": "prod", "CostCenter": "eng"})
        )
        instances, _, _ = find_idle_instances(ec2, dry_run=True)
        assert instances == []

    # Dry run mode
    def test_dry_run_does_not_call_stop_instances(self):
        ec2 = _ec2()
        ec2.describe_instances.return_value = self._reservations(
            self._instance("i-555", "t3.large", {})
        )
        _, stopped, _ = find_idle_instances(ec2, dry_run=True)
        ec2.stop_instances.assert_not_called()
        assert stopped == []

    # Delete mode
    def test_delete_mode_calls_stop_instances(self):
        ec2 = _ec2()
        ec2.describe_instances.return_value = self._reservations(
            self._instance("i-666", "t3.large", {"Name": "idle"})
        )
        _, stopped, _ = find_idle_instances(ec2, dry_run=False)
        ec2.stop_instances.assert_called_once_with(InstanceIds=["i-666"])
        assert "i-666" in stopped
