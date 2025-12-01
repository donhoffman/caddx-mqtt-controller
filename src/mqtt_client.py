import time
from typing import List
import json
import logging
import paho.mqtt.client as mqtt

from partition import Partition
from zone import Zone

logger = logging.getLogger("app.mqtt_client")


class MQTTClient(object):
    def __init__(
        self,
        caddx_ctrl,
        host: str,
        port: int,
        user: str,
        password: str,
        topic_root: str,
        panel_unique_id: str,
        panel_name: str,
        _tls: bool = False,
        _tls_insecure: bool = False,
        version: str = "Unknown",
        timeout_seconds: int = 60,
        qos: int = 1,
    ):
        self.software_version = version
        self.qos = qos
        self.topic_root = topic_root
        self.panel_unique_id = panel_unique_id
        self.panel_name = panel_name
        self.topic_prefix_panel = (
            f"{self.topic_root}/alarm_control_panel/{self.panel_unique_id}"
        )
        self.command_topic_path_panel = f"{self.topic_prefix_panel}/+/set"
        self.state_topic_path_panel = f"{self.topic_prefix_panel}/+/state"
        self.topic_prefix_zones = (
            f"{self.topic_root}/binary_sensor/{self.panel_unique_id}"
        )
        self.state_topic_path_zones = f"{self.topic_prefix_zones}/+/state"
        self.availability_topic = f"{self.topic_prefix_panel}/availability"
        self.caddx_ctrl = caddx_ctrl
        self.timeout_seconds = timeout_seconds
        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        self.connected = False

        self.client.username_pw_set(user, password)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.client.reconnect_delay_set(self.timeout_seconds)

        # Set Last Will and Testament BEFORE connecting
        # This ensures the broker will publish "offline" if we disconnect unexpectedly
        self.client.will_set(self.availability_topic, "offline", qos=self.qos, retain=True)

        logger.info(f"Connecting to MQTT server at {host}:{port}.")

        try:
            self.client.connect(host, port, self.timeout_seconds)
            self.client.loop_start()
        except Exception as e:
            logger.debug(f"Failed to connect to MQTT broker at {host}: {str(e)}")
            raise e

    def on_connect(self, _client, _userdata, _flags, rc) -> None:
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT server.")

            # Publish offline status until panel sync completes
            # (publish_online() will be called after sync in caddx_controller.py)
            self.publish_offline()

            # Listen for commands
            self.client.subscribe(self.command_topic_path_panel)

            # Subscribe to HA MQTT integration status to detect HA restarts
            self.client.subscribe(f"{self.topic_root}/status")

        else:
            self.connected = False
            logger.debug(f"Failed to connect to MQTT server result code {rc}.")

    def on_message(self, _client, _userdata, msg) -> None:
        if not self.connected:
            return
        # Check for MQTT integration availability message
        topic_parts: List[str] = msg.topic.split("/")
        if (
            len(topic_parts) == 2
            and topic_parts[0] == self.topic_root
            and topic_parts[1] == "status"
        ):
            if msg.payload == b"online":
                logger.info("MQTT integration restarted. Re-synchronizing data.")
                self.publish_configs()
                self.publish_online()
                self.publish_partition_states()
            return
        # Check for command.
        if (
            (len(topic_parts) == 5)
            and (topic_parts[0] == self.topic_root)
            and (topic_parts[1] == "alarm_control_panel")
            and (topic_parts[2] == self.panel_unique_id)
            and (topic_parts[3].startswith("partition_"))
            and (topic_parts[4] == "set")
        ):
            partition_index = int(topic_parts[3].split("_")[1])
            partition = Partition.get_partition_by_index(partition_index)
            if partition is None:
                logger.error(
                    f"Got command for partition {partition_index} that is not configured."
                )
                return
            command = msg.payload.decode("utf-8")
            match command:
                case "ARM_AWAY":
                    self.caddx_ctrl.send_arm_away(partition)
                case "ARM_HOME":
                    self.caddx_ctrl.send_arm_home(partition)
                case "DISARM":
                    self.caddx_ctrl.send_disarm(partition)
                case _:
                    logger.error(f"Unknown command: {command}")

    def on_disconnect(self, _client, _userdata, _rc) -> None:
        self.connected = False

    def publish_online(self) -> None:
        self.client.publish(
            self.availability_topic, payload="online", qos=self.qos, retain=True
        )

    def publish_offline(self) -> None:
        self.client.publish(
            self.availability_topic, payload="offline", qos=self.qos, retain=True
        )

    def publish_configs(self) -> None:
        partitions = Partition.get_all_partitions()
        for partition in partitions:
            self.publish_partition_config(partition)

    def publish_partition_config(self, partition: Partition) -> None:
        partition_config = {
            "name": None,
            "device_class": "alarm_control_panel",
            "unique_id": f"{self.panel_unique_id}_{partition.unique_name}",
            "device": {
                "name": f"{self.panel_name} Partition {partition.index}",
                "identifiers": [f"{self.panel_unique_id}_{partition.unique_name}"],
                "manufacturer": "Caddx",
                "model": "NX8E",
            },
            "origin": {"name": "Caddx MQTT Controller", "sw_version": "1.0.0"},
            "supported_features": ["arm_home", "arm_away"],
            "optimistic": False,
            "code_arm_required": False,
            "code_disarm_required": False,
            "code_trigger_required": False,
            "~": f"{self.topic_prefix_panel}/{partition.unique_name}",
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "state_topic": "~/state",
            "command_topic": "~/set",
            "json_attributes_topic": "~/attributes",
            "retain": True,
        }
        config_topic = f"{self.topic_prefix_panel}/{partition.unique_name}/config"
        self.client.publish(
            config_topic, json.dumps(partition_config), qos=self.qos, retain=True
        )
        logger.debug(f"Published Partition {partition.index} config.")

    def publish_zone_config(self, zone: Zone) -> None:
        # The zone config defines three entities for the zone:
        # 1. A binary sensor for the zone's bypass status
        # 2. A binary sensor for the zone's fault status
        # 3. A binary sensor for the zone's trouble status
        zone_config_bypass = {
            "name": "Bypass",
            "device_class": "safety",
            "unique_id": f"{self.panel_unique_id}_{zone.unique_name}_bypass",
            "device": {
                "name": zone.name,
                "identifiers": [f"{self.panel_unique_id}_{zone.unique_name}"],
                "manufacturer": "Caddx",
                "model": "NX8E",
            },
            "origin": {"name": "Caddx MQTT Controller", "sw_version": "1.0.0"},
            "state_topic": f"{self.topic_prefix_zones}/{zone.unique_name}/state",
            "value_template": "{{ value_json.bypassed }}",
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "retain": True,
        }
        config_topic = f"{self.topic_prefix_zones}/{zone.unique_name}_bypass/config"
        self.client.publish(
            config_topic, json.dumps(zone_config_bypass), qos=self.qos, retain=True
        )
        zone_config_faulted = {
            "name": "Faulted",
            "device_class": "safety",
            "unique_id": f"{self.panel_unique_id}_{zone.unique_name}_faulted",
            "device": {
                "name": zone.name,
                "identifiers": [f"{self.panel_unique_id}_{zone.unique_name}"],
                "manufacturer": "Caddx",
                "model": "NX8E",
            },
            "origin": {"name": "Caddx MQTT Controller", "sw_version": "1.0.0"},
            "state_topic": f"{self.topic_prefix_zones}/{zone.unique_name}/state",
            "value_template": "{{ value_json.faulted }}",
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "retain": True,
        }
        config_topic = f"{self.topic_prefix_zones}/{zone.unique_name}_faulted/config"
        self.client.publish(
            config_topic, json.dumps(zone_config_faulted), qos=self.qos, retain=True
        )
        zone_config_trouble = {
            "name": "Trouble",
            "device_class": "problem",
            "unique_id": f"{self.panel_unique_id}_{zone.unique_name}_trouble",
            "device": {
                "name": zone.name,
                "identifiers": [f"{self.panel_unique_id}_{zone.unique_name}"],
                "manufacturer": "Caddx",
                "model": "NX8E",
            },
            "origin": {"name": "Caddx MQTT Controller", "sw_version": "1.0.0"},
            "state_topic": f"{self.topic_prefix_zones}/{zone.unique_name}/state",
            "value_template": "{{ value_json.trouble }}",
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "retain": True,
        }
        config_topic = f"{self.topic_prefix_zones}/{zone.unique_name}_trouble/config"
        self.client.publish(
            config_topic, json.dumps(zone_config_trouble), qos=self.qos, retain=True
        )
        logger.debug(f"Published Zone {zone.index} config.")

    def publish_zone_configs(self) -> None:
        zones = Zone.get_all_zones()
        for zone in zones:
            time.sleep(1)
            self.publish_zone_config(zone)

    def publish_zone_states(self) -> None:
        zones = Zone.get_all_zones()
        for zone in zones:
            time.sleep(1)
            self.publish_zone_state(zone)

    def publish_zone_state(self, zone: Zone) -> None:
        if not zone.is_updated:
            return
        state = {
            "bypassed": "ON" if zone.is_bypassed else "OFF",
            "faulted": "ON" if zone.is_faulted else "OFF",
            "trouble": "ON" if zone.is_trouble else "OFF",
        }
        state_topic = f"{self.topic_prefix_zones}/{zone.unique_name}/state"
        self.client.publish(state_topic, json.dumps(state), qos=self.qos, retain=True)
        zone.is_updated = False
        logger.debug(f"Published Zone {zone.index} state.")

    def publish_partition_states(self) -> None:
        partitions = Partition.get_all_partitions()
        for partition in partitions:
            self.publish_partition_state(partition)

    def publish_partition_state(self, partition: Partition) -> None:
        state = partition.state
        if state is not None:
            state_topic = f"{self.topic_prefix_panel}/{partition.unique_name}/state"
            self.client.publish(state_topic, state.value[0], qos=self.qos, retain=True)
        logger.debug(f"Published Partition {partition.index} state.")
