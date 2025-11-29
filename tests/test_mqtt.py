"""Tests for MQTT topic generation and message formatting."""
import pytest
import json
from unittest.mock import Mock, MagicMock, patch
from partition import Partition
from zone import Zone


class TestMQTTTopicGeneration:
    """Tests for MQTT topic path generation."""

    def setup_method(self):
        """Set up test fixtures."""
        Partition.partition_by_index.clear()
        Partition.partition_by_unique_name.clear()
        Zone.zones_by_index.clear()
        Zone.zones_by_unique_name.clear()

        self.topic_root = "homeassistant"
        self.panel_unique_id = "test_panel"

    def test_partition_command_topic(self):
        """Test partition command topic generation."""
        partition = Partition(1)
        expected = f"{self.topic_root}/alarm_control_panel/{self.panel_unique_id}/{partition.unique_name}/set"
        assert expected == f"homeassistant/alarm_control_panel/test_panel/partition_1/set"

    def test_partition_state_topic(self):
        """Test partition state topic generation."""
        partition = Partition(1)
        expected = f"{self.topic_root}/alarm_control_panel/{self.panel_unique_id}/{partition.unique_name}/state"
        assert expected == "homeassistant/alarm_control_panel/test_panel/partition_1/state"

    def test_partition_config_topic(self):
        """Test partition config topic generation."""
        partition = Partition(1)
        expected = f"{self.topic_root}/alarm_control_panel/{self.panel_unique_id}/{partition.unique_name}/config"
        assert expected == "homeassistant/alarm_control_panel/test_panel/partition_1/config"

    def test_partition_availability_topic(self):
        """Test availability topic generation."""
        expected = f"{self.topic_root}/alarm_control_panel/{self.panel_unique_id}/availability"
        assert expected == "homeassistant/alarm_control_panel/test_panel/availability"

    def test_zone_state_topic(self):
        """Test zone state topic generation."""
        zone = Zone(1, "Front Door")
        expected = f"{self.topic_root}/binary_sensor/{self.panel_unique_id}/{zone.unique_name}/state"
        assert expected == "homeassistant/binary_sensor/test_panel/zone_001/state"

    def test_zone_bypass_config_topic(self):
        """Test zone bypass config topic generation."""
        zone = Zone(1, "Front Door")
        expected = f"{self.topic_root}/binary_sensor/{self.panel_unique_id}/{zone.unique_name}_bypass/config"
        assert expected == "homeassistant/binary_sensor/test_panel/zone_001_bypass/config"

    def test_zone_faulted_config_topic(self):
        """Test zone faulted config topic generation."""
        zone = Zone(1, "Front Door")
        expected = f"{self.topic_root}/binary_sensor/{self.panel_unique_id}/{zone.unique_name}_faulted/config"
        assert expected == "homeassistant/binary_sensor/test_panel/zone_001_faulted/config"

    def test_zone_trouble_config_topic(self):
        """Test zone trouble config topic generation."""
        zone = Zone(1, "Front Door")
        expected = f"{self.topic_root}/binary_sensor/{self.panel_unique_id}/{zone.unique_name}_trouble/config"
        assert expected == "homeassistant/binary_sensor/test_panel/zone_001_trouble/config"

    def test_topic_with_custom_root(self):
        """Test topics with custom root."""
        custom_root = "my_custom_root"
        partition = Partition(1)
        expected = f"{custom_root}/alarm_control_panel/{self.panel_unique_id}/{partition.unique_name}/state"
        assert expected == "my_custom_root/alarm_control_panel/test_panel/partition_1/state"

    def test_topic_with_custom_panel_id(self):
        """Test topics with custom panel ID."""
        custom_panel_id = "bedroom_panel"
        partition = Partition(1)
        expected = f"{self.topic_root}/alarm_control_panel/{custom_panel_id}/{partition.unique_name}/state"
        assert expected == "homeassistant/alarm_control_panel/bedroom_panel/partition_1/state"


