from typing import Set, Dict, Optional
import model


class Partition(object):
    partition_by_index: Dict[int, "Partition"] = {}
    partition_by_unique_name: Dict[str, "Partition"] = {}

    @classmethod
    def get_partition_by_index(cls, index: int) -> Optional["Partition"]:
        return cls.partition_by_index.get(index)

    @classmethod
    def get_partition_by_unique_name(cls, unique_name: str) -> Optional["Partition"]:
        return cls.partition_by_unique_name.get(unique_name)

    @classmethod
    def get_partition_condition_flags(
        cls, mask: int
    ) -> Set[model.PartitionConditionFlags]:
        condition_flags = set()
        for flag in model.PartitionConditionFlags:
            if mask & flag.value:
                condition_flags.add(flag)
        return condition_flags

    def __init__(self, index: int, unique_name: str):
        self.index = index
        self.unique_name = unique_name
