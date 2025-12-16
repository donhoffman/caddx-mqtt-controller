from typing import Dict, Optional, ValuesView, Callable
from enum import Enum, IntEnum


class PartitionConditionFlags(IntEnum):
    """
    Partition condition flag bit definitions from Caddx protocol.

    48-bit mask indicating various partition states and conditions.
    Each flag represents a specific partition status (Armed, Entry, Exit, etc.).
    """
    # User code required to bypass zones.
    BypassCodeRequired = 0b_00000000_00000000_00000000_00000000_00000000_00000001
    # Fire trouble.
    FireTrouble = 0b_00000000_00000000_00000000_00000000_00000000_00000010
    # Fire alarm.
    Fire = 0b_00000000_00000000_00000000_00000000_00000000_00000100
    # Pulsing buzzer.
    PulsingBuzzer = 0b_00000000_00000000_00000000_00000000_00000000_00001000
    # TLM (Telephone Line Monitoring) fault memory.
    TLMFaultMemory = 0b_00000000_00000000_00000000_00000000_00000000_00010000
    # Armed.
    Armed = 0b_00000000_00000000_00000000_00000000_00000000_01000000
    # Instant.
    Instant = 0b_00000000_00000000_00000000_00000000_00000000_10000000
    # Previous alarm.
    PreviousAlarm = 0b_00000000_00000000_00000000_00000000_00000001_00000000
    # Siren on.
    SirenOn = 0b_00000000_00000000_00000000_00000000_00000010_00000000
    # Steady siren on.
    SteadySirenOn = 0b_00000000_00000000_00000000_00000000_00000100_00000000
    # Alarm memory.
    AlarmMemory = 0b_00000000_00000000_00000000_00000000_00001000_00000000
    # Tamper.
    Tamper = 0b_00000000_00000000_00000000_00000000_00010000_00000000
    # Cancel entered.
    CancelEntered = 0b_00000000_00000000_00000000_00000000_00100000_00000000
    # Code entered.
    CodeEntered = 0b_00000000_00000000_00000000_00000000_01000000_00000000
    # Cancel pending.
    CancelPending = 0b_00000000_00000000_00000000_00000000_10000000_00000000
    # Silent exit enabled.
    SilentExitEnabled = 0b_00000000_00000000_00000000_00000010_00000000_00000000
    # Entry Guard.
    EntryGuard = 0b_00000000_00000000_00000000_00000100_00000000_00000000
    # Chime mode.
    ChimeMode = 0b_00000000_00000000_00000000_00001000_00000000_00000000
    # Entry.
    Entry = 0b_00000000_00000000_00000000_00010000_00000000_00000000
    # Delay expiration warning.
    DelayExpirationWarn = 0b_00000000_00000000_00000000_00100000_00000000_00000000
    # Exit 1.
    Exit1 = 0b_00000000_00000000_00000000_01000000_00000000_00000000
    # Exit 2.
    Exit2 = 0b_00000000_00000000_00000000_10000000_00000000_00000000
    # LED extinguish.
    LEDExtinguish = 0b_00000000_00000000_00000001_00000000_00000000_00000000
    # Cross timing.
    CrossTiming = 0b_00000000_00000000_00000010_00000000_00000000_00000000
    # Recent close being timed.
    RecentCloseTimed = 0b_00000000_00000000_00000100_00000000_00000000_00000000
    # Exit error triggered.
    ExitErrorTriggered = 0b_00000000_00000000_00010000_00000000_00000000_00000000
    # Auto home inhibited.
    AutoHomeInhibited = 0b_00000000_00000000_00100000_00000000_00000000_00000000
    # Sensor low battery.
    SensorLowBattery = 0b_00000000_00000000_01000000_00000000_00000000_00000000
    # Sensor lost supervision.
    SensorLostSupervision = 0b_00000000_00000000_10000000_00000000_00000000_00000000
    # Zone bypassed.
    ZoneBypassed = 0b_00000000_00000001_00000000_00000000_00000000_00000000
    # Force arm triggered.
    ForceArmTriggered = 0b_00000000_00000010_00000000_00000000_00000000_00000000
    # Ready to arm.
    ReadyToArm = 0b_00000000_00000100_00000000_00000000_00000000_00000000
    # Ready to force arm.
    ReadyToForceArm = 0b_00000000_00001000_00000000_00000000_00000000_00000000
    # Valid PIN accepted.
    ValidPINAccepted = 0b_00000000_00010000_00000000_00000000_00000000_00000000
    # Chime on (sounding).
    ChimeOn = 0b_00000000_00100000_00000000_00000000_00000000_00000000
    # Error beep (triple beep).
    ErrorBeep = 0b_00000000_01000000_00000000_00000000_00000000_00000000
    # Tone on (activation tone).
    ToneOn = 0b_00000000_10000000_00000000_00000000_00000000_00000000
    # Entry 1.
    Entry1 = 0b_00000001_00000000_00000000_00000000_00000000_00000000
    # Open period.
    OpenPeriod = 0b_00000010_00000000_00000000_00000000_00000000_00000000
    # Alarm sent using phone 1.
    AlarmSentPhone1 = 0b_00000100_00000000_00000000_00000000_00000000_00000000
    # Alarm sent using phone 2.
    AlarmSentPhone2 = 0b_00001000_00000000_00000000_00000000_00000000_00000000
    # Alarm sent using phone 3.
    AlarmSentPhone3 = 0b_00010000_00000000_00000000_00000000_00000000_00000000
    # Cancel report is in the stack.
    CancelInStack = 0b_00100000_00000000_00000000_00000000_00000000_00000000
    # Keyswitch armed.
    KeyswitchArmed = 0b_01000000_00000000_00000000_00000000_00000000_00000000
    # Delay trip in progress.
    DelayTripInProgress = 0b_10000000_00000000_00000000_00000000_00000000_00000000


