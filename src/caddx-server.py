from typing import Final
import os
import signal
import sys
import argparse

# import yaml
import logging

from caddx_controller import CaddxController

VERSION: Final = "1.0.0"
DEFAULT_MQTT_PORT: Final = 1883
LOG_FORMAT: Final = "%(asctime)s - %(module)s - %(levelname)s - %(message)s"


def main() -> int:
    mqtt = None

    # Setup for exit
    def exit_handler(_sig, _frame):
        if mqtt is not None:
            mqtt.publish_offline()
        sys.exit(0)

    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGTERM, exit_handler)

    # Gather the arguments from command line or environment.
    parser = argparse.ArgumentParser(description="Caddx MQTT Server")
    parser.add_argument(
        "--log-level",
        type=str,
        help="Logging level",
        default=os.getenv("LOG_LEVEL", "INFO"),
    )
    parser.add_argument(
        "--serial", type=str, help="Serial port", default=os.getenv("SERIAL", None)
    )
    parser.add_argument(
        "--baud", type=str, help="Serial baud rate", default=os.getenv("BAUD", 38400)
    )
    parser.add_argument(
        "--max-zones", type=int, help="Max zones", default=os.getenv("MAX_ZONES", 8)
    )
    parser.add_argument(
        "--mqtt-port",
        type=int,
        help="MQTT port number",
        default=os.getenv("MQTT_PORT", DEFAULT_MQTT_PORT),
    )
    parser.add_argument(
        "--mqtt-user",
        type=str,
        help="MQTT user name",
        default=os.getenv("MQTT_USER", None),
    )
    parser.add_argument(
        "--mqtt-password",
        type=str,
        help="MQTT password",
        default=os.getenv("MQTT_PASSWORD", None),
    )
    parser.add_argument(
        "--mqtt-topic-root",
        type=str,
        help="Root topic for MQTT Client publishing",
        default=os.getenv("TOPIC_ROOT", "homeassistant"),
    )
    parser.add_argument(
        "--entity-root",
        type=str,
        help="Root entity",
        default=os.getenv("ENTITY_ROOT", None),
    )
    args = parser.parse_args()

    logging.basicConfig(format=LOG_FORMAT, level=args.log_level)
    logger = logging.getLogger(__name__)
    logger.info("Starting Caddx MQTT Server")

    # Check for required arguments
    if args.entity_root is None:
        logging.error(
            "Argument --entity-root or environment variable ENTITY_ROOT is required"
        )
        return 1
    if args.serial is None:
        logging.error("Argument --serial or environment variable SERIAL is required")
        return 1

    # Initialize the controller
    try:
        controller = CaddxController(args.serial, args.baud, args.max_zones)
    except Exception as e:
        logger.error(f"Failed to initialize Caddx MQTT Controller: {e}")
        return 1

    # ToDo: Initialize the MQTT client

    # Run the controller loop
    code = controller.control_loop(None)
    return code


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
