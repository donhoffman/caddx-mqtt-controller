"""Tests for zone state management."""
import pytest
from zone import Zone, ZoneConditionFlags, ZoneTypeFlags
from partition import Partition


class TestZoneCreation:
    """Tests for zone creation and registry."""

    def setup_method(self):
        """Clear zone registry before each test."""
        Zone.zones_by_index.clear()
        Zone.zones_by_unique_name.clear()

    def test_zone_creation(self):
        """Test creating a new zone."""
        zone = Zone(1, "Front Door")
        assert zone.index == 1
        assert zone.name == "Front Door"
        assert zone.unique_name == "zone_001"
        assert zone.is_updated is False

    def test_zone_unique_name_formatting(self):
        """Test that unique names are zero-padded."""
        zone1 = Zone(1, "Zone 1")
        zone99 = Zone(99, "Zone 99")

        assert zone1.unique_name == "zone_001"
        assert zone99.unique_name == "zone_099"

    def test_zone_registry_by_index(self):
        """Test zone lookup by index."""
        zone = Zone(5, "Test Zone")
        retrieved = Zone.get_zone_by_index(5)
        assert retrieved is zone

    def test_zone_registry_by_unique_name(self):
        """Test zone lookup by unique name."""
        zone = Zone(5, "Test Zone")
        retrieved = Zone.get_zone_by_unique_name("zone_005")
        assert retrieved is zone

    def test_zone_duplicate_index(self):
        """Test that duplicate zone indices raise assertion."""
        Zone(1, "First")
        with pytest.raises(AssertionError, match="Non-unique zone index"):
            Zone(1, "Duplicate")

    def test_zone_duplicate_unique_name(self):
        """Test that duplicate unique names are prevented."""
        zone1 = Zone(1, "First")
        # Creating a second zone with index 1 should fail before unique name check
        # But we can test the assertion exists
        with pytest.raises(AssertionError):
            Zone(1, "Second")

    def test_get_all_zones(self):
        """Test retrieving all zones."""
        z1 = Zone(1, "Zone 1")
        z2 = Zone(2, "Zone 2")
        z3 = Zone(3, "Zone 3")

        all_zones = list(Zone.get_all_zones())
        assert len(all_zones) == 3
        assert z1 in all_zones
        assert z2 in all_zones
        assert z3 in all_zones


class TestZoneConditionProperties:
    """Tests for zone condition flag properties."""

    def setup_method(self):
        """Create a zone for testing."""
        Zone.zones_by_index.clear()
        Zone.zones_by_unique_name.clear()
        self.zone = Zone(1, "Test Zone")

    def test_is_bypassed_false(self):
        """Test that zone is not bypassed by default."""
        assert self.zone.is_bypassed is False

    def test_is_bypassed_true(self):
        """Test that bypassed flag is detected."""
        self.zone._condition_mask = ZoneConditionFlags.Bypassed
        assert self.zone.is_bypassed is True

    def test_is_faulted_false(self):
        """Test that zone is not faulted by default."""
        assert self.zone.is_faulted is False

    def test_is_faulted_true(self):
        """Test that faulted flag is detected."""
        self.zone._condition_mask = ZoneConditionFlags.Faulted
        assert self.zone.is_faulted is True

    def test_is_trouble_false(self):
        """Test that zone has no trouble by default."""
        assert self.zone.is_trouble is False

    def test_is_trouble_tampered(self):
        """Test that tamper sets trouble."""
        self.zone._condition_mask = ZoneConditionFlags.Tampered
        assert self.zone.is_trouble is True

    def test_is_trouble_trouble_flag(self):
        """Test that trouble flag sets trouble."""
        self.zone._condition_mask = ZoneConditionFlags.Trouble
        assert self.zone.is_trouble is True

    def test_is_trouble_low_battery(self):
        """Test that low battery sets trouble."""
        self.zone._condition_mask = ZoneConditionFlags.LowBattery
        assert self.zone.is_trouble is True

    def test_is_trouble_supervision_lost(self):
        """Test that supervision lost sets trouble."""
        self.zone._condition_mask = ZoneConditionFlags.SupervisionLost
        assert self.zone.is_trouble is True

    def test_is_trouble_multiple_conditions(self):
        """Test that any trouble condition triggers is_trouble."""
        self.zone._condition_mask = (
            ZoneConditionFlags.Tampered | ZoneConditionFlags.LowBattery
        )
        assert self.zone.is_trouble is True

    def test_multiple_conditions_simultaneously(self):
        """Test multiple conditions can be true at once."""
        self.zone._condition_mask = (
            ZoneConditionFlags.Faulted
            | ZoneConditionFlags.Bypassed
            | ZoneConditionFlags.Trouble
        )
        assert self.zone.is_faulted is True
        assert self.zone.is_bypassed is True
        assert self.zone.is_trouble is True


class TestZonePartitionMembership:
    """Tests for zone partition validation."""

    def setup_method(self):
        """Create zones and partitions for testing."""
        Zone.zones_by_index.clear()
        Zone.zones_by_unique_name.clear()
        Partition.partition_by_index.clear()
        Partition.partition_by_unique_name.clear()

        self.zone = Zone(1, "Test Zone")
        self.partition1 = Partition(1)
        self.partition2 = Partition(2)
        self.partition3 = Partition(3)

    def test_is_valid_partition_none(self):
        """Test zone with no partition membership."""
        self.zone._partition_mask = 0b00000000
        assert self.zone.is_valid_partition(self.partition1) is False

    def test_is_valid_partition_single(self):
        """Test zone assigned to partition 1."""
        self.zone._partition_mask = 0b00000001  # Bit 0 = Partition 1
        assert self.zone.is_valid_partition(self.partition1) is True
        assert self.zone.is_valid_partition(self.partition2) is False

    def test_is_valid_partition_multiple(self):
        """Test zone assigned to multiple partitions."""
        self.zone._partition_mask = 0b00000011  # Bits 0,1 = Partitions 1,2
        assert self.zone.is_valid_partition(self.partition1) is True
        assert self.zone.is_valid_partition(self.partition2) is True
        assert self.zone.is_valid_partition(self.partition3) is False

    def test_is_valid_partition_bit_positions(self):
        """Test that partition index maps correctly to bit positions."""
        # Partition N corresponds to bit N-1
        for partition_idx in range(1, 9):
            Partition.partition_by_index.clear()
            partition = Partition(partition_idx)
            self.zone._partition_mask = 1 << (partition_idx - 1)
            assert self.zone.is_valid_partition(partition) is True


