from typing import Dict, Optional, ValuesView
from enum import IntEnum


class ZoneTypeFlags(IntEnum):
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
    zones_by_index: Dict[int, "Zone"] = {}
    zones_by_unique_name: Dict[str, "Zone"] = {}

    @classmethod
    def get_zone_by_index(cls, zone_id: int) -> Optional["Zone"]:
        return cls.zones_by_index.get(zone_id)

    @classmethod
    def get_zone_by_unique_name(cls, unique_name: str) -> Optional["Zone"]:
        return cls.zones_by_unique_name.get(unique_name)

    @classmethod
    def get_all_zones(cls) -> ValuesView["Zone"]:
        return cls.zones_by_index.values()

    def __init__(self, index: int, name: str) -> None:
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
        return bool(ZoneConditionFlags.Bypassed & self._condition_mask)

    @property
    def is_faulted(self) -> bool:
        return bool(ZoneConditionFlags.Faulted & self._condition_mask)

    @property
    def is_trouble(self) -> bool:
        # Return True if tampered, trouble, low battery, or supervision lost
        return bool(
            ZoneConditionFlags.Tampered & self._condition_mask
            or ZoneConditionFlags.Trouble & self._condition_mask
            or ZoneConditionFlags.LowBattery & self._condition_mask
            or ZoneConditionFlags.SupervisionLost & self._condition_mask
        )

    def is_valid_partition(self, partition) -> bool:
        # Check if the bit for this partition is set in the partition mask for this zone
        return bool(self._partition_mask & (1 << (partition.index - 1)))

    def set_masks(
        self, partition_mask: int, condition_mask: int, type_mask: int
    ) -> None:
        self._partition_mask = partition_mask
        self._condition_mask = condition_mask
        self._type_mask = type_mask
        self.is_updated = True
