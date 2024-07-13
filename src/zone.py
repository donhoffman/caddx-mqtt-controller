from typing import Set, Dict, Optional
import model


class Zone(object):
    zones_by_index: Dict[int, "Zone"] = {}
    zones_by_unique_name: Dict[str, "Zone"] = {}

    @classmethod
    def get_zone_by_index(cls, zone_id: int) -> Optional["Zone"]:
        return cls.zones_by_index.get(zone_id)

    @classmethod
    def get_zone_by_unique_name(cls, unique_name: str) -> Optional["Zone"]:
        return cls.zones_by_unique_name.get(unique_name)

    def __init__(self, index: int, name: str) -> None:
        self.index = index
        self.name = name
        self.unique_name = f"zone_{(self.index + 1):03}"
        self._partition_mask: int = 0
        self._condition_mask: int = 0
        self._type_mask: int = 0
        self._condition_flags: Set[model.ZoneConditionFlags] = set()
        self._type_flags: Set[model.ZoneTypeFlags] = set()
        self.is_updated: bool = True
        assert index not in self.zones_by_index, "Non-unique zone index"
        self.__class__.zones_by_index[index] = self
        assert (
            self.unique_name not in self.zones_by_unique_name
        ), "Non-unique unique zone name"
        self.__class__.zones_by_unique_name[self.unique_name] = self

    @property
    def bypassed(self) -> bool:
        return (
            model.ZoneConditionFlags.Inhibited in self._condition_flags
            or model.ZoneConditionFlags.Bypassed in self._condition_flags
        )

    @property
    def faulted(self) -> bool:
        return model.ZoneConditionFlags.Faulted in self._condition_flags

    @property
    def trouble(self) -> bool:
        return (
            model.ZoneConditionFlags.Tampered in self._condition_flags
            or model.ZoneConditionFlags.Trouble in self._condition_flags
            or model.ZoneConditionFlags.LowBattery in self._condition_flags
            or model.ZoneConditionFlags.SupervisionLost in self._condition_flags
        )

    @property
    def condition_mask(self) -> int:
        return self._condition_mask

    @condition_mask.setter
    def condition_mask(self, value: int) -> None:
        self._condition_mask = value
        self._condition_flags = set()
        for flag in model.ZoneConditionFlags:
            if value & flag.value:
                self._condition_flags.add(flag)

    @property
    def type_mask(self) -> int:
        return self._type_mask

    @type_mask.setter
    def type_mask(self, value: int) -> None:
        self._type_mask = value
        self._type_flags = set()
        for flag in model.ZoneTypeFlags:
            if value & flag.value:
                self._type_flags.add(flag)