class Partition(object):
    """
    Represents an alarm partition in the Caddx alarm panel.

    Partitions divide the alarm system into independent security areas (1-8).
    The partition's alarm state is derived from its 48-bit condition flags
    using a priority-based state machine. Partitions self-register in class-level
    dictionaries for lookup by index or unique_name.

    Attributes:
        index: Partition number (1-8)
        unique_name: Generated identifier in format "partition_N"
        condition_flags: 48-bit mask of partition condition flags
    """
    class State(Enum):
        """
        Alarm partition state enumeration for Home Assistant.

        Maps partition condition flags to standard alarm states:
        - DISARMED: System is off, ready to arm
        - ARMED_HOME: Armed in stay mode (entry guard)
        - ARMED_AWAY: Armed in away mode (full protection)
        - PENDING: Entry or exit delay in progress
        - TRIGGERED: Alarm is sounding
        - ARMING: Exit delay in progress
        - DISARMING: Disarm sequence in progress
        """
        DISARMED = ("disarmed",)
        ARMED_HOME = ("armed_home",)
        ARMED_AWAY = ("armed_away",)
        PENDING = ("pending",)
        TRIGGERED = ("triggered",)
        ARMING = ("arming",)
        DISARMING = "disarming"

    partition_by_index: Dict[int, "Partition"] = {}
    partition_by_unique_name: Dict[str, "Partition"] = {}

    @classmethod
    def get_partition_by_index(cls, index: int) -> Optional["Partition"]:
        """
        Retrieve a partition by its numeric index.

        Args:
            index: The partition index (1-8)

        Returns:
            Partition object if found, None otherwise
        """
        return cls.partition_by_index.get(index)

    @classmethod
    def get_partition_by_unique_name(cls, unique_name: str) -> Optional["Partition"]:
        """
        Retrieve a partition by its unique name identifier.

        Args:
            unique_name: The partition unique name (format: "partition_N")

        Returns:
            Partition object if found, None otherwise
        """
        return cls.partition_by_unique_name.get(unique_name)

    @classmethod
    def get_all_partitions(cls) -> ValuesView["Partition"]:
        """
        Get all registered partitions.

        Returns:
            View of all Partition objects
        """
        return cls.partition_by_index.values()

    def __init__(self, index: int):
        """
        Initialize a new Partition.

        The partition self-registers in class-level dictionaries for later lookup.
        Duplicate indices will trigger an assertion error.

        Args:
            index: Partition number (1-8)

        Raises:
            AssertionError: If index is not in range 1-8 or already exists
        """
        self.index = index
        assert 1 <= index <= 8
        self.unique_name = f"partition_{self.index}"
        assert index not in self.partition_by_index, "Non-unique partition index"
        self.__class__.partition_by_index[index] = self
        self.__class__.partition_by_unique_name[self.unique_name] = self
        self.condition_flags: Optional[int] = None

    @property
    def state(self) -> Optional["Partition.State"]:
        """
        Compute current alarm state from condition flags.

        Uses a priority-based state machine:
        1. TRIGGERED (highest) - Siren is active
        2. ARMING - Armed with exit delay active
        3. PENDING - Armed with entry delay active
        4. ARMED_HOME - Armed with entry guard
        5. ARMED_AWAY - Armed without entry guard
        6. DISARMED - Ready to arm
        7. PENDING (fallback) - Unknown state

        Returns:
            Current State enum value, or None if condition_flags not yet set
        """
        if self.condition_flags is None:
            return None
        if (self.condition_flags & PartitionConditionFlags.SirenOn) or (
            self.condition_flags & PartitionConditionFlags.SteadySirenOn
        ):
            return Partition.State.TRIGGERED
        if self.condition_flags & PartitionConditionFlags.Armed:
            if (self.condition_flags & PartitionConditionFlags.Exit1) or (
                self.condition_flags & PartitionConditionFlags.Exit2
            ):
                return Partition.State.ARMING
            if self.condition_flags & PartitionConditionFlags.Entry:
                return Partition.State.PENDING
            if self.condition_flags & PartitionConditionFlags.EntryGuard:
                return Partition.State.ARMED_HOME
            else:
                return Partition.State.ARMED_AWAY
        if (self.condition_flags & PartitionConditionFlags.ReadyToArm) or (
            self.condition_flags & PartitionConditionFlags.ReadyToForceArm
        ):
            return Partition.State.DISARMED
        # There are a few conditions that don't fit neatly into the state model so this is a catch-all
        return Partition.State.PENDING

    def log_condition(self, logger: Callable[[str], None]) -> None:
        """
        Log detailed partition condition flags.

        Outputs the raw 48-bit condition flags value in hexadecimal,
        followed by a space-separated list of all set flag names.

        Args:
            logger: Logging function to call with formatted strings
        """
        logger(f"Partition {self.index} raw value: {self.condition_flags:0>12x}")
        log_entry = f"Partition {self.index} conditions: "
        for flag in PartitionConditionFlags:
            if flag & self.condition_flags:
                log_entry += f"{flag.name} "
        logger(log_entry)