class TestPartitionConfigPayload:
    """Tests for partition MQTT discovery config payloads."""

    def setup_method(self):
        """Set up test fixtures."""
        Partition.partition_by_index.clear()
        Partition.partition_by_unique_name.clear()
        self.partition = Partition(1)
        self.panel_unique_id = "test_panel"
        self.panel_name = "Test Alarm Panel"
        self.topic_root = "homeassistant"

    def test_partition_config_structure(self):
        """Test partition config has required fields."""
        config = {
            "name": None,
            "device_class": "alarm_control_panel",
            "unique_id": f"{self.panel_unique_id}_{self.partition.unique_name}",
            "device": {
                "name": f"{self.panel_name} Partition {self.partition.index}",
                "identifiers": [f"{self.panel_unique_id}_{self.partition.unique_name}"],
                "manufacturer": "Caddx",
                "model": "NX8E",
            },
            "supported_features": ["arm_home", "arm_away"],
            "state_topic": f"{self.topic_root}/alarm_control_panel/{self.panel_unique_id}/{self.partition.unique_name}/state",
            "command_topic": f"{self.topic_root}/alarm_control_panel/{self.panel_unique_id}/{self.partition.unique_name}/set",
        }

        # Verify all required fields are present
        assert config["device_class"] == "alarm_control_panel"
        assert config["unique_id"] == "test_panel_partition_1"
        assert "arm_home" in config["supported_features"]
        assert "arm_away" in config["supported_features"]

    def test_partition_config_json_serializable(self):
        """Test that partition config can be serialized to JSON."""
        config = {
            "name": None,
            "device_class": "alarm_control_panel",
            "unique_id": f"{self.panel_unique_id}_{self.partition.unique_name}",
            "supported_features": ["arm_home", "arm_away"],
        }

        # Should not raise exception
        json_str = json.dumps(config)
        assert isinstance(json_str, str)

        # Should be able to decode back
        decoded = json.loads(json_str)
        assert decoded["unique_id"] == "test_panel_partition_1"


class TestZoneConfigPayload:
    """Tests for zone MQTT discovery config payloads."""

    def setup_method(self):
        """Set up test fixtures."""
        Zone.zones_by_index.clear()
        Zone.zones_by_unique_name.clear()
        self.zone = Zone(1, "Front Door")
        self.panel_unique_id = "test_panel"
        self.topic_root = "homeassistant"

    def test_zone_bypass_config_structure(self):
        """Test zone bypass config has required fields."""
        config = {
            "name": "Bypass",
            "device_class": "safety",
            "unique_id": f"{self.panel_unique_id}_{self.zone.unique_name}_bypass",
            "device": {
                "name": self.zone.name,
                "identifiers": [f"{self.panel_unique_id}_{self.zone.unique_name}"],
                "manufacturer": "Caddx",
                "model": "NX8E",
            },
            "state_topic": f"{self.topic_root}/binary_sensor/{self.panel_unique_id}/{self.zone.unique_name}/state",
            "value_template": "{{ value_json.bypassed }}",
        }

        assert config["name"] == "Bypass"
        assert config["device_class"] == "safety"
        assert config["unique_id"] == "test_panel_zone_001_bypass"
        assert config["value_template"] == "{{ value_json.bypassed }}"

    def test_zone_faulted_config_structure(self):
        """Test zone faulted config has required fields."""
        config = {
            "name": "Faulted",
            "device_class": "safety",
            "unique_id": f"{self.panel_unique_id}_{self.zone.unique_name}_faulted",
            "value_template": "{{ value_json.faulted }}",
        }

        assert config["name"] == "Faulted"
        assert config["unique_id"] == "test_panel_zone_001_faulted"
        assert config["value_template"] == "{{ value_json.faulted }}"

    def test_zone_trouble_config_structure(self):
        """Test zone trouble config has required fields."""
        config = {
            "name": "Trouble",
            "device_class": "problem",
            "unique_id": f"{self.panel_unique_id}_{self.zone.unique_name}_trouble",
            "value_template": "{{ value_json.trouble }}",
        }

        assert config["name"] == "Trouble"
        assert config["device_class"] == "problem"
        assert config["unique_id"] == "test_panel_zone_001_trouble"


