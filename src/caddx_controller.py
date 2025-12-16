from __future__ import annotations

from typing import NamedTuple, Dict, Callable, Optional, TYPE_CHECKING
from types import MappingProxyType
from enum import IntEnum
import logging
import serial
import queue
import time
import datetime

if TYPE_CHECKING:
    from mqtt_client import MQTTClient

from zone import Zone
from partition import Partition

logger = logging.getLogger("app.caddx_controller")

# Configuration constants
SERIAL_POLL_INTERVAL_SECONDS = 0.05  # Interval between serial port polls
REPUBLISH_INTERVAL_MINUTES = 60  # How often to republish all states to MQTT
ACK_DELAY_SECONDS = 0.25  # Delay before sending ACK message


def get_nth_bit(num: int, n: int) -> int:
    """
    Extract the nth bit from an integer (0-indexed, LSB first).

    Args:
        num: Integer to extract bit from
        n: Bit position (0 = LSB)

    Returns:
        0 or 1 depending on bit value at position n
    """
    return (num >> n) & 1


def pin_to_bytearray(pin: str) -> bytearray:
    """
    Convert a PIN string to packed BCD bytearray format for panel protocol.

    Packs two decimal digits per byte in BCD format (e.g., "1234" -> [0x12, 0x34, 0x00]).

    Args:
        pin: PIN string containing 4 or 6 decimal digits

    Returns:
        3-byte bytearray with BCD-encoded PIN (trailing zeros if 4 digits)

    Raises:
        ValueError: If PIN length is not 4 or 6 characters
    """
    if len(pin) not in [4, 6]:
        raise ValueError("PIN must be 4 or 6 characters long")

    pin_array = bytearray(3)

    for i in range(0, len(pin), 2):
        byte = (int(pin[i]) << 4) | int(pin[i + 1])
        pin_array[i // 2] = byte

    return pin_array


def panel_zone_to_server(panel_zone: int) -> int:
    """
    Convert panel zone index (0-based) to server zone index (1-based).

    Panel zones are numbered 0-7, server zones are numbered 1-8.

    Args:
        panel_zone: Zone index from panel message (0-7)

    Returns:
        Server zone index (1-8)
    """
    return panel_zone + 1


def server_zone_to_panel(server_zone: int) -> int:
    """
    Convert server zone index (1-based) to panel zone index (0-based).

    Server zones are numbered 1-8, panel zones are numbered 0-7.
    The result is masked to ensure it fits in a single byte for the protocol.

    Args:
        server_zone: Zone index used in server (1-8)

    Returns:
        Panel zone index as byte value (0-7, masked to 0xFF)
    """
    return (server_zone - 1) & 0xFF


def panel_partition_to_server(panel_partition: int) -> int:
    """
    Convert panel partition index (0-based) to server partition index (1-based).

    Panel partitions are numbered 0-7, server partitions are numbered 1-8.

    Args:
        panel_partition: Partition index from panel message (0-7)

    Returns:
        Server partition index (1-8)
    """
    return panel_partition + 1


def server_partition_to_panel(server_partition: int) -> int:
    """
    Convert server partition index (1-based) to panel partition index (0-based).

    Server partitions are numbered 1-8, panel partitions are numbered 0-7.
    The result is masked to ensure it fits in a single byte for the protocol.

    Args:
        server_partition: Partition index used in server (1-8)

    Returns:
        Panel partition index as byte value (0-7, masked to 0xFF)
    """
    return (server_partition - 1) & 0xFF


class StopThread(Exception):
    """Exception raised to signal graceful shutdown of the controller thread."""
    pass


class ControllerError(Exception):
    """Exception raised when panel configuration validation fails."""
    pass


class MessageType(IntEnum):
    """
    Caddx NX-584 protocol message type identifiers.

    Messages are split into responses (0x01-0x1F) from the panel
    and requests (0x21-0x3F) sent to the panel.
    """
    InterfaceConfigRsp = 0x01  # Interface Configuration (Response)
    ZoneNameRsp = 0x03  # Zone Name (Response)
    ZoneStatusRsp = 0x04  # Zone Status (Response)
    ZonesSnapshotRsp = 0x05  # Zones Snapshot (Response)
    PartitionStatusRsp = 0x06  # Partition Status (Response)
    PartitionSnapshotRsp = 0x07  # Partition Snapshot (Response)
    SystemStatusRsp = 0x08  # System Status (Response)
    X10MessageInd = 0x09  # X10 Message (Indication)
    LogEventInd = 0x0A  # Log Event (Indication)
    KeypadButtonInd = 0x0B  # Keypad Button (Response)
    ProgramDataRsp = 0x10  # Program Data Reply (Response)
    UserInfoRsp = 0x12  # User Info Reply (Response)
    Failed = 0x1C  # Failed Request (Response)
    ACK = 0x1D  # Acknowledge (Response)
    NACK = 0x1E  # Negative Acknowledge (Response)
    Rejected = 0x1F  # Rejected (Response)

    InterfaceConfigReq = 0x21  # Interface Configuration (Request)
    ZoneNameReq = 0x23  # Zone Name (Request)
    ZoneStatusReq = 0x24  # Zone Status (Request)
    ZonesSnapshotReq = 0x25  # Zones Snapshot (Request)
    PartitionStatusReq = 0x26  # Partition Status (Request)
    PartitionSnapshotReq = 0x27  # Partition Snapshot (Request)
    SystemStatusReq = 0x28  # System Status (Request)
    X10MessageReq = 0x29  # X10 Message (Request)
    LogEventReq = 0x2A  # Log Event (Request)
    KeypadTextMsgReq = 0x2B  # Keypad Text Message (Request)
    KeypadTerminalModeReq = 0x2C  # Keypad Terminal Mode (Request)
    ProgramDataReq = 0x30  # Program Data Request (Request)
    ProgramDataCmd = 0x31  # Program Data Command (Request)
    UserInfoReqPin = 0x32  # User Info Request with PIN (Request)
    UserInfoReqNoPin = 0x33  # User Info Request without PIN (Request)
    SetUserCodePin = 0x34  # Set User Code with PIN (Request)
    SetUserCodeNoPin = 0x35  # Set User Code without PIN (Request)
    SetUserAuthorityPin = 0x36  # Set User Authority with PIN (Request)
    SetUserAuthorityNoPin = 0x37  # Set User Authority without PIN (Request)
    SetClockCalendar = 0x3B  # Set Clock/Calendar (Request)
    PrimaryKeypadFuncPin = 0x3C  # Primary Keypad Function with PIN (Request)
    PrimaryKeypadFuncNoPin = 0x3D  # Primary Keypad Function without PIN (Request)
    SecondaryKeypadFunc = 0x3E  # Secondary Keypad Function (Request)
    ZoneBypassToggle = 0x3F  # Zone Bypass Toggle (Request)


MessageValidLength = MappingProxyType(
    {
        MessageType.InterfaceConfigRsp: 11,
        MessageType.ZoneNameRsp: 18,
        MessageType.ZoneStatusRsp: 8,
        MessageType.ZonesSnapshotRsp: 10,
        MessageType.PartitionStatusRsp: 9,
        MessageType.PartitionSnapshotRsp: 9,
        MessageType.SystemStatusRsp: 12,
        MessageType.X10MessageInd: 4,
        MessageType.LogEventInd: 10,
        MessageType.KeypadButtonInd: 3,
        MessageType.ProgramDataRsp: 13,
        MessageType.UserInfoRsp: 17,
        MessageType.Failed: 1,
        MessageType.ACK: 1,
        MessageType.NACK: 1,
        MessageType.Rejected: 1,
        MessageType.InterfaceConfigReq: 1,
        MessageType.ZoneNameReq: 2,
        MessageType.ZoneStatusReq: 2,
        MessageType.ZonesSnapshotReq: 2,
        MessageType.PartitionStatusReq: 2,
        MessageType.PartitionSnapshotReq: 1,
        MessageType.SystemStatusReq: 1,
        MessageType.X10MessageReq: 4,
        MessageType.LogEventReq: 2,
        MessageType.KeypadTextMsgReq: 12,
        MessageType.KeypadTerminalModeReq: 3,
        MessageType.ProgramDataReq: 4,
        MessageType.ProgramDataCmd: 13,
        MessageType.UserInfoReqPin: 5,
        MessageType.UserInfoReqNoPin: 2,
        MessageType.SetUserCodePin: 8,
        MessageType.SetUserCodeNoPin: 5,
        MessageType.SetUserAuthorityPin: 7,
        MessageType.SetUserAuthorityNoPin: 4,
        MessageType.SetClockCalendar: 7,
        MessageType.PrimaryKeypadFuncPin: 6,
        MessageType.PrimaryKeypadFuncNoPin: 4,
        MessageType.SecondaryKeypadFunc: 3,
        MessageType.ZoneBypassToggle: 2,
    }
)


class Command(NamedTuple):
    """
    Command structure for queueing panel requests with their handlers.

    Attributes:
        req_msg_type: Message type to send to panel
        req_msg_data: Optional payload bytes for the message
        response_handler: Dict mapping expected response types to handler functions
        request_ack: Whether to request ACK from panel (sets bit 0x80 in msg type)
    """
    req_msg_type: MessageType
    req_msg_data: Optional[bytearray] = None
    response_handler: Optional[Dict[MessageType, Callable[[bytearray], None]]] = None
    request_ack: bool = False


# Interface Configuration (Response) constants
class TransitionMessageFlags(IntEnum):
    """
    Bitmask flags indicating which transition/broadcast messages the panel supports.

    These flags appear in the Interface Configuration response (2 bytes, little-endian).
    Each bit indicates whether the panel will send unsolicited broadcast messages
    of that type when state changes occur.
    """
    # Combined transition/broadcast message flags.
    # Represented as 2 bytes in little-endian format OTW, so lower index bytes are rightmost when represented as int.
    # Interface Configuration response
    InterfaceConfig = 0b_00000000_00000010
    # Zone Status response
    ZoneStatus = 0b_00000000_00010000
    # Zone Snapshot response
    ZoneSnapshot = 0b_00000000_00100000
    # Partition Status response
    PartitionStatus = 0b_00000000_01000000
    # Partition Snapshot response
    PartitionSnapshot = 0b_00000000_10000000
    # System Status response
    SystemStatus = 0b_00000001_00000000
    # X10 Message indication
    X10Message = 0b_00000010_00000000
    # Log Event response/indication
    LogEvent = 0b_00000100_00000000
    # Keypad Button response
    KeypadButton = 0b_00001000_00000000


class RequestCommandFlags(IntEnum):
    """
    Bitmask flags indicating which request/command messages the panel supports.

    These flags appear in the Interface Configuration response (4 bytes, little-endian).
    Each bit indicates whether the panel will accept and respond to that request type.
    """
    # Combined request/ message flags.
    # Represented as 4 bytes in little-endian format over-the-wire, so lower index bytes are rightmost
    #  when represented as int.
    # Interface Configuration request
    InterfaceConfig = 0b_00000000_00000000_00000000_00000010
    # Zone Name request
    ZoneName = 0b_00000000_00000000_00000000_00001000
    # Zone Status request
    ZoneStatus = 0b_00000000_00000000_00000000_00010000
    # Zone Snapshot request
    ZoneSnapshot = 0b_00000000_00000000_00000000_00100000
    # Partition Status request
    PartitionStatus = 0b_00000000_00000000_00000000_01000000
    # Partition Snapshot request
    PartitionSnapshot = 0b_00000000_00000000_00000000_10000000
    # System Status request
    SystemStatus = 0b_00000000_00000000_00000001_00000000
    # X10 Message request
    X10Message = 0b_00000000_00000000_00000010_00000000
    # Log Event request
    LogEvent = 0b_00000000_00000000_00000100_00000000
    # Keypad Text Message request
    KeypadTextMessage = 0b_00000000_00000000_00001000_00000000
    # Keypad Terminal Mode request
    KeypadTerminalMode = 0b_00000000_00000000_00010000_00000000
    # Program Data request
    ProgramData = 0b_00000000_00000001_00000000_00000000
    # Program Data command
    ProgramDataCommand = 0b_00000000_00000010_00000000_00000000
    # User Info request with PIN
    UserInfoPin = 0b_00000000_00000100_00000000_00000000
    # User Info request without PIN
    UserInfoNoPin = 0b_00000000_00001000_00000000_00000000
    # Set User Code with PIN
    SetUserCodePin = 0b_00000000_00010000_00000000_00000000
    # Set User Code without PIN
    SetUserCodeNoPin = 0b_00000000_00100000_00000000_00000000
    # Set User Authority with PIN
    SetUserAuthorityPin = 0b_00000000_01000000_00000000_00000000
    # Set User Authority without PIN
    SetUserAuthorityNoPin = 0b_00000000_10000000_00000000_00000000
    # Set Clock/Calendar
    SetClockCalendar = 0b_00001000_00000000_00000000_00000000
    # Primary Keypad Function with PIN
    PrimaryKeypadPin = 0b_00010000_00000000_00000000_00000000
    # Primary Keypad Function without PIN
    PrimaryKeypadNoPin = 0b_00100000_00000000_00000000_00000000
    # Secondary Keypad Function
    SecondaryKeypad = 0b_01000000_00000000_00000000_00000000
    # Zone Bypass Toggle
    ZoneBypassToggle = 0b_10000000_00000000_00000000_00000000


class PrimaryKeypadFunctions(IntEnum):
    """
    Primary keypad function codes for arm/disarm operations.

    These values are used in PrimaryKeypadFunction messages to control partitions.
    """
    TurnOffAlarm = 0x00
    Disarm = 0x01
    ArmAway = 0x02
    ArmStay = 0x03
    Cancel = 0x04
    InitiateAutoArm = 0x05
    StartWalkTest = 0x06
    StopWalkTest = 0x07


class CaddxController:
    """
    Controller for Caddx NX-584 alarm panel serial protocol communication.

    Manages serial communication with Caddx alarm panels, implements the NX-584
    binary protocol with Fletcher-16 checksums and byte stuffing, maintains
    command queue with retry logic, and synchronizes panel state on startup.

    Attributes:
        serial_path: Path to serial device (e.g., /dev/ttyUSB0)
        number_zones: Maximum number of zones to monitor
        default_code: Default PIN for arm/disarm (BCD encoded)
        default_user: Default user number for arm/disarm without PIN
        mqtt_client: MQTT client for publishing state updates
        panel_synced: True after initial synchronization completes
        panel_firmware: Firmware version string from panel
        panel_id: Panel ID from system status
        partition_mask: Bitmask of active partitions
        ignored_zones: Set of zone numbers to skip during sync
    """
    def __init__(
        self,
        serial_path: str,
        baud_rate: int,
        number_zones: int,
        default_code: str = None,
        default_user: str = None,
        ignored_zones: str = None,
    ) -> None:
        """
        Initialize Caddx controller and open serial connection.

        Args:
            serial_path: Path to serial device (e.g., /dev/ttyUSB0)
            baud_rate: Serial baud rate (typically 38400)
            number_zones: Maximum zone number to monitor
            default_code: Optional PIN code for arm/disarm operations
            default_user: Optional user number for PIN-less operations
            ignored_zones: Optional comma-separated list of zone numbers to ignore

        Raises:
            serial.SerialException: If serial port cannot be opened
        """
        self.serial_path = serial_path
        self.number_zones = number_zones
        self.default_code = default_code
        self.default_user = default_user
        self.mqtt_client: MQTTClient = None  # type: ignore  # Set in control_loop()
        self._command_queue = None
        self.conn = None
        self.panel_synced = False
        self.read_timeout = 2.0
        self.sleep_between_polls = SERIAL_POLL_INTERVAL_SECONDS
        self.panel_firmware: Optional[str] = None
        self.panel_id: Optional[int] = None
        self.partition_mask: Optional[int] = None
        self.ignored_zones: set[int] = (
            set([int(x) for x in ignored_zones.split(",")]) if ignored_zones else set()
        )
        self.conn = serial.Serial(serial_path, baudrate=baud_rate, timeout=2)
        logger.info(f"Opened serial connection at '{serial_path}'. Mode is binary")

    def control_loop(self, mqtt_client: MQTTClient) -> int:
        """
        Main control loop for panel communication and state management.

        Performs initial panel synchronization, publishes configs to Home Assistant,
        processes command queue, polls for transition messages, and republishes
        state hourly. Runs until interrupted or exception occurs.

        Args:
            mqtt_client: MQTT client for publishing states and configs

        Returns:
            0 for normal exit, 1 for error exit
        """
        logger.debug("Starting controller run loop.")
        self.mqtt_client = mqtt_client
        self._command_queue = queue.Queue()
        self.conn.reset_input_buffer()
        rc = 0

        # Clean out any old transition message before we start synchronization
        self._send_direct_ack()
        while True:
            received_message = self._read_message(wait=True)
            if received_message is None:
                logger.debug("No additional old transition messages waiting.")
                break
            logger.debug("Discarding old message before synchronization.")

        next_panel_update = datetime.datetime.max
        logger.info("Starting synchronization.")
        self._db_sync_start0()
        try:
            while True:
                # Next statement blocks until all commands and associated responses have been cleared.
                self._process_command_queue()
                if not self.panel_synced:
                    # We do not reach this point until all commands submitted by _db_sync_start() have completed.
                    self.panel_synced = True
                    logger.info(
                        "Synchronization completed. Setting clock and sending configs to HA."
                    )
                    self.send_set_clock_req()
                    mqtt_client.publish_configs()
                    mqtt_client.publish_zone_configs()
                    mqtt_client.publish_online()
                    mqtt_client.publish_partition_states()
                    mqtt_client.publish_zone_states()
                    next_panel_update = datetime.datetime.now() + datetime.timedelta(
                        minutes=REPUBLISH_INTERVAL_MINUTES
                    )
                elif datetime.datetime.now() >= next_panel_update:
                    next_panel_update = datetime.datetime.now() + datetime.timedelta(
                        minutes=REPUBLISH_INTERVAL_MINUTES
                    )
                    mqtt_client.publish_partition_states()
                    mqtt_client.publish_zone_states()
                time.sleep(self.sleep_between_polls)
                received_message = self._read_message(wait=False)
                if received_message is not None:
                    self._process_transition_message(received_message)
        except KeyboardInterrupt:
            logger.debug("Received keyboard interrupt. Normal stop")
        except StopThread:
            logger.debug("Normal stop.")
        except Exception as e:
            logger.error(f"Caddx controller received exception: {e}")
            rc = 1
        finally:
            # Publish offline status before cleanup
            if mqtt_client is not None:
                mqtt_client.publish_offline()
            # Clean up serial connection and command queue
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
        """
        Read and decode a message from the serial port using NX-584 protocol.

        Reads start byte (0x7E), message length, data, and checksum. Performs
        byte unstuffing (0x7D 0x5E → 0x7E, 0x7D 0x5D → 0x7D) and validates
        Fletcher-16 checksum. Returns None on timeout, invalid format, or
        checksum mismatch.

        Args:
            wait: If True, block until message arrives. If False, return None immediately
                  if no data available.

        Returns:
            Message data (without length byte, start byte, or checksum) on success,
            None on timeout or error
        """
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
        :param data: The data to be checked.
        :return: 16-bit checksum.
        """
        sum1 = int(0)
        sum2 = int(0)
        for byte in data:
            sum1 = (sum1 + byte) % 255
            sum2 = (sum2 + sum1) % 255
        return (sum2 << 8) | sum1

    def _process_transition_message(self, received_message: bytearray) -> None:
        """
        Process unsolicited broadcast messages from the panel.

        Handles transition messages (state changes) sent by the panel without
        a request. Routes to appropriate handler based on message type. Only
        processes messages after panel_synced is True to avoid state corruption
        during initial sync.

        Args:
            received_message: Raw message bytes (msg_type + data, no length/checksum)
        """
        message_type = received_message[0] & ~0xC0
        ack_requested = bool(received_message[0] & 0x80)
        if message_type not in MessageValidLength:
            logger.error(f"Invalid message type: {message_type}")
            return
        if len(received_message) != MessageValidLength[message_type]:
            logger.error("Invalid message length for type. Discarding message.")
            return
        if self.panel_synced:
            match message_type:
                case MessageType.InterfaceConfigRsp:
                    self._process_interface_config_rsp(received_message)
                case MessageType.ZoneStatusRsp:
                    self._process_zone_status_rsp(received_message)
                case MessageType.PartitionStatusRsp:
                    self._process_partition_status_rsp(received_message)
                case MessageType.SystemStatusRsp:
                    self._process_system_status_rsp(received_message)
                case _:
                    # Message type not implemented.  ACK if requested though.
                    pass
        else:
            logger.debug("Not processing transition message during synchronization.")
        if ack_requested:  # OK to ACK even unexpected messages types
            self._send_direct_ack()
        return

    def _process_interface_config_rsp(self, message: bytearray) -> None:
        """
        Process Interface Configuration response and validate panel capabilities.

        Extracts panel firmware version, transition message flags, and request
        command flags. Validates that all required messages for proper operation
        are enabled in the panel configuration.

        Args:
            message: Interface Configuration response message bytes

        Raises:
            ControllerError: If required messages are not enabled in panel config
        """
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
        for message_type in TransitionMessageFlags:
            logger.debug(
                f"  - {message_type.name}: {bool(transition_message_flags & message_type)}"
            )

        # Log enabled command/request messages
        logger.debug("Command/request messages enabled:")
        for message_type in RequestCommandFlags:
            logger.debug(
                f"  - {message_type.name}: {bool(request_command_flags & message_type)}"
            )

        # Check for that all required messages are enabled
        required_message_disabled = False
        if not transition_message_flags & TransitionMessageFlags.InterfaceConfig:
            logger.error(
                "Interface Config Message is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not transition_message_flags & TransitionMessageFlags.ZoneStatus:
            logger.error(
                "Zone Status Message is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not transition_message_flags & TransitionMessageFlags.PartitionStatus:
            logger.error(
                "Partition Status Message is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not transition_message_flags & TransitionMessageFlags.PartitionSnapshot:
            logger.error(
                "Partition Snapshot Message is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not transition_message_flags & TransitionMessageFlags.SystemStatus:
            logger.error(
                "System Status Message is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & RequestCommandFlags.InterfaceConfig:
            logger.error(
                "Interface Config Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & RequestCommandFlags.ZoneName:
            logger.error(
                "Zone Name Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & RequestCommandFlags.ZoneStatus:
            logger.error(
                "Zone Status Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & RequestCommandFlags.ZoneSnapshot:
            logger.error(
                "Zone Snapshot Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & RequestCommandFlags.PartitionStatus:
            logger.error(
                "Partition Status Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & RequestCommandFlags.PartitionSnapshot:
            logger.error(
                "Partition Snapshot Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & RequestCommandFlags.SystemStatus:
            logger.error(
                "System Status Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & RequestCommandFlags.SetClockCalendar:
            logger.error(
                "Set Clock/Calendar Request is not enabled. This is required for proper operation."
            )
            required_message_disabled = True
        if not request_command_flags & RequestCommandFlags.PrimaryKeypadNoPin:
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
        """
        Process Zone Name response and create or update Zone object.

        During initial sync, creates Zone objects as names are received. After
        sync, updates existing zone names if changed. Ignores zones outside
        configured range or in ignored_zones set.

        Args:
            message: Zone Name response message bytes
        """
        # Note that we request zone names for all zones on first startup.   In the case of this handler
        #  the zone object may not yet exist, and we can instantiate if necessary.   For other zone
        #  messages the zone object should already exist.
        if len(message) != MessageValidLength[MessageType.ZoneNameRsp]:
            logger.error("Invalid zone name message.")
            return
        zone_index = panel_zone_to_server(int(message[1]))
        if zone_index > self.number_zones and zone_index not in self.ignored_zones:
            logger.debug(
                f"Zone index {zone_index} is out of range or ignored. Ignoring zone name response."
            )
            return
        zone_name = message[2:].decode("utf-8").rstrip()
        zone = Zone.get_zone_by_index(zone_index)
        if zone is None:
            logger.debug(f"Creating new zone object: Zone {zone_index} - {zone_name}")
            _zone = Zone(zone_index, zone_name)
        elif self.panel_synced:
            logger.error(
                f"Attempt to create new zone after sync has completed. Ignoring, but restart if this is intentional."
            )
        else:
            logger.info(f"Zone {zone_index} renamed from {zone.name} to {zone_name}")
            zone.name = zone_name
            zone.is_updated = True

    # noinspection PyMethodMayBeStatic
    def _process_zone_status_rsp(self, message: bytearray) -> None:
        """
        Process Zone Status response and update Zone state.

        Extracts partition mask, type mask, and condition mask from message
        and updates the corresponding Zone object. Publishes state to MQTT
        if panel is already synced.

        Args:
            message: Zone Status response message bytes
        """
        if len(message) != MessageValidLength[MessageType.ZoneStatusRsp]:
            logger.error("Invalid zone status message.")
            return
        zone_index = panel_zone_to_server(int(message[1]))
        if zone_index > self.number_zones and zone_index not in self.ignored_zones:
            logger.debug(
                f"Zone index {zone_index} is out of range or ignored. Ignoring zone status."
            )
            return
        zone = Zone.get_zone_by_index(zone_index)
        if zone is None:
            logger.error(f"Ignoring zone status. Unknown zone index: {zone_index}")
            return
        logger.debug(f"Got status for zone {zone_index} - {zone.name}.")
        partition_mask = int.from_bytes(message[2:3], byteorder="little")
        type_mask = int.from_bytes(message[3:6], byteorder="little")
        condition_mask = int.from_bytes(message[6:8], byteorder="little")
        zone.set_masks(
            partition_mask=partition_mask,
            type_mask=type_mask,
            condition_mask=condition_mask,
        )
        if self.panel_synced:
            self.mqtt_client.publish_zone_state(zone)
        return

    # noinspection PyMethodMayBeStatic
    def _process_ack(self, _message: bytearray) -> None:
        """
        Process ACK response from panel.

        Args:
            _message: ACK message bytes (unused, ACK has no data payload)
        """
        logger.debug("Got ACK in response to previous request.")

    # noinspection PyMethodMayBeStatic
    def _process_zone_snapshot_rsp(self, message: bytearray) -> None:
        """
        Process Zone Snapshot response (currently not fully implemented).

        Zone snapshots provide bulk zone state updates. This handler is a stub;
        the system relies on individual Zone Status messages for state updates.

        Args:
            message: Zone Snapshot response message bytes
        """
        # Zone snapshot processing is not implemented - individual zone status messages are used instead
        logger.info(
            "Received zone snapshot message - not currently processed, relying on individual zone status updates"
        )

        def _update_zone_attr(z: Zone, _mask: int, _start_bit: int) -> None:
            """
            Update zone attributes from snapshot data (stub implementation).

            Currently only marks zone as updated. Full implementation would
            extract faulted, bypassed, and trouble states from mask bits.

            Args:
                z: Zone to update
                _mask: Condition mask (unused in current implementation)
                _start_bit: Starting bit position (unused in current implementation)
            """
            # z.faulted = bool(get_nth_bit(mask, start_bit))
            # z.bypassed = bool(get_nth_bit(mask, start_bit + 1))
            # z.trouble = bool(get_nth_bit(mask, start_bit + 2))
            z.is_updated = True

        if len(message) != MessageValidLength[MessageType.ZonesSnapshotRsp]:
            logger.error("Invalid z snapshot message.")
            return
        zone_index = int(message[1]) * 16
        for i in range(2, len(message)):
            zone_mask = int(message[i])
            for bit in [0, 4]:
                if (zone := Zone.get_zone_by_index(zone_index)) is not None:
                    _update_zone_attr(zone, zone_mask, bit)
                else:
                    logger.debug(
                        f"Ignoring zone snapshot for unknown zone index: {zone_index}. "
                        "Restart if this zone was intentionally added."
                    )
                zone_index += 1

    # noinspection PyMethodMayBeStatic
    def _process_partition_status_rsp(self, message: bytearray) -> None:
        """
        Process Partition Status response and update Partition state.

        During sync, creates new Partition objects. After sync, updates existing
        partition condition flags (48-bit value). Publishes state to MQTT if
        panel is synced.

        Args:
            message: Partition Status response message bytes
        """
        if len(message) != MessageValidLength[MessageType.PartitionStatusRsp]:
            logger.error("Invalid partition status response message.")
            return
        partition_id = panel_partition_to_server(int(message[1]))
        partition: Optional[Partition]
        if not self.panel_synced:
            logger.debug(f"Creating new object for partition {partition_id}.")
            partition = Partition(partition_id)
        else:
            logger.debug(f"Got status for existing partition {partition_id}.")
            partition = Partition.get_partition_by_index(partition_id)
            if partition is None:
                logger.error(
                    f"Got partition status for unknown partition {partition_id}"
                )
                return

        condition_flags_low = (
            int.from_bytes(message[2:6], byteorder="little") & 0xFF_FF_FF_FF
        )
        condition_flags_high = (
            int.from_bytes(message[7:9], byteorder="little") & 0xFF_FF
        ) << 32
        partition.condition_flags = condition_flags_low | condition_flags_high
        partition.log_condition(logger.debug)
        logger.debug(f"Partition {partition.index} state is {partition.state.name}")
        if self.panel_synced:
            self.mqtt_client.publish_partition_state(partition)

    def _process_system_status_rsp(self, message: bytearray) -> None:
        """
        Process System Status response and discover active partitions.

        Extracts panel ID and partition mask (bitmask of active partitions).
        During initial sync, queues Partition Status requests for all active
        partitions. After sync, validates partition mask hasn't changed.

        Args:
            message: System Status response message bytes
        """
        if len(message) != MessageValidLength[MessageType.SystemStatusRsp]:
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
            return
        else:
            for i in range(0, 7):
                partition_bit = bool(get_nth_bit(self.partition_mask, i))
                if partition_bit:
                    valid_partition = i + 1
                    logger.info(
                        f"Partition {valid_partition} active. Queueing status request."
                    )
                    self._send_partition_status_req(valid_partition)

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
            assert isinstance(command, Command)

            # Retry command up to 3 times on timeout.
            # Processed transition message do not count toward timeout and are processed in-line.
            # Fail immediately if the command is rejected.
            retries = 3
            self._send_direct(
                command.req_msg_type, command.req_msg_data, command.request_ack
            )
            while retries > 0:
                incoming_message = self._read_message(wait=True)
                if incoming_message is None:  # Timeout
                    logger.warning(
                        f"Timeout waiting for response to {command.req_msg_type.name} message. Retrying."
                    )
                    retries -= 1
                    self._send_direct(
                        command.req_msg_type, command.req_msg_data, command.request_ack
                    )
                    continue
                incoming_message_type_byte = incoming_message[0] & 0b001111111
                incoming_message_is_acked = bool(incoming_message[0] & 0b10000000)
                try:
                    incoming_message_type = MessageType(incoming_message_type_byte)
                except ValueError:
                    logger.critical(
                        f"Unknown incoming message type: {incoming_message_type_byte:02x}"
                    )
                    continue

                # Panel did not like our message.   Don't resend.
                if incoming_message_type in (
                    MessageType.Rejected,
                    MessageType.Failed,
                    MessageType.NACK,
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

    def _send_request_to_queue(self, command: Command) -> None:
        """
        Add a command to the processing queue.

        Args:
            command: Command object containing request and response handler
        """
        self._command_queue.put(command)
        return

    def _send_direct(
        self,
        message_type: MessageType,
        message_data: Optional[bytearray],
        request_ack: bool = False,
    ) -> None:
        """
        Send a message directly to the panel via serial port.

        Constructs message with length byte, message type, optional data, and
        Fletcher-16 checksum. Applies byte stuffing (0x7E → 0x7D 0x5E, 0x7D →
        0x7D 0x5D) and adds start byte (0x7E). Sets ACK bit (0x80) in message
        type if requested.

        Args:
            message_type: Message type identifier
            message_data: Optional message payload bytes
            request_ack: If True, sets bit 0x80 in message type to request ACK
        """
        message_length = 1 + len(message_data) if message_data else 1
        if message_type not in MessageValidLength:
            logger.error(f"Unsupported message type: {message_type:02x}")
            return
        if not message_length == MessageValidLength[message_type]:
            logger.error(
                f"Invalid message length for message type {message_type.name}. "
                f"Expected {MessageValidLength[message_type]}, got {message_length}."
            )
            return
        if request_ack:
            message_type = message_type | 0x80
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

    def _send_direct_ack(self) -> None:
        """
        Send ACK message to panel after brief delay.

        Used to acknowledge transition messages that have the ACK-requested bit set.
        """
        time.sleep(ACK_DELAY_SECONDS)
        self._send_direct(MessageType.ACK, None)

    def _send_direct_nack(self) -> None:
        """Send NACK message to panel (currently unused)."""
        self._send_direct(MessageType.NACK, None)

    def _send_interface_configuration_req(self) -> None:
        """
        Queue Interface Configuration request to validate panel capabilities.

        Used during initial sync to verify panel supports all required message types.
        """
        logger.debug(f"Queuing interface configuration request")
        command = Command(
            MessageType.InterfaceConfigReq,
            None,
            {MessageType.InterfaceConfigRsp: self._process_interface_config_rsp},
        )
        self._send_request_to_queue(command)

    def _send_zone_name_req(self, zone: int) -> None:
        """
        Queue Zone Name request for specified zone.

        Args:
            zone: Server zone index (1-based)
        """
        logger.debug(f"Queuing zone name request for zone {zone}")
        zone_index = server_zone_to_panel(zone)
        command = Command(
            MessageType.ZoneNameReq,
            bytearray(zone_index.to_bytes(1, byteorder="little")),
            {MessageType.ZoneNameRsp: self._process_zone_name_rsp},
        )
        self._send_request_to_queue(command)

    def _send_zone_status_req(self, zone: int) -> None:
        """
        Queue Zone Status request for specified zone.

        Args:
            zone: Server zone index (1-based)
        """
        logger.debug(f"Queuing zone status request for zone {zone}")
        zone_index = server_zone_to_panel(zone)
        command = Command(
            MessageType.ZoneStatusReq,
            bytearray(zone_index.to_bytes(1, byteorder="little")),
            {MessageType.ZoneStatusRsp: self._process_zone_status_rsp},
        )
        self._send_request_to_queue(command)

    def _send_partition_status_req(self, partition: int) -> None:
        """
        Queue Partition Status request for specified partition.

        Args:
            partition: Server partition index (1-8)
        """
        logger.debug(f"Queuing partition {partition} status request.")
        assert 1 <= partition <= 8
        partition_index = server_partition_to_panel(partition)
        command = Command(
            MessageType.PartitionStatusReq,
            bytearray(partition_index.to_bytes(1, byteorder="little")),
            {MessageType.PartitionStatusRsp: self._process_partition_status_rsp},
        )
        self._send_request_to_queue(command)

    def _send_system_status_req(self) -> None:
        """
        Queue System Status request to discover active partitions.

        Used during initial sync to get partition bitmask from panel.
        """
        logger.debug(f"Queuing system status request")
        command = Command(
            MessageType.SystemStatusReq,
            None,
            {MessageType.SystemStatusRsp: self._process_system_status_rsp},
        )
        self._send_request_to_queue(command)

    def send_set_clock_req(self) -> None:
        """
        Queue Set Clock/Calendar request to synchronize panel time.

        Sends current system time to panel. Weekday is corrected for difference
        between Python's tm_wday (0=Monday) and panel expectation (1=Monday).
        """
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
        logger.debug(f"Queuing set clock/date request")
        command = Command(
            MessageType.SetClockCalendar,
            message,
            {MessageType.ACK: self._process_ack},
        )
        self._send_request_to_queue(command)

    def send_primary_keypad_function_wo_pin(
        self, partition: Partition, function: PrimaryKeypadFunctions
    ) -> None:
        """
        Queue Primary Keypad Function command without PIN.

        Uses default_user number for authentication. Requires panel to be
        configured to allow PIN-less operations for the specified user.

        Args:
            partition: Partition to operate on
            function: Keypad function to perform (Disarm, ArmAway, ArmStay, etc.)
        """
        message = bytearray()
        message.append(function.value)
        partition_mask = 1 << (partition.index - 1)
        message.append(partition_mask)
        message.append(int(self.default_user))  # Default to User 1 for now.
        logger.debug(
            "Queuing send primary keypad function wo PIN with function "
            f"{function.name} on partition {partition.index}"
        )
        command = Command(
            MessageType.PrimaryKeypadFuncNoPin,
            message,
            {MessageType.ACK: self._process_ack},
            request_ack=True,
        )
        self._send_request_to_queue(command)

    def send_primary_keypad_function_w_pin(
        self, partition: Partition, function: PrimaryKeypadFunctions
    ) -> None:
        """
        Queue Primary Keypad Function command with PIN authentication.

        Uses default_code PIN for authentication. PIN is BCD-encoded before sending.

        Args:
            partition: Partition to operate on
            function: Keypad function to perform (Disarm, ArmAway, ArmStay, etc.)
        """
        message = bytearray()
        pin_array = pin_to_bytearray(self.default_code)
        message.extend(pin_array)
        message.append(function.value)
        partition_mask = 1 << (partition.index - 1)
        message.append(partition_mask)
        logger.debug(
            "Queuing send primary keypad function with PIN with function "
            f"{function.name} on partition {partition.index}"
        )
        command = Command(
            MessageType.PrimaryKeypadFuncPin,
            message,
            {MessageType.ACK: self._process_ack},
            request_ack=True,
        )
        self._send_request_to_queue(command)

    def send_primary_keypad_function(
        self, partition: Partition, function: PrimaryKeypadFunctions
    ) -> None:
        """
        Queue Primary Keypad Function using configured authentication method.

        Automatically chooses PIN or user-based authentication based on which
        default is configured (default_code takes precedence).

        Args:
            partition: Partition to operate on
            function: Keypad function to perform (Disarm, ArmAway, ArmStay, etc.)
        """
        if self.default_code is not None:
            self.send_primary_keypad_function_w_pin(partition, function)
        elif self.default_user is not None:
            self.send_primary_keypad_function_wo_pin(partition, function)
        else:
            logger.error(
                f"Attempt to do primary keypad function on partition {partition.index} when no default code or user set"
            )

    def send_disarm(self, partition: Partition) -> None:
        """
        Send disarm command to specified partition.

        Args:
            partition: Partition to disarm
        """
        if partition.state == Partition.State.DISARMED:
            logger.error(
                f"Attempt to disarm partition {partition.index} that is already disarmed."
            )
            return
        self.send_primary_keypad_function(partition, PrimaryKeypadFunctions.Disarm)

    def send_arm_home(self, partition: Partition) -> None:
        """
        Send arm stay (home) command to specified partition.

        Args:
            partition: Partition to arm in stay/home mode
        """
        if (
            (partition.state == Partition.State.ARMED_HOME)
            or (partition.state == Partition.State.ARMED_AWAY)
            or (partition.state == Partition.State.ARMING)
        ):
            logger.error(
                f"Attempt to arm home partition {partition.index} that is already armed or is arming."
            )
        self.send_primary_keypad_function(partition, PrimaryKeypadFunctions.ArmStay)

    def send_arm_away(self, partition: Partition) -> None:
        """
        Send arm away command to specified partition.

        Args:
            partition: Partition to arm in away mode
        """
        if (
            (partition.state == Partition.State.ARMED_HOME)
            or (partition.state == Partition.State.ARMED_AWAY)
            or (partition.state == Partition.State.ARMING)
        ):
            logger.error(
                f"Attempt to arm home partition {partition.index} that is already armed or is arming."
            )
        self.send_primary_keypad_function(partition, PrimaryKeypadFunctions.ArmAway)

    def _db_sync_start0(self) -> None:
        """
        Initialize and queue all commands for panel state synchronization.

        Queues the following sequence:
        1. Interface Configuration request (validates panel capabilities)
        2. System Status request (discovers active partitions)
        3. Zone Name and Zone Status requests for all configured zones
           (excluding ignored zones)

        All queued commands are processed sequentially by _process_command_queue().
        """
        self.panel_synced = False

        # Do Interface Configuration Request to ensure that panel interface is configured correctly.
        #  May throw exception if not.  Handled in control loop.
        self._send_interface_configuration_req()

        # Do System Status Request to find valid partitions.  The response will trigger Partition Status Requests
        #  for valid partitions in its handler.
        self._send_system_status_req()

        # Get all the zone information up to self.number_zones.
        for zone_number in range(1, (self.number_zones + 1)):
            if zone_number not in self.ignored_zones:
                self._send_zone_name_req(zone_number)
                self._send_zone_status_req(zone_number)
            else:
                logger.debug(f"Not requesting zone {zone_number}. Ignored")
        return
