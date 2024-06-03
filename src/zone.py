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

    @classmethod
    def get_zone_type_flags(cls, mask: int) -> Set[model.ZoneTypeFlags]:
        type_flags = set()
        for flag in model.ZoneTypeFlags:
            if mask & flag.value:
                type_flags.add(flag)
        return type_flags

    @classmethod
    def get_zone_condition_flags(cls, mask: int) -> Set[model.ZoneConditionFlags]:
        condition_flags = set()
        for flag in model.ZoneConditionFlags:
            if mask & flag.value:
                condition_flags.add(flag)
        return condition_flags

    def __init__(self, index: int, name: str) -> None:
        self.index = index
        self.name = name
        self.unique_name = f"zone_{(self.index + 1):03}"
        self.condition_flags: Set[model.ZoneConditionFlags] = set()
        self.type_flags: Set[model.ZoneTypeFlags] = set()
        self.is_updated: bool = True
        assert index not in self.zones_by_index, "Non-unique zone index"
        self.__class__.zones_by_index[index] = self
        assert self.unique_name not in self.zones_by_unique_name, "Non-unique zone name"
        self.__class__.zones_by_unique_name[self.unique_name] = self

    @property
    def bypassed(self) -> bool:
        return (
            model.ZoneConditionFlags.Inhibited in self.condition_flags
            or model.ZoneConditionFlags.Bypassed in self.condition_flags
        )

    @bypassed.setter
    def bypassed(self, value: bool) -> None:
        if value:
            self.condition_flags.add(model.ZoneConditionFlags.Bypassed)
        else:
            self.condition_flags.discard(model.ZoneConditionFlags.Bypassed)
        self.is_updated = True

    @property
    def faulted(self) -> bool:
        return model.ZoneConditionFlags.Faulted in self.condition_flags

    @faulted.setter
    def faulted(self, value: bool) -> None:
        if value:
            self.condition_flags.add(model.ZoneConditionFlags.Faulted)
        else:
            self.condition_flags.discard(model.ZoneConditionFlags.Faulted)
        self.is_updated = True

    @property
    def trouble(self) -> bool:
        return (
            model.ZoneConditionFlags.Tampered in self.condition_flags
            or model.ZoneConditionFlags.Trouble in self.condition_flags
            or model.ZoneConditionFlags.LowBattery in self.condition_flags
            or model.ZoneConditionFlags.SupervisionLost in self.condition_flags
        )

    @trouble.setter
    def trouble(self, value: bool) -> None:
        if value:
            self.condition_flags.add(model.ZoneConditionFlags.Trouble)
        else:
            self.condition_flags.discard(model.ZoneConditionFlags.Trouble)
        self.is_updated = True