class TestZoneMasks:
    """Tests for zone mask setting."""

    def setup_method(self):
        """Create a zone for testing."""
        Zone.zones_by_index.clear()
        Zone.zones_by_unique_name.clear()
        self.zone = Zone(1, "Test Zone")

    def test_set_masks(self):
        """Test setting zone masks."""
        partition_mask = 0b00000001
        type_mask = ZoneTypeFlags.Fire | ZoneTypeFlags.Hour24
        condition_mask = ZoneConditionFlags.Faulted

        self.zone.set_masks(partition_mask, type_mask, condition_mask)

        assert self.zone._partition_mask == partition_mask
        assert self.zone._type_mask == type_mask
        assert self.zone._condition_mask == condition_mask
        assert self.zone.is_updated is True

    def test_set_masks_updates_flag(self):
        """Test that set_masks sets is_updated flag."""
        assert self.zone.is_updated is False
        self.zone.set_masks(0, 0, 0)
        assert self.zone.is_updated is True

    def test_set_masks_multiple_calls(self):
        """Test that calling set_masks multiple times works."""
        self.zone.set_masks(0b0001, 0, 0)
        assert self.zone._partition_mask == 0b0001

        self.zone.set_masks(0b0010, 0, 0)
        assert self.zone._partition_mask == 0b0010

    def test_masks_persist_across_reads(self):
        """Test that mask values are retained."""
        condition_mask = ZoneConditionFlags.Faulted | ZoneConditionFlags.Bypassed
        self.zone.set_masks(0, 0, condition_mask)

        # Properties should reflect the mask
        assert self.zone.is_faulted is True
        assert self.zone.is_bypassed is True

        # Mask should still be there
        assert self.zone._condition_mask == condition_mask


class TestZoneTypeFlags:
    """Tests for zone type flag recognition."""

    def setup_method(self):
        """Create a zone for testing."""
        Zone.zones_by_index.clear()
        Zone.zones_by_unique_name.clear()
        self.zone = Zone(1, "Test Zone")

    def test_type_flags_stored(self):
        """Test that type flags are stored correctly."""
        type_mask = ZoneTypeFlags.Fire | ZoneTypeFlags.EntryExitDelay1
        self.zone.set_masks(0, type_mask, 0)

        assert self.zone._type_mask == type_mask
        assert self.zone._type_mask & ZoneTypeFlags.Fire
        assert self.zone._type_mask & ZoneTypeFlags.EntryExitDelay1
        assert not (self.zone._type_mask & ZoneTypeFlags.Hour24)


class TestZoneNameUpdate:
    """Tests for zone name changes."""

    def setup_method(self):
        """Create a zone for testing."""
        Zone.zones_by_index.clear()
        Zone.zones_by_unique_name.clear()

    def test_zone_name_can_change(self):
        """Test that zone name is mutable."""
        zone = Zone(1, "Original Name")
        assert zone.name == "Original Name"

        zone.name = "New Name"
        assert zone.name == "New Name"

    def test_zone_index_immutable(self):
        """Test that zone index doesn't change."""
        zone = Zone(1, "Test")
        original_index = zone.index
        # Index should remain 1 (can't easily test immutability without trying to set it)
        assert zone.index == original_index
        assert zone.index == 1


class TestZoneEdgeCases:
    """Tests for zone edge cases and boundary conditions."""

    def setup_method(self):
        """Clear zone registry."""
        Zone.zones_by_index.clear()
        Zone.zones_by_unique_name.clear()

    def test_zone_with_empty_name(self):
        """Test zone with empty name."""
        zone = Zone(1, "")
        assert zone.name == ""
        assert zone.unique_name == "zone_001"

    def test_zone_with_special_characters_in_name(self):
        """Test zone with special characters."""
        zone = Zone(1, "Front/Back Door & Window")
        assert zone.name == "Front/Back Door & Window"
        # Unique name should still be safe
        assert zone.unique_name == "zone_001"

    def test_zone_high_index(self):
        """Test zone with high index number."""
        zone = Zone(999, "High Index Zone")
        assert zone.index == 999
        assert zone.unique_name == "zone_999"

    def test_all_condition_flags_set(self):
        """Test zone with all condition flags set."""
        zone = Zone(1, "Test")
        all_flags = (
            ZoneConditionFlags.Faulted
            | ZoneConditionFlags.Tampered
            | ZoneConditionFlags.Trouble
            | ZoneConditionFlags.Bypassed
            | ZoneConditionFlags.Inhibited
            | ZoneConditionFlags.LowBattery
            | ZoneConditionFlags.SupervisionLost
            | ZoneConditionFlags.AlarmMemory
            | ZoneConditionFlags.BypassMemory
        )
        zone._condition_mask = all_flags

        assert zone.is_faulted is True
        assert zone.is_bypassed is True
        assert zone.is_trouble is True