import json
import logging
import paho.mqtt.client as mqtt

from partition import Partition

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
    ):
        self.software_version = version
        self.topic_root = topic_root
        self.panel_unique_id = panel_unique_id
        self.panel_name = panel_name
        self.topic_prefix = (
            f"{self.topic_root}/alarm_control_panel/{self.panel_unique_id}"
        )
        self.command_topic_path = f"{self.topic_prefix}/+/set"
        self.state_topic_path = f"{self.topic_prefix}/+/state"
        self.availability_topic = f"{self.topic_prefix}/availability"
        self.caddx_ctrl = caddx_ctrl
        self.timeout_seconds = timeout_seconds
        self.client = mqtt.Client()
        self.connected = False

        self.client.username_pw_set(user, password)
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        self.client.reconnect_delay_set(self.timeout_seconds)
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

            # Publish our initial availability to HA MQTT integration
            self.publish_offline()
            self.client.will_set(self.availability_topic, "offline", retain=True)

            # Listen for commands
            self.client.subscribe(self.command_topic_path)

            # Subscribe to HA MQTT integration status to detect HA restarts
            self.client.subscribe(f"{self.topic_root}/status")

        else:
            self.connected = False
            logger.debug(f"Failed to connect to MQTT server result code {rc}.")

    def on_message(self, _client, _userdata, _msg) -> None:
        if not self.connected:
            return

    def on_disconnect(self, _client, _userdata, _rc) -> None:
        self.connected = False

    def publish_online(self) -> None:
        self.client.publish(
            self.availability_topic, payload="online", qos=1, retain=True
        )

    def publish_offline(self) -> None:
        self.client.publish(
            self.availability_topic, payload="offline", qos=1, retain=True
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
            "~": f"{self.topic_prefix}/{partition.unique_name}",
            "availability_topic": self.availability_topic,
            "payload_available": "online",
            "payload_not_available": "offline",
            "state_topic": "~/state",
            "command_topic": "~/set",
            "json_attributes_topic": "~/attributes",
        }
        config_topic = f"{self.topic_prefix}/{partition.unique_name}/config"
        self.client.publish(config_topic, json.dumps(partition_config))

    def publish_partition_states(self) -> None:
        partitions = Partition.get_all_partitions()
        for partition in partitions:
            self.publish_partition_state(partition)

    def publish_partition_state(self, partition: Partition) -> None:
        state = partition.state
        if state is not None:
            state_topic = f"{self.topic_prefix}/{partition.unique_name}/state"
            self.client.publish(state_topic, state.value[0])