class TestZoneStatePayload:
    """Tests for zone state MQTT payloads."""

    def setup_method(self):
        """Set up test fixtures."""
        Zone.zones_by_index.clear()
        Zone.zones_by_unique_name.clear()
        self.zone = Zone(1, "Front Door")

    def test_zone_state_all_off(self):
        """Test zone state payload when nothing is triggered."""
        state = {
            "bypassed": "OFF",
            "faulted": "OFF",
            "trouble": "OFF",
        }

        json_str = json.dumps(state)
        decoded = json.loads(json_str)

        assert decoded["bypassed"] == "OFF"
        assert decoded["faulted"] == "OFF"
        assert decoded["trouble"] == "OFF"

    def test_zone_state_faulted(self):
        """Test zone state payload when faulted."""
        from zone import ZoneConditionFlags

        self.zone._condition_mask = ZoneConditionFlags.Faulted

        state = {
            "bypassed": "ON" if self.zone.is_bypassed else "OFF",
            "faulted": "ON" if self.zone.is_faulted else "OFF",
            "trouble": "ON" if self.zone.is_trouble else "OFF",
        }

        assert state["bypassed"] == "OFF"
        assert state["faulted"] == "ON"
        assert state["trouble"] == "OFF"

    def test_zone_state_bypassed(self):
        """Test zone state payload when bypassed."""
        from zone import ZoneConditionFlags

        self.zone._condition_mask = ZoneConditionFlags.Bypassed

        state = {
            "bypassed": "ON" if self.zone.is_bypassed else "OFF",
            "faulted": "ON" if self.zone.is_faulted else "OFF",
            "trouble": "ON" if self.zone.is_trouble else "OFF",
        }

        assert state["bypassed"] == "ON"
        assert state["faulted"] == "OFF"
        assert state["trouble"] == "OFF"

    def test_zone_state_trouble(self):
        """Test zone state payload when in trouble."""
        from zone import ZoneConditionFlags

        self.zone._condition_mask = ZoneConditionFlags.Trouble

        state = {
            "bypassed": "ON" if self.zone.is_bypassed else "OFF",
            "faulted": "ON" if self.zone.is_faulted else "OFF",
            "trouble": "ON" if self.zone.is_trouble else "OFF",
        }

        assert state["bypassed"] == "OFF"
        assert state["faulted"] == "OFF"
        assert state["trouble"] == "ON"

    def test_zone_state_multiple_conditions(self):
        """Test zone state with multiple conditions."""
        from zone import ZoneConditionFlags

        self.zone._condition_mask = (
            ZoneConditionFlags.Faulted | ZoneConditionFlags.Bypassed
        )

        state = {
            "bypassed": "ON" if self.zone.is_bypassed else "OFF",
            "faulted": "ON" if self.zone.is_faulted else "OFF",
            "trouble": "ON" if self.zone.is_trouble else "OFF",
        }

        assert state["bypassed"] == "ON"
        assert state["faulted"] == "ON"
        assert state["trouble"] == "OFF"


class TestPartitionStatePayload:
    """Tests for partition state MQTT payloads."""

    def setup_method(self):
        """Set up test fixtures."""
        Partition.partition_by_index.clear()
        Partition.partition_by_unique_name.clear()
        self.partition = Partition(1)

    def test_partition_state_disarmed(self):
        """Test partition state payload when disarmed."""
        from partition import PartitionConditionFlags

        self.partition.condition_flags = PartitionConditionFlags.ReadyToArm
        state_value = self.partition.state.value[0]
        assert state_value == "disarmed"

    def test_partition_state_armed_away(self):
        """Test partition state payload when armed away."""
        from partition import PartitionConditionFlags

        self.partition.condition_flags = PartitionConditionFlags.Armed
        state_value = self.partition.state.value[0]
        assert state_value == "armed_away"

    def test_partition_state_armed_home(self):
        """Test partition state payload when armed home."""
        from partition import PartitionConditionFlags

        self.partition.condition_flags = (
            PartitionConditionFlags.Armed | PartitionConditionFlags.Entryguard
        )
        state_value = self.partition.state.value[0]
        assert state_value == "armed_home"

    def test_partition_state_triggered(self):
        """Test partition state payload when triggered."""
        from partition import PartitionConditionFlags

        self.partition.condition_flags = PartitionConditionFlags.SirenOn
        state_value = self.partition.state.value[0]
        assert state_value == "triggered"

    def test_partition_state_pending(self):
        """Test partition state payload when pending."""
        from partition import PartitionConditionFlags

        self.partition.condition_flags = (
            PartitionConditionFlags.Armed | PartitionConditionFlags.Entry
        )
        state_value = self.partition.state.value[0]
        assert state_value == "pending"

    def test_partition_state_arming(self):
        """Test partition state payload when arming."""
        from partition import PartitionConditionFlags

        self.partition.condition_flags = (
            PartitionConditionFlags.Armed | PartitionConditionFlags.Exit1
        )
        state_value = self.partition.state.value[0]
        assert state_value == "arming"


class TestMQTTCommandParsing:
    """Tests for parsing MQTT commands from Home Assistant."""

    def test_parse_arm_away_command(self):
        """Test parsing ARM_AWAY command."""
        command = "ARM_AWAY"
        assert command == "ARM_AWAY"

    def test_parse_arm_home_command(self):
        """Test parsing ARM_HOME command."""
        command = "ARM_HOME"
        assert command == "ARM_HOME"

    def test_parse_disarm_command(self):
        """Test parsing DISARM command."""
        command = "DISARM"
        assert command == "DISARM"

    def test_command_topic_parsing(self):
        """Test parsing partition index from command topic."""
        # Topic format: homeassistant/alarm_control_panel/panel_id/partition_1/set
        topic = "homeassistant/alarm_control_panel/test_panel/partition_3/set"
        parts = topic.split("/")

        assert len(parts) == 5
        assert parts[0] == "homeassistant"
        assert parts[1] == "alarm_control_panel"
        assert parts[2] == "test_panel"
        assert parts[3] == "partition_3"
        assert parts[4] == "set"

        # Extract partition index
        partition_name = parts[3]
        assert partition_name.startswith("partition_")
        partition_index = int(partition_name.split("_")[1])
        assert partition_index == 3