from typing import Optional
import logging
import serial
import queue
import time

from mqtt_client import MQTTClient
import model
from zone import Zone

logger = logging.getLogger("app.caddx_controller")


def get_nth_bit(num, n):
    return (num >> n) & 1


class StopThread(Exception):
    pass


class ControllerError(Exception):
    pass


class CaddxController:
    def __init__(self, serial_path: str, baud_rate: int, number_zones: int) -> None:
        self.serial_path = serial_path
        self.number_zones = number_zones
        self.mqtt_client: Optional[MQTTClient] = None
        self._command_queue = None
        self.conn = None
        self.panel_synced = False
        self.read_timeout = 2.0
        self.sleep_between_polls = 0.05
        self.conn = serial.Serial(serial_path, baudrate=baud_rate, timeout=1)
        logger.info(f"Opened serial connection at '{serial_path}'. Mode is binary")

    def control_loop(self, mqtt_client: Optional[MQTTClient]) -> int:
        logger.debug("Starting controller run loop.")
        self.mqtt_client = mqtt_client
        self._command_queue = queue.Queue()
        self.conn.reset_input_buffer()
        rc = 0

        if mqtt_client and not mqtt_client.connected:
            logger.error("Run loop started with no MQTT connection.")
            self.conn.close()
            self.conn = None
            return 1

        self._queue_db_sync()
        try:
            while True:
                # Next statement blocks until all commands and associated responses have been cleared.
                self._process_command_queue()
                time.sleep(self.sleep_between_polls)
                received_message = self._read_message(wait=False)
                if received_message is not None:
                    logger.debug(
                        f"Received transition or broadcast message: {received_message}"
                    )
                    self._process_transition_message(received_message)
        except KeyboardInterrupt:
            logger.debug("Received keyboard interrupt. Normal stop")
        except StopThread:
            logger.debug("Normal stop.")
        except Exception as e:
            logger.error(f"Caddx controller received exception: {e}")
            rc = 1
        finally:
            self.conn.close()
            self.conn = None
            while not self._command_queue.empty():
                logger.debug("Shutdown: Discarding message from _command_queue.")
                self._command_queue.get_nowait()
                self._command_queue.task_done()
            self._command_queue = None
        logger.debug("Exiting controller run loop.")
        return rc

    def _read_message(self, wait: bool = True) -> Optional[bytearray]:
        if not self.conn.is_open:
            logger.error("Call to _read_message with closed serial connection.")
            return None
        if not wait and not self.conn.in_waiting:
            return None
        start_character = self.conn.read(1)
        if start_character != b"\x7e":
            logger.error("Invalid or missing start character.")
            self.conn.reset_input_buffer()
            return None
        message_length_byte = self.conn.read(1)
        if not message_length_byte:
            logger.error("Invalid or missing message length.")
            self.conn.reset_input_buffer()
            return None
        message_data = bytearray()
        message_data.extend(message_length_byte)
        message_length = int.from_bytes(message_length_byte, "little")
        for i in range(message_length + 2):  # +2 for checksum
            next_byte = self.conn.read(1)
            if next_byte == b"\x7d":
                next_byte = self.conn.read(1)
                if next_byte == b"\x5e":
                    next_byte = b"\x7e"
                elif next_byte == b"\x5d":
                    next_byte = b"\x7d"
                else:
                    logger.error(
                        "Invalid escape sequence. Flushing and discarding buffer."
                    )
                    self.conn.reset_input_buffer()
                    return None
            message_data.extend(next_byte)

        if (
            len(message_data) != message_length + 3
        ):  # +3 for length and checksum. Both will be stripped off later.
            logger.error("Message data wrong length. Flushing and discarding buffer.")
            self.conn.reset_input_buffer()
            return None
        logger.debug(f"Input message type: {(message_data[1] & 0b00111111):02x}")
        logger.debug(f"Input message data: {message_data.hex()}")
        # Check the checksum
        offered_checksum = int.from_bytes(message_data[-2:], byteorder="little")
        del message_data[-2:]  # Strip off the checksum
        calculated_checksum = self._calculate_fletcher16(message_data)
        if offered_checksum != calculated_checksum:
            logger.error("Invalid checksum. Discarding message.")
            return None
        del message_data[0]  # Strip off the length byte
        return message_data

    @staticmethod
    def _calculate_fletcher16(data: bytearray) -> int:
        """
        Calculate the Fletcher-16 checksum for the given data.
        :param data: The data to be checksummed.
        :return: 16-bit checksum.
        """
        sum1 = int(0)
        sum2 = int(0)
        for byte in data:
            sum1 = (sum1 + byte) % 255
            sum2 = (sum2 + sum1) % 255
        return (sum2 << 8) | sum1

    def _process_transition_message(self, received_message: bytearray) -> None:
        message_type = received_message[0]
        ack_requested = bool(message_type & 0x80)
        message_type &= ~0xC0
        if message_type not in model.MessageValidLength:
            logger.error(f"Invalid message type: {message_type}")
            return
        if len(received_message) != model.MessageValidLength[message_type]:
            logger.error("Invalid message length for type. Discarding message.")
            return
        match message_type:
            case model.MessageType.InterfaceConfigRsp:
                self._process_interface_config_rsp(received_message)
            case model.MessageType.ZoneStatusRsp:
                self._process_zone_status_rsp(received_message)
            case model.MessageType.ZonesSnapshotRsp:
                self._process_zones_snapshot_rsp(received_message)
            case model.MessageType.PartitionStatusRsp:
                self._process_partition_status_rsp(received_message)
            case model.MessageType.PartitionSnapshotRsp:
                self._process_partition_snapshot_rsp(received_message)
            case model.MessageType.SystemStatusRsp:
                self._process_system_status_rsp(received_message)
            case model.MessageType.LogEventInd:
                self._process_log_event_ind(received_message)
            case model.MessageType.KeypadButtonInd:
                self._process_keypad_button_ind(received_message)
            case _:  # Message type not supported for broadcast or transition messages
                logger.error(
                    f"Received message with indeterminate disposition: {message_type}"
                )
                logger.error("This is probably a bug in the server. Please report it.")

        if ack_requested:  # OK to ACK even unexpected messages types
            self._send_direct_ack()
        return

    @staticmethod
    def _process_interface_config_rsp(message: bytearray) -> None:
        panel_firmware = message[1:5].decode("ascii").rstrip()
        logger.debug(f"Panel firmware: {panel_firmware}")

        transition_message_flags = (
            int.from_bytes(message[5:7], byteorder="little") & 0xFF_FF
        )
        request_command_flags = (
            int.from_bytes(message[7:11], byteorder="little") & 0xFF_FF_FF_FF
        )

        # Log enabled transition-based broadcast messages
        logger.debug("Transition-based broadcast messages enabled:")
        for message_type in model.TransitionMessageFlags:
            logger.debug(
                f"  - {message_type.name}: {bool(transition_message_flags & message_type)}"
            )

        # Log enabled command/request messages
        logger.debug("Command/request messages enabled:")
        for message_type in model.RequestCommandFlags:
            logger.debug(
                f"  - {message_type.name}: {bool(request_command_flags & message_type)}"
            )

        # Check for that all required messages are enabled
        required_message_disabled = False
        if not transition_message_flags & model.TransitionMessageFlags.InterfaceConfig:
            logger.error(
                "Interface Config Message is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not transition_message_flags & model.TransitionMessageFlags.ZoneStatus:
            logger.error(
                "Zone Status Message is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not transition_message_flags & model.TransitionMessageFlags.PartitionStatus:
            logger.error(
                "Partition Status Message is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if (
            not transition_message_flags
            & model.TransitionMessageFlags.PartitionSnapshot
        ):
            logger.error(
                "Partition Snapshot Message is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not transition_message_flags & model.TransitionMessageFlags.SystemStatus:
            logger.error(
                "System Status Message is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & model.RequestCommandFlags.InterfaceConfig:
            logger.error(
                "Interface Config Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & model.RequestCommandFlags.ZoneName:
            logger.error(
                "Zone Name Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & model.RequestCommandFlags.ZoneStatus:
            logger.error(
                "Zone Status Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & model.RequestCommandFlags.ZoneSnapshot:
            logger.error(
                "Zone Snapshot Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & model.RequestCommandFlags.PartitionStatus:
            logger.error(
                "Partition Status Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & model.RequestCommandFlags.PartitionSnapshot:
            logger.error(
                "Partition Snapshot Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & model.RequestCommandFlags.SystemStatus:
            logger.error(
                "System Status Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & model.RequestCommandFlags.SetClockCalendar:
            logger.error(
                "Set Clock/Calendar Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & model.RequestCommandFlags.PrimaryKeypadNoPin:
            logger.error(
                "Primary Keypad No Pin Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if required_message_disabled:
            logger.error(
                "Please enable the required messages in the Caddx panel configuration before starting plugin."
            )
            raise ControllerError(
                "Required messages not enabled in panel config.  See logs for more information."
            )
        # No need to save this state.  Once we have checked interface configuration above, no need to keep it around
        return

    @staticmethod
    def _process_zone_name_rsp(message: bytearray) -> None:
        # Note that we request zone names for all zones on first startup.   In the case of this handler
        #  the zone object may not yet exist, and we can instantiate if necessary.   For other zone
        #  messages the zone object should already exist.
        if len(message) != model.MessageValidLength[model.MessageType.ZoneNameRsp]:
            logger.error("Invalid zone name message.")
            return
        zone_index = int(message[1])
        zone_name = message[2:].decode("utf-8").rstrip()
        zone = Zone.get_zone_by_index(zone_index)
        if zone is None:
            logger.debug(f"Creating new zone object: {zone_index}) {zone_name}")
            _zone = Zone(zone_index, zone_name)
        else:
            zone.name = zone_name
            zone.is_updated = True
        return

    @staticmethod
    def _process_zone_status_rsp(message: bytearray) -> None:
        if len(message) != model.MessageValidLength[model.MessageType.ZoneNameRsp]:
            logger.error("Invalid zone name message.")
            return
        zone_index = int(message[1])
        zone = Zone.get_zone_by_index(zone_index)
        if zone is None:
            logger.error(f"Unknown zone index: {zone_index}")
            return
        # Skip partition mask at [2:3]
        zone_type_mask = int.from_bytes(message[3:6], byteorder="little")
        zone_type_flags = Zone.get_zone_type_flags(zone_type_mask)
        if zone_type_flags != zone.type_flags:
            logger.debug(
                f"Updated zone type flags for zone {zone_index}: {str(zone_type_flags)}"
            )
            zone.type_flags = zone_type_flags
            zone.is_updated = True
        zone_condition_mask = int.from_bytes(message[6:8], byteorder="little")
        zone_condition_flags = Zone.get_zone_condition_flags(zone_condition_mask)
        if zone_condition_flags != zone.condition_flags:
            logger.debug(
                f"Updated zone condition flags for zone {zone_index}: {str(zone_condition_flags)}"
            )
            zone.condition_flags = zone_condition_flags
            zone.is_updated = True
        return

    @staticmethod
    def _process_ack(_message: bytearray) -> None:
        logger.debug("Got ACK in response to previous request.")

    @staticmethod
    def _process_zone_snapshot_rsp(message: bytearray) -> None:

        def _update_zone_attr(z: Zone, mask: int, start_bit: int) -> None:
            z.faulted = bool(get_nth_bit(mask, start_bit))
            z.bypassed = bool(get_nth_bit(mask, start_bit + 1))
            z.trouble = bool(get_nth_bit(mask, start_bit + 2))
            z.is_updated = True

        if len(message) != model.MessageValidLength[model.MessageType.ZonesSnapshotRsp]:
            logger.error("Invalid z snapshot message.")
            return
        zone_index = int(message[1]) * 16
        for i in range(2, len(message)):
            zone_mask = int(message[i])
            for bit in [0, 4]:
                if (zone := Zone.get_zone_by_index(zone_index)) is not None:
                    _update_zone_attr(zone, zone_mask, bit)
                zone_index += 1

    @staticmethod
    def _process_partition_status_rsp(message: bytearray) -> None:
        if len(message) != model.MessageValidLength[model.MessageType.PartitionStatusRsp]:
            logger.error("Invalid zone name message.")
            return
        _partition = int(message[1])
        # ToDo: Figure out what data we need to retain.

    @staticmethod
    def _process_partition_snapshot_rsp(message: bytearray) -> None:
        raise NotImplementedError("_process_partition_snapshot_rsp not implemented")

    @staticmethod
    def _process_system_status_rsp(message: bytearray) -> None:
        raise NotImplementedError("_process_system_status_rsp not implemented")

    @staticmethod
    def _process_log_event_ind(message: bytearray) -> None:
        raise NotImplementedError("_process_log_event_ind not implemented")

    @staticmethod
    def _process_keypad_button_ind(message: bytearray) -> None:
        raise NotImplementedError("_process_keypad_button_ind not implemented")

    @staticmethod
    def _process_zones_snapshot_rsp(message: bytearray) -> None:
        raise NotImplementedError("_process_zones_snapshot_rsp not implemented")

    def _process_command_queue(self) -> None:
        """
        Process the command queue.

        Send the next command in the queue, if any.
        Wait for the response, if any.
        Remove the command from the queue:

        * If expected response is received (from response_handler field in Command object),
        * If timeout occurs after 3 retries,
        * if unexpected response is received.  This is likely a NAK, Reject or Fail response.

        :return: None
        """
        while not self._command_queue.empty():
            command = self._command_queue.get()
            assert isinstance(command, model.Command)

            # Retry command up to 3 times on timeout.
            # Processed transition message do not count toward timeout and are processed in-line.
            # Fail immediately if the command is rejected.
            retries = 3
            incoming_message_type = None
            incoming_message = None
            self._send_direct(command.req_msg_type, command.req_msg_data)
            while retries > 0:
                incoming_message = self._read_message(wait=True)
                if incoming_message is None:  # Timeout
                    logger.warning(
                        f"Timeout waiting for response to {command.req_msg_type.name} message. Retrying."
                    )
                    retries -= 1
                    self._send_direct(command.req_msg_type, command.req_msg_data)
                    continue
                incoming_message_type_byte = incoming_message[0] & 0b001111111
                try:
                    incoming_message_type = model.MessageType(incoming_message_type_byte)
                except ValueError:
                    logger.error(f"Unknown incoming message type: {incoming_message_type:02x}")
                    incoming_message_type = None
                    incoming_message = None
                    break

                if incoming_message_type not in command.response_handler:
                    # This is probably a transition message.  Process it.
                    logger.debug(
                        f"Received transition message {incoming_message_type.name} "
                        f"while waiting for response to {command.req_msg_type.name} message"
                    )
                    self._process_transition_message(incoming_message)
                    continue
                if incoming_message_type in (
                    model.MessageType.Rejected,
                    model.MessageType.Failed,
                    model.MessageType.NACK,
                ):
                    logger.error(f"Message of type {command.req_msg_type.name} rejected by panel")
                    incoming_message_type = None
                    incoming_message = None
                break

            if incoming_message_type is None:
                logger.error(f"Command {command.req_msg_type.name} failed due timeout or rejection. Giving up.")
                self._command_queue.task_done()
                continue

            response_handler = command.response_handler[incoming_message_type]
            if response_handler:
                response_handler(incoming_message)
            logger.debug(
                f"Command {command.req_msg_type.name} completed successfully with {incoming_message_type.name}"
            )
            self._command_queue.task_done()
        return

    def _send_request_to_queue(self, command: model.Command) -> None:
        self._command_queue.put(command)
        return

    def _send_direct(
        self, message_type: model.MessageType, message_data: Optional[bytearray]
    ) -> None:
        message_length = 1 + len(message_data) if message_data else 1
        if message_type not in model.MessageValidLength:
            logger.error(f"Unsupported message type: {message_type:02x}")
            return
        if not message_length == model.MessageValidLength[message_type]:
            logger.error(
                f"Invalid message length for message type {message_type.name}. "
                f"Expected {model.MessageValidLength[message_type]}, got {message_length}."
            )
            return

        message = bytearray()
        message.append(message_length & 0xFF)
        message.append(message_type & 0xFF)
        if message_data:
            message.extend(message_data)
        checksum = self._calculate_fletcher16(message)
        message.extend(checksum.to_bytes(2, byteorder="little"))

        message_stuffed = bytearray()
        for i in message:
            if i == 0x7E:
                message_stuffed.extend(b"\x7d\x5e")
            elif i == 0x7D:
                message_stuffed.extend(b"\x7d\x5d")
            else:
                message_stuffed.append(i)

        # Add the start byte
        message_stuffed[0:0] = b"\x7e"

        logger.debug(f"Sending message: {message_stuffed.hex()}")
        self.conn.write(message_stuffed)
        return

    def _send_direct_ack(self):
        self._send_direct(model.MessageType.ACK, None)

    def _send_direct_nack(self):
        self._send_direct(model.MessageType.NACK, None)

    def _send_interface_configuration_req(self) -> None:
        logger.debug(f"Sending interface configuration request")
        command = model.Command(
            model.MessageType.InterfaceConfigReq,
            None,
            {model.MessageType.InterfaceConfigRsp: self._process_interface_config_rsp},
        )
        self._send_request_to_queue(command)

    def _send_zone_name_req(self, zone: int) -> None:
        logger.debug(f"Sending zone name request for zone {zone}")
        zone &= 0xFF
        command = model.Command(
            model.MessageType.ZoneNameReq,
            bytearray(zone.to_bytes(1, byteorder="big")),
            {model.MessageType.ZoneNameReq: self._process_zone_name_rsp},
        )
        self._send_request_to_queue(command)

    def _send_zone_status_req(self, zone: int) -> None:
        logger.debug(f"Sending zone status request for zone {zone}")
        zone &= 0xFF
        command = model.Command(
            model.MessageType.ZoneStatusReq,
            bytearray(zone.to_bytes(1, byteorder="big")),
            {model.MessageType.ZoneStatusRsp: self._process_zone_status_rsp},
        )
        self._send_request_to_queue(command)

    def _send_zone_snapshot_req(self, partition: int) -> None:
        logger.debug(f"Sending zone snapshot request for partition {partition}")
        partition &= 0xFF
        command = model.Command(
            model.MessageType.ZonesSnapshotReq,
            bytearray(partition.to_bytes(1, byteorder="big")),
            {model.MessageType.ZonesSnapshotRsp: self._process_zone_snapshot_rsp},
        )
        self._send_request_to_queue(command)

    def _send_partition_snapshot_req(self) -> None:
        logger.debug(f"Sending partition snapshot request")
        command = model.Command(
            model.MessageType.PartitionSnapshotReq,
            None,
            {
                model.MessageType.PartitionSnapshotRsp: self._process_partition_snapshot_rsp
            },
        )
        self._send_request_to_queue(command)

    def send_system_status_req(self) -> None:
        logger.debug(f"Sending system status request")
        command = model.Command(
            model.MessageType.SystemStatusReq,
            None,
            {model.MessageType.SystemStatusRsp: self._process_system_status_rsp},
        )
        self._send_request_to_queue(command)

    def send_set_clock_req(self) -> None:
        time_stamp = time.localtime(time.time())
        message = bytearray()
        message.extend((time_stamp.tm_year - 2000).to_bytes(1, byteorder="little"))
        message.extend(time_stamp.tm_month.to_bytes(1, byteorder="little"))
        message.extend(time_stamp.tm_mday.to_bytes(1, byteorder="little"))
        message.extend(time_stamp.tm_hour.to_bytes(1, byteorder="little"))
        message.extend(time_stamp.tm_min.to_bytes(1, byteorder="little"))
        # Correct for offset between time.localtime() and what panels expects.
        corrected_wday = [2, 3, 4, 5, 6, 7, 1][time_stamp.tm_wday]
        message.extend(corrected_wday.to_bytes(1, byteorder="little"))
        assert len(message) == 6
        # Todo: Verify responses to Set Clock/Calendar.  Assume ACK for now.
        command = model.Command(
            model.MessageType.SetClockCalendar,
            message,
            {model.MessageType.ACK: self._process_ack},
        )
        self._send_request_to_queue(command)

    def _queue_db_sync(self) -> None:
        self.panel_synced = False
        # Do Interface Configuration Request to ensure that panel interface is configured correctly.
        #  May throw exception if not.  Handled in control loop.
        self._send_interface_configuration_req()

        # Do System Status Request to find valid partitions.  The response will trigger Partition Status Requests
        #  for valid partitions in its handler.

        # Get all the zone information up to self.number_zones.
