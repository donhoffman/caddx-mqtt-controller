from typing import Dict, Optional, ValuesView
from enum import IntEnum
import logging

logger = logging.getLogger("app.zone")


class ZoneTypeFlags(IntEnum):
    """
    Zone type flag bit definitions from Caddx protocol.

    24-bit mask indicating zone type characteristics and behavior.
    Defines how the zone operates (Fire, 24-hour, Entry/Exit delay, etc.).
    """
    Fire = 0b_00000000_00000000_00000001  # Zone is a fire zone.
    Hour24 = 0b_00000000_00000000_00000010  # Zone is a 24-hour zone.
    KeySwitch = 0b_00000000_00000000_00000100  # Zone is a keyswitch zone.
    Follower = 0b_00000000_00000000_00001000  # Zone is a follower zone.
    EntryExitDelay1 = (
        0b_00000000_00000000_00010000  # Zone is an entry/exit delay 1 zone.
    )
    EntryExitDelay2 = (
        0b_00000000_00000000_00100000  # Zone is an entry/exit delay 2 zone.
    )
    Interior = 0b_00000000_00000000_01000000  # Zone is an interior zone.
    LocalOnly = 0b_00000000_00000000_10000000  # Zone is local only.
    KeypadSounder = 0b_00000000_00000001_00000000  # Zone is a keypad sounder zone.
    YelpingSiren = 0b_00000000_00000010_00000000  # Zone is a yelping siren zone.
    SteadySiren = 0b_00000000_00000100_00000000  # Zone is a steady siren zone.
    Chime = 0b_00000000_00001000_00000000  # Zone is a chime zone.
    Bypassable = 0b_00000000_00010000_00000000  # Zone is bypassable.
    GroupBypassable = 0b_00000000_00100000_00000000  # Zone is group bypassable.
    ForceArmable = 0b_00000000_01000000_00000000  # Zone is force armable.
    EntryGuard = 0b_00000000_10000000_00000000  # Zone is an entry guard zone.
    FastLoopResponse = (
        0b_00000001_00000000_00000000  # Zone is a fast loop response zone.
    )
    DoubleEOLTamper = 0b_00000010_00000000_00000000  # Zone is a double EOL tamper zone.
    Trouble = 0b_00000100_00000000_00000000  # Zone is a trouble zone.
    CrossZone = 0b_00001000_00000000_00000000  # Zone is a cross zone.
    DialerDelay = 0b_00010000_00000000_00000000  # Zone is a dialer delay zone.
    SwingerShutdown = 0b_00100000_00000000_00000000  # Zone is a swinger shutdown zone.
    Restorable = 0b_01000000_00000000_00000000  # Zone is restorable.
    ListenIn = 0b_10000000_00000000_00000000  # Zone is a listen-in zone.


class ZoneConditionFlags(IntEnum):
    """
    Zone condition flag bit definitions from Caddx protocol.

    16-bit mask indicating current zone status and conditions.
    Includes faulted, tampered, bypassed, trouble states, etc.
    """
    Faulted = 0b_00000000_00000001  # Zone is faulted (aka "triggered").
    Tampered = 0b_00000000_00000010  # Zone is tampered.
    Trouble = 0b_00000000_00000100  # Zone showing trouble state.
    Bypassed = 0b_00000000_00001000  # Zone is bypassed.
    Inhibited = 0b_00000000_00010000  # Zone is inhibited.
    LowBattery = 0b_00000000_00100000  # Zone has low battery.
    SupervisionLost = 0b_00000000_01000000  # Zone has lost supervision.
    AlarmMemory = 0b_00000001_00000000  # Zone triggered the last alarm event.
    BypassMemory = (
        0b_00000010_00000000  # Zone was bypassed during the last alarm event.
    )


