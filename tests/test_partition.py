"""Tests for partition state management."""
import pytest
from partition import Partition, PartitionConditionFlags


class TestPartitionStateTransitions:
    """Tests for partition state machine."""

    def setup_method(self):
        """Clear partition registry before each test."""
        Partition.partition_by_index.clear()
        Partition.partition_by_unique_name.clear()

    def test_partition_creation(self):
        """Test creating a new partition."""
        partition = Partition(1)
        assert partition.index == 1
        assert partition.unique_name == "partition_1"
        assert partition.condition_flags is None
        assert partition.state is None

    def test_partition_registry_by_index(self):
        """Test partition lookup by index."""
        partition = Partition(1)
        retrieved = Partition.get_partition_by_index(1)
        assert retrieved is partition

    def test_partition_registry_by_unique_name(self):
        """Test partition lookup by unique name."""
        partition = Partition(1)
        retrieved = Partition.get_partition_by_unique_name("partition_1")
        assert retrieved is partition

    def test_partition_creation_bounds(self):
        """Test partition index validation."""
        # Valid partitions (1-8)
        for i in range(1, 9):
            Partition.partition_by_index.clear()
            partition = Partition(i)
            assert partition.index == i

    def test_partition_invalid_index_low(self):
        """Test that partition 0 raises assertion."""
        with pytest.raises(AssertionError):
            Partition(0)

    def test_partition_invalid_index_high(self):
        """Test that partition > 8 raises assertion."""
        with pytest.raises(AssertionError):
            Partition(9)

    def test_partition_duplicate_index(self):
        """Test that duplicate partition indices raise assertion."""
        Partition(1)
        with pytest.raises(AssertionError, match="Non-unique partition index"):
            Partition(1)

    def test_get_all_partitions(self):
        """Test retrieving all partitions."""
        p1 = Partition(1)
        p2 = Partition(2)
        p3 = Partition(3)

        all_partitions = list(Partition.get_all_partitions())
        assert len(all_partitions) == 3
        assert p1 in all_partitions
        assert p2 in all_partitions
        assert p3 in all_partitions


class TestPartitionStateDisarmed:
    """Tests for DISARMED state detection."""

    def setup_method(self):
        """Create a partition for testing."""
        Partition.partition_by_index.clear()
        Partition.partition_by_unique_name.clear()
        self.partition = Partition(1)

    def test_disarmed_ready_to_arm(self):
        """Test DISARMED state with ReadyToArm flag."""
        self.partition.condition_flags = PartitionConditionFlags.ReadyToArm
        assert self.partition.state == Partition.State.DISARMED

    def test_disarmed_ready_to_force_arm(self):
        """Test DISARMED state with ReadyToForceArm flag."""
        self.partition.condition_flags = PartitionConditionFlags.ReadyToForceArm
        assert self.partition.state == Partition.State.DISARMED

    def test_disarmed_both_ready_flags(self):
        """Test DISARMED with both ready flags."""
        self.partition.condition_flags = (
            PartitionConditionFlags.ReadyToArm
            | PartitionConditionFlags.ReadyToForceArm
        )
        assert self.partition.state == Partition.State.DISARMED


class TestPartitionStateArmed:
    """Tests for armed states (HOME/AWAY/ARMING)."""

    def setup_method(self):
        """Create a partition for testing."""
        Partition.partition_by_index.clear()
        Partition.partition_by_unique_name.clear()
        self.partition = Partition(1)

    def test_armed_away_basic(self):
        """Test ARMED_AWAY with just Armed flag."""
        self.partition.condition_flags = PartitionConditionFlags.Armed
        assert self.partition.state == Partition.State.ARMED_AWAY

    def test_armed_home_with_entry_guard(self):
        """Test ARMED_HOME with Armed + Entry guard flags."""
        self.partition.condition_flags = (
            PartitionConditionFlags.Armed | PartitionConditionFlags.EntryGuard
        )
        assert self.partition.state == Partition.State.ARMED_HOME

    def test_arming_with_exit1(self):
        """Test ARMING state with Armed + Exit1."""
        self.partition.condition_flags = (
            PartitionConditionFlags.Armed | PartitionConditionFlags.Exit1
        )
        assert self.partition.state == Partition.State.ARMING

    def test_arming_with_exit2(self):
        """Test ARMING state with Armed + Exit2."""
        self.partition.condition_flags = (
            PartitionConditionFlags.Armed | PartitionConditionFlags.Exit2
        )
        assert self.partition.state == Partition.State.ARMING

    def test_arming_with_both_exits(self):
        """Test ARMING state with both exit flags."""
        self.partition.condition_flags = (
            PartitionConditionFlags.Armed
            | PartitionConditionFlags.Exit1
            | PartitionConditionFlags.Exit2
        )
        assert self.partition.state == Partition.State.ARMING

    def test_pending_with_entry(self):
        """Test PENDING state with Armed + Entry."""
        self.partition.condition_flags = (
            PartitionConditionFlags.Armed | PartitionConditionFlags.Entry
        )
        assert self.partition.state == Partition.State.PENDING


