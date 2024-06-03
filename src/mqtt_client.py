from typing import List, Optional
import json
import logging
import paho.mqtt.client as mqtt

# from zones import zones_by_index

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
        panel_id: str,
        _tls: bool = False,
        _tls_insecure: bool = False,
        version: str = "Unknown",
        timeout_seconds: int = 60,
    ):
        self.software_version = version
        self.topic_root = topic_root
        self.panel_id = panel_id
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

    def on_connect(self, client, _userdata, _flags, rc) -> None:
        if rc == 0:
            self.connected = True
            logger.debug("Connected to MQTT server.")

            # Mark device as offline until data is synced and published

        else:
            self.connected = False
            logger.debug(f"Failed to connect to MQTT server result code {rc}.")

    def on_message(self, _client, _userdata, msg) -> None:
        if not self.connected:
            return

    def on_disconnect(self, _client, _userdata, _rc) -> None:
        self.connected = False