class Zone(object):
    """
    Represents a physical alarm zone in the Caddx alarm panel.

    Each zone has an index (1-based), name, and maintains state through
    partition, type, and condition masks. Zones self-register in class-level
    dictionaries for lookup by index or unique_name.

    Attributes:
        index: Zone number (1-based, server indexing)
        name: Human-readable zone name from panel
        unique_name: Generated identifier in format "zone_NNN"
        is_updated: Flag indicating if zone state has changed
    """
    zones_by_index: Dict[int, "Zone"] = {}
    zones_by_unique_name: Dict[str, "Zone"] = {}

    @classmethod
    def get_zone_by_index(cls, zone_id: int) -> Optional["Zone"]:
        """
        Retrieve a zone by its numeric index.

        Args:
            zone_id: The zone index (1-based)

        Returns:
            Zone object if found, None otherwise
        """
        return cls.zones_by_index.get(zone_id)

    @classmethod
    def get_zone_by_unique_name(cls, unique_name: str) -> Optional["Zone"]:
        """
        Retrieve a zone by its unique name identifier.

        Args:
            unique_name: The zone unique name (format: "zone_NNN")

        Returns:
            Zone object if found, None otherwise
        """
        return cls.zones_by_unique_name.get(unique_name)

    @classmethod
    def get_all_zones(cls) -> ValuesView["Zone"]:
        """
        Get all registered zones.

        Returns:
            View of all Zone objects
        """
        return cls.zones_by_index.values()

    def __init__(self, index: int, name: str) -> None:
        """
        Initialize a new Zone.

        The zone self-registers in class-level dictionaries for later lookup.
        Duplicate indices or unique_names will trigger an assertion error.

        Args:
            index: Zone number (1-based, server indexing)
            name: Human-readable zone name

        Raises:
            AssertionError: If index or unique_name already exists
        """
        self.index = index
        self.name = name
        self.unique_name = f"zone_{self.index :03}"
        self._partition_mask: int = 0
        self._condition_mask: int = 0
        self._type_mask: int = 0
        self.is_updated: bool = False
        assert index not in self.zones_by_index, "Non-unique zone index"
        assert (
            self.unique_name not in self.zones_by_unique_name
        ), "Non-unique zone unique name"
        self.__class__.zones_by_index[index] = self
        self.__class__.zones_by_unique_name[self.unique_name] = self

    @property
    def is_bypassed(self) -> bool:
        """
        Check if the zone is currently bypassed.

        Returns:
            True if zone is bypassed, False otherwise
        """
        return bool(ZoneConditionFlags.Bypassed & self._condition_mask)

    @property
    def is_faulted(self) -> bool:
        """
        Check if the zone is currently faulted (triggered).

        Returns:
            True if zone is faulted, False otherwise
        """
        return bool(ZoneConditionFlags.Faulted & self._condition_mask)

    @property
    def is_trouble(self) -> bool:
        """
        Check if the zone has any trouble condition.

        Trouble includes: tampered, trouble flag, low battery, or supervision lost.

        Returns:
            True if any trouble condition exists, False otherwise
        """
        # Return True if tampered, trouble, low battery, or supervision lost
        return bool(
            ZoneConditionFlags.Tampered & self._condition_mask
            or ZoneConditionFlags.Trouble & self._condition_mask
            or ZoneConditionFlags.LowBattery & self._condition_mask
            or ZoneConditionFlags.SupervisionLost & self._condition_mask
        )

    def is_valid_partition(self, partition) -> bool:
        """
        Check if this zone belongs to the specified partition.

        Args:
            partition: Partition object to check membership

        Returns:
            True if zone is assigned to this partition, False otherwise
        """
        # Check if the bit for this partition is set in the partition mask for this zone
        return bool(self._partition_mask & (1 << (partition.index - 1)))

    def set_masks(
        self, partition_mask: int, type_mask: int, condition_mask: int
    ) -> None:
        """
        Update zone state masks from panel status message.

        Args:
            partition_mask: 8-bit mask indicating partition membership
            type_mask: 24-bit mask of zone type flags
            condition_mask: 16-bit mask of zone condition flags
        """
        self._partition_mask = partition_mask
        self._type_mask = type_mask
        self._condition_mask = condition_mask
        self.is_updated = True
        self.debug_zone_status()

    def debug_zone_status(self):
        """
        Log detailed zone status information at DEBUG level.

        Outputs zone name, type mask, and condition flags in binary format
        with human-readable flag names for all set bits.
        """
        if logger.level > logging.DEBUG:
            return
        logger.debug(f"Zone {self.index} - {self.name}")
        logger.debug(f"  Type mask: {self._type_mask:0>24b}")
        for flag in ZoneTypeFlags:
            if flag & self._type_mask:
                logger.debug(f"    {flag.name} is set")
        logger.debug(f"  Condition flags: {self._condition_mask:0>16b}")
        for flag in ZoneConditionFlags:
            if flag & self._condition_mask:
                logger.debug(f"    {flag.name} is set")