class TestPartitionStateTriggered:
    """Tests for TRIGGERED state detection."""

    def setup_method(self):
        """Create a partition for testing."""
        Partition.partition_by_index.clear()
        Partition.partition_by_unique_name.clear()
        self.partition = Partition(1)

    def test_triggered_with_siren_on(self):
        """Test TRIGGERED state with SirenOn flag."""
        self.partition.condition_flags = PartitionConditionFlags.SirenOn
        assert self.partition.state == Partition.State.TRIGGERED

    def test_triggered_with_steady_siren(self):
        """Test TRIGGERED state with SteadySirenOn flag."""
        self.partition.condition_flags = PartitionConditionFlags.SteadySirenOn
        assert self.partition.state == Partition.State.TRIGGERED

    def test_triggered_with_both_sirens(self):
        """Test TRIGGERED with both siren flags."""
        self.partition.condition_flags = (
            PartitionConditionFlags.SirenOn | PartitionConditionFlags.SteadySirenOn
        )
        assert self.partition.state == Partition.State.TRIGGERED

    def test_triggered_overrides_armed(self):
        """Test that TRIGGERED state takes priority over armed states."""
        # Even if armed, siren means triggered
        self.partition.condition_flags = (
            PartitionConditionFlags.Armed | PartitionConditionFlags.SirenOn
        )
        assert self.partition.state == Partition.State.TRIGGERED


class TestPartitionStatePriority:
    """Tests for state priority/precedence."""

    def setup_method(self):
        """Create a partition for testing."""
        Partition.partition_by_index.clear()
        Partition.partition_by_unique_name.clear()
        self.partition = Partition(1)

    def test_triggered_highest_priority(self):
        """Siren should override all other states."""
        # Set multiple flags, but siren should win
        self.partition.condition_flags = (
            PartitionConditionFlags.SirenOn
            | PartitionConditionFlags.Armed
            | PartitionConditionFlags.ReadyToArm
        )
        assert self.partition.state == Partition.State.TRIGGERED

    def test_arming_overrides_armed_away(self):
        """Exit delay should override steady armed state."""
        self.partition.condition_flags = (
            PartitionConditionFlags.Armed | PartitionConditionFlags.Exit1
        )
        assert self.partition.state == Partition.State.ARMING
        assert self.partition.state != Partition.State.ARMED_AWAY

    def test_pending_overrides_armed_away(self):
        """Entry delay should override armed away."""
        self.partition.condition_flags = (
            PartitionConditionFlags.Armed | PartitionConditionFlags.Entry
        )
        assert self.partition.state == Partition.State.PENDING
        assert self.partition.state != Partition.State.ARMED_AWAY

    def test_entry_guard_sets_armed_home(self):
        """Entry guard should set ARMED_HOME not ARMED_AWAY."""
        self.partition.condition_flags = (
            PartitionConditionFlags.Armed | PartitionConditionFlags.EntryGuard
        )
        assert self.partition.state == Partition.State.ARMED_HOME
        assert self.partition.state != Partition.State.ARMED_AWAY


class TestPartitionStateNull:
    """Tests for null/undefined states."""

    def setup_method(self):
        """Create a partition for testing."""
        Partition.partition_by_index.clear()
        Partition.partition_by_unique_name.clear()
        self.partition = Partition(1)

    def test_state_none_when_no_flags_set(self):
        """State should be None when condition_flags is None."""
        assert self.partition.condition_flags is None
        assert self.partition.state is None

    def test_pending_fallback_for_unknown_state(self):
        """Unknown flag combinations should fall back to PENDING."""
        # Set some random flags that don't clearly indicate a state
        self.partition.condition_flags = PartitionConditionFlags.ChimeMode
        assert self.partition.state == Partition.State.PENDING


class TestPartitionConditionLogging:
    """Tests for partition condition logging (no assertions, just coverage)."""

    def setup_method(self):
        """Create a partition for testing."""
        Partition.partition_by_index.clear()
        Partition.partition_by_unique_name.clear()
        self.partition = Partition(1)

    def test_log_condition_executes(self):
        """Test that log_condition can be called without error."""
        self.partition.condition_flags = (
            PartitionConditionFlags.Armed | PartitionConditionFlags.ReadyToArm
        )

        # Should not raise any exceptions
        log_entries = []
        self.partition.log_condition(lambda msg: log_entries.append(msg))

        # Should have logged something
        assert len(log_entries) > 0
        assert "Partition 1" in log_entries[0]