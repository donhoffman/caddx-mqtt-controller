import time
from typing import List
import json
import logging
import paho.mqtt.client as mqtt

from partition import Partition
from zone import Zone

logger = logging.getLogger("app.mqtt_client")


def sanitize_mqtt_identifier(value: str) -> str:
    """
    Sanitize a string for use in MQTT topics and identifiers.

    Replaces special characters that could break MQTT topic structure
    with underscores. MQTT wildcards (#, +), hierarchy separator (/),
    and whitespace are replaced to ensure valid topic paths.

    Args:
        value: The string to sanitize

    Returns:
        Sanitized string with only alphanumeric, underscore, and dash characters
    """
    result = ""
    for char in value:
        if char.isalnum() or char in ("_", "-"):
            result += char
        else:
            result += "_"
    return result


class MQTTClient(object):
    """
    MQTT client for publishing Caddx alarm panel state to Home Assistant.

    Implements Home Assistant MQTT Discovery protocol for alarm panels and zones.
    Manages connection to MQTT broker, publishes device configs and states, and
    listens for arm/disarm commands from Home Assistant.

    Attributes:
        software_version: Version string for MQTT discovery device info
        qos: MQTT Quality of Service level (0, 1, or 2)
        panel_unique_id: Sanitized unique identifier for the panel
        panel_name: Human-readable panel name
        connected: True when connected to MQTT broker
    """
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
        """
        Initialize MQTT client and connect to broker.

        Args:
            caddx_ctrl: CaddxController instance for sending commands
            host: MQTT broker hostname or IP
            port: MQTT broker port
            user: MQTT username
            password: MQTT password
            topic_root: Root topic for all messages (default: "homeassistant")
            panel_unique_id: Unique identifier for panel (sanitized automatically)
            panel_name: Human-readable panel name
            _tls: TLS encryption (not implemented)
            _tls_insecure: Allow insecure TLS (not implemented)
            version: Software version for discovery
            timeout_seconds: Connection timeout in seconds
            qos: MQTT QoS level (0, 1, or 2)

        Raises:
            Exception: If connection to MQTT broker fails
        """
        self.software_version = version
        self.qos = qos
        self.topic_root = topic_root

        # Sanitize panel_unique_id to ensure valid MQTT topic structure
        # (panel_name is only used for display and doesn't need sanitization)
        sanitized_id = sanitize_mqtt_identifier(panel_unique_id)
        if sanitized_id != panel_unique_id:
            logger.warning(
                f"Panel unique ID sanitized from '{panel_unique_id}' to '{sanitized_id}' "
                "to ensure valid MQTT topic structure (alphanumeric, underscore, and dash only)"
            )
        self.panel_unique_id = sanitized_id
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
        self.client.will_set(
            self.availability_topic, "offline", qos=self.qos, retain=True
        )

        logger.info(f"Connecting to MQTT server at {host}:{port}.")

        try:
            self.client.connect(host, port, self.timeout_seconds)
            self.client.loop_start()
        except Exception as e:
            logger.debug(f"Failed to connect to MQTT broker at {host}: {str(e)}")
            raise e

    def on_connect(self, _client, _userdata, _flags, rc) -> None:
        """
        Handle MQTT broker connection initialization.

        Called by paho-mqtt when connection succeeds or fails. On success,
        subscribes to command topics and publishes initial offline availability.

        Args:
            _client: MQTT client instance (unused)
            _userdata: User data (unused)
            _flags: Connection flags (unused)
            rc: Result code (0 = success)
        """
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
        """
        Handle incoming MQTT messages.

        Processes two types of messages:
        1. Home Assistant status ("homeassistant/status") - triggers re-sync on HA restart
        2. Alarm commands ("<topic_root>/alarm_control_panel/<panel_id>/<partition>/set")
           - ARM_AWAY, ARM_HOME, DISARM

        Args:
            _client: MQTT client instance (unused)
            _userdata: User data (unused)
            msg: MQTT message with topic and payload
        """
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
        """
        Handle MQTT broker disconnection.

        Called by paho-mqtt when connection is lost. Sets connected flag to False.
        Automatic reconnection is handled by paho-mqtt background thread.

        Args:
            _client: MQTT client instance (unused)
            _userdata: User data (unused)
            _rc: Result code (unused)
        """
        self.connected = False

    def publish_online(self) -> None:
        """
        Publish online availability status to MQTT.

        Should be called after panel sync completes. Updates all Home Assistant
        entities to show as available.
        """
        self.client.publish(
            self.availability_topic, payload="online", qos=self.qos, retain=True
        )

    def publish_offline(self) -> None:
        """
        Publish offline availability status to MQTT.

        Called during startup and shutdown. Updates all Home Assistant entities
        to show as unavailable.
        """
        self.client.publish(
            self.availability_topic, payload="offline", qos=self.qos, retain=True
        )

    def publish_configs(self) -> None:
        """
        Publish all partition MQTT discovery configs.

        Iterates through all partitions and publishes discovery config for each.
        Should be called after panel sync or on Home Assistant restart.
        """
        partitions = Partition.get_all_partitions()
        for partition in partitions:
            self.publish_partition_config(partition)

    def publish_partition_config(self, partition: Partition) -> None:
        """
        Publish MQTT discovery config for a partition.

        Creates Home Assistant alarm_control_panel entity with ARM_HOME and
        ARM_AWAY capabilities. Config includes device info, state/command topics,
        and availability.

        Args:
            partition: Partition to publish config for
        """
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
        """
        Publish MQTT discovery configs for a zone.

        Creates three Home Assistant binary_sensor entities per zone:
        1. Bypass status sensor
        2. Fault status sensor
        3. Trouble status sensor

        Each sensor shares the same zone device in Home Assistant.

        Args:
            zone: Zone to publish configs for
        """
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
        """
        Publish MQTT discovery configs for all zones.

        Includes 1-second delay between zones to prevent MQTT broker overload.
        Should be called after panel sync completes.
        """
        zones = Zone.get_all_zones()
        for zone in zones:
            time.sleep(1)
            self.publish_zone_config(zone)

    def publish_zone_states(self) -> None:
        """
        Publish state updates for all zones.

        Includes 1-second delay between zones to prevent MQTT broker overload.
        Should be called after panel sync or periodically.
        """
        zones = Zone.get_all_zones()
        for zone in zones:
            time.sleep(1)
            self.publish_zone_state(zone)

    def publish_zone_state(self, zone: Zone) -> None:
        """
        Publish state update for a single zone.

        Publishes JSON payload with bypassed, faulted, and trouble status.
        Only publishes if zone has been updated since last publish. Clears
        the is_updated flag after publishing.

        Args:
            zone: Zone to publish state for
        """
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
        """
        Publish state updates for all partitions.

        Should be called after panel sync or when partition states change.
        """
        partitions = Partition.get_all_partitions()
        for partition in partitions:
            self.publish_partition_state(partition)

    def publish_partition_state(self, partition: Partition) -> None:
        """
        Publish state update for a single partition.

        Publishes alarm state (disarmed, armed_away, armed_home, triggered, etc.)
        to Home Assistant. Only publishes if partition state is known.

        Args:
            partition: Partition to publish state for
        """
        state = partition.state
        if state is not None:
            state_topic = f"{self.topic_prefix_panel}/{partition.unique_name}/state"
            self.client.publish(state_topic, state.value[0], qos=self.qos, retain=True)
        logger.debug(f"Published Partition {partition.index} state.")
