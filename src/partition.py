from typing import Dict, Optional, ValuesView, Callable
from enum import Enum

import model


class Partition(object):
    class State(Enum):
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
        return cls.partition_by_index.get(index)

    @classmethod
    def get_partition_by_unique_name(cls, unique_name: str) -> Optional["Partition"]:
        return cls.partition_by_unique_name.get(unique_name)

    @classmethod
    def get_all_partitions(cls) -> ValuesView["Partition"]:
        return cls.partition_by_index.values()

    def __init__(self, index: int):
        self.index = index
        assert 1 <= index <= 8
        self.unique_name = f"partition_{self.index}"
        assert index not in self.partition_by_index, "Non-unique partition index"
        self.__class__.partition_by_index[index] = self
        self.__class__.partition_by_unique_name[self.unique_name] = self
        self.condition_flags: Optional[int] = None

    @property
    def state(self) -> Optional["Partition.State"]:
        if self.condition_flags is None:
            return None
        if (self.condition_flags & model.PartitionConditionFlags.SirenOn) or (
            self.condition_flags & model.PartitionConditionFlags.SteadySirenOn
        ):
            return Partition.State.TRIGGERED
        if self.condition_flags & model.PartitionConditionFlags.Armed:
            if (self.condition_flags & model.PartitionConditionFlags.Exit1) or (
                self.condition_flags & model.PartitionConditionFlags.Exit2
            ):
                return Partition.State.ARMING
            if self.condition_flags & model.PartitionConditionFlags.Entry:
                return Partition.State.PENDING
            if self.condition_flags & model.PartitionConditionFlags.Entryguard:
                return Partition.State.ARMED_HOME
            else:
                return Partition.State.ARMED_AWAY
        if (self.condition_flags & model.PartitionConditionFlags.ReadyToArm) or (
            self.condition_flags & model.PartitionConditionFlags.ReadyToForceArm
        ):
            return Partition.State.DISARMED

    def log_condition(self, logger: Callable[[str], None]) -> None:
        logger(f"Partition {self.index} raw value: {self.condition_flags:0>12x}")
        log_entry = f"Partition {self.index} conditions: "
        for flag in model.PartitionConditionFlags:
            if flag & self.condition_flags:
                log_entry += f"{flag.name} "
        logger(log_entry)
