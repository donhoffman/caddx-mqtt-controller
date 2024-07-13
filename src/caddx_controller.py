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
        self.panel_firmware: Optional[str] = None
        self.panel_id: Optional[int] = None
        self.partition_mask: Optional[int] = None
        self.conn = serial.Serial(serial_path, baudrate=baud_rate, timeout=2)
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

        # Clean out any old transition message before we start synchronization
        self._send_direct_ack()
        time.sleep(1)
        while True:
            received_message = self._read_message(wait=False)
            if received_message is None:
                logger.debug("No additional old transition messages waiting.")
                break
            logger.debug("Discarding old message before synchronization.")

        logger.info("Starting synchronization.")
        self._db_sync_start0()
        try:
            while True:
                # Next statement blocks until all commands and associated responses have been cleared.
                self._process_command_queue()
                if not self.panel_synced:
                    # We do not reach this point until all commands submitted by _db_sync_start() have completed.
                    self.panel_synced = True
                    logger.info("Synchronization completed. Setting clock.")
                    self.send_set_clock_req()
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
        if len(start_character) == 0:  # Timeout probably
            logger.debug(f"Zero length read.  In Waiting: {self.conn.in_waiting}")
            return None
        if start_character != b"\x7e":
            logger.error(f"Invalid or missing start character: {start_character}")
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
        if self.panel_synced:
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
                case (
                    _
                ):  # Message type not supported for broadcast or transition messages
                    logger.error(
                        f"Received message with indeterminate disposition: {message_type}"
                    )
                    logger.error(
                        "This is probably a bug in the server. Please report it."
                    )
        else:
            logger.debug("Not processing transition message during synchronization.")

        if ack_requested:  # OK to ACK even unexpected messages types
            self._send_direct_ack()
        return

    def _process_interface_config_rsp(self, message: bytearray) -> None:
        self.panel_firmware = message[1:5].decode("ascii").rstrip()
        logger.debug(f"Panel firmware: {self.panel_firmware}")

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
        logger.info(
            f"Panel with firmware '{self.panel_firmware}' meets interface requirements for this server."
        )
        # No need to save this state.  Once we have checked interface configuration above, no need to keep it around
        return

    # noinspection PyMethodMayBeStatic
    def _process_zone_name_rsp(self, message: bytearray) -> None:
        # Note that we request zone names for all zones on first startup.   In the case of this handler
        #  the zone object may not yet exist, and we can instantiate if necessary.   For other zone
        #  messages the zone object should already exist.
        if len(message) != model.MessageValidLength[model.MessageType.ZoneNameRsp]:
            logger.error("Invalid zone name message.")
            return
        zone_index = (
            int(message[1]) + 1
        )  # Server zones start from 1.  Panel zones start from 0.
        zone_name = message[2:].decode("utf-8").rstrip()
        zone = Zone.get_zone_by_index(zone_index)
        if zone is None:
            logger.debug(f"Creating new zone object: Zone {zone_index} - {zone_name}")
            _zone = Zone(zone_index, zone_name)
        elif self.panel_synced:
            logger.error(
                f"Attempt to create new zone after sync has completed. Ignoring, but this is a bug."
            )
        else:
            logger.info(f"Zone {zone_index} renamed from {zone.name} to {zone_name}")
            zone.name = zone_name
            zone.is_updated = True

    # noinspection PyMethodMayBeStatic
    def _process_zone_status_rsp(self, message: bytearray) -> None:
        if len(message) != model.MessageValidLength[model.MessageType.ZoneStatusRsp]:
            logger.error("Invalid zone status message.")
            return
        zone_index = (
            int(message[1]) + 1
        )  # Server zones start from 1.  Panel zones start from 0.
        zone = Zone.get_zone_by_index(zone_index)
        if zone is None:
            logger.error(f"Ignoring zone status. Unknown zone index: {zone_index}")
            return
        logger.debug(f"Got status for zone {zone_index}.")
        # Skip partition mask at [2:3]
        zone.type_mask = int.from_bytes(message[3:6], byteorder="little")
        zone.condition_mask = int.from_bytes(message[6:8], byteorder="little")
        return

    # noinspection PyMethodMayBeStatic
    def _process_ack(self, _message: bytearray) -> None:
        logger.debug("Got ACK in response to previous request.")

    # noinspection PyMethodMayBeStatic
    def _process_zone_snapshot_rsp(self, message: bytearray) -> None:

        def _update_zone_attr(z: Zone, _mask: int, _start_bit: int) -> None:
            # z.faulted = bool(get_nth_bit(mask, start_bit))
            # z.bypassed = bool(get_nth_bit(mask, start_bit + 1))
            # z.trouble = bool(get_nth_bit(mask, start_bit + 2))
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

    # noinspection PyMethodMayBeStatic
    def _process_partition_status_rsp(self, message: bytearray) -> None:
        if (
            len(message)
            != model.MessageValidLength[model.MessageType.PartitionStatusRsp]
        ):
            logger.error("Invalid partition status response message.")
            return
        partition = int(message[1])
        if not self.panel_synced:
            logger.debug(
                f"TBD: Creating new object for partition {partition+1} if it does not exist."
            )
        else:
            logger.debug(f"Got status for partition {partition+1}.")

    # noinspection PyMethodMayBeStatic
    def _process_partition_snapshot_rsp(self, _message: bytearray) -> None:
        logger.error("_process_partition_snapshot_rsp not implemented")

    def _process_system_status_rsp(self, message: bytearray) -> None:
        if len(message) != model.MessageValidLength[model.MessageType.SystemStatusRsp]:
            logger.error("Invalid system status message.")
            return
        if self.panel_id is None:
            self.panel_id = int(message[1])
            self.partition_mask = int(message[10])
        else:
            new_partition_mask = int(message[10])
            if new_partition_mask != self.partition_mask:
                logger.error(
                    "Partition mask updated since last sync.  Please restart server to synchronise new configuration."
                )
        if self.panel_synced:
            # Todo: Monitor system status for faults.   Partition state is used for alarm status.
            logger.debug(
                "Ignoring system status for now.  TBD: Process system status for faults."
            )
            return
        else:
            for i in range(0, 7):
                partition_bit = bool(get_nth_bit(self.partition_mask, i))
                if partition_bit:
                    valid_partition = i + 1
                    logger.info(f"Partition {valid_partition} active. Getting status.")
                    self._send_partition_status_req(valid_partition)

    # noinspection PyMethodMayBeStatic
    def _process_log_event_ind(self, _message: bytearray) -> None:
        logger.error("_process_log_event_ind not implemented")

    # noinspection PyMethodMayBeStatic
    def _process_keypad_button_ind(self, _message: bytearray) -> None:
        logger.error("_process_keypad_button_ind not implemented")

    # noinspection PyMethodMayBeStatic
    def _process_zones_snapshot_rsp(self, _message: bytearray) -> None:
        logger.error("_process_zones_snapshot_rsp not implemented")

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
                incoming_message_is_acked = bool(incoming_message[0] & 0b10000000)
                try:
                    incoming_message_type = model.MessageType(
                        incoming_message_type_byte
                    )
                except ValueError:
                    logger.critical(
                        f"Unknown incoming message type: {incoming_message_type_byte:02x}"
                    )
                    continue

                # Panel did not like our message.   Don't resend.
                if incoming_message_type in (
                    model.MessageType.Rejected,
                    model.MessageType.Failed,
                    model.MessageType.NACK,
                ):
                    logger.critical(
                        f"Message of type {command.req_msg_type.name} rejected by panel"
                    )
                    self._command_queue.task_done()
                    break

                if (
                    incoming_message_type not in command.response_handler
                    or incoming_message_is_acked
                ):
                    # This is probably a transition message.  Process it.
                    logger.debug(
                        f"Received transition message {incoming_message_type.name} "
                        f"while waiting for response to {command.req_msg_type.name} message. "
                        "Processing as transition message."
                    )
                    self._process_transition_message(incoming_message)
                    continue
                response_handler = command.response_handler[incoming_message_type]
                response_handler(incoming_message)
                logger.debug(
                    f"Command {command.req_msg_type.name} completed successfully with {incoming_message_type.name}"
                )
                self._command_queue.task_done()
                break
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
        time.sleep(0.25)
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
        zone_index = (zone - 1) & 0xFF
        command = model.Command(
            model.MessageType.ZoneNameReq,
            bytearray(zone_index.to_bytes(1, byteorder="big")),
            {model.MessageType.ZoneNameRsp: self._process_zone_name_rsp},
        )
        self._send_request_to_queue(command)

    def _send_zone_status_req(self, zone: int) -> None:
        logger.debug(f"Sending zone status request for zone {zone}")
        zone_index = (zone - 1) & 0xFF
        command = model.Command(
            model.MessageType.ZoneStatusReq,
            bytearray(zone_index.to_bytes(1, byteorder="big")),
            {model.MessageType.ZoneStatusRsp: self._process_zone_status_rsp},
        )
        self._send_request_to_queue(command)

    def _send_zone_snapshot_req(self, zone_offset: int) -> None:
        zone_offset &= 0xFF
        logger.debug(
            f"Sending zone snapshot request for zone offset {zone_offset}. Zone base: {(zone_offset*16)+1}."
        )
        command = model.Command(
            model.MessageType.ZonesSnapshotReq,
            bytearray(zone_offset.to_bytes(1, byteorder="big")),
            {model.MessageType.ZonesSnapshotRsp: self._process_zone_snapshot_rsp},
        )
        self._send_request_to_queue(command)

    def _send_partition_status_req(self, partition: int):
        logger.debug(f"Sending partition {partition} status request.")
        assert 1 <= partition <= 7
        partition = partition - 1
        command = model.Command(
            model.MessageType.PartitionStatusReq,
            bytearray(partition.to_bytes(1, byteorder="little")),
            {model.MessageType.PartitionStatusRsp: self._process_partition_status_rsp},
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

    def _send_system_status_req(self) -> None:
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
        message.extend(time_stamp.tm_mon.to_bytes(1, byteorder="little"))
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

    def _db_sync_start0(self) -> None:
        self.panel_synced = False

        # Do Interface Configuration Request to ensure that panel interface is configured correctly.
        #  May throw exception if not.  Handled in control loop.
        self._send_interface_configuration_req()

        # Do System Status Request to find valid partitions.  The response will trigger Partition Status Requests
        #  for valid partitions in its handler.
        self._send_system_status_req()

        # Get all the zone information up to self.number_zones.
        for zone_number in range(1, (self.number_zones + 1)):
            self._send_zone_name_req(zone_number)
            self._send_zone_status_req(zone_number)
