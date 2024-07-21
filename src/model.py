from enum import IntEnum
from typing import NamedTuple, Dict, Callable, Optional
from types import MappingProxyType


class MessageType(IntEnum):
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
    req_msg_type: MessageType
    req_msg_data: Optional[bytearray] = None
    response_handler: Optional[Dict[MessageType, Callable[[bytearray], None]]] = None
    request_ack: bool = False


# Interface Configuration (Response) constants
class TransitionMessageFlags(IntEnum):
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


class PartitionConditionFlags(IntEnum):
    # User code required to bypass zones.
    BypassCodeRequired = 0b_00000000_00000000_00000000_00000000_00000000_00000001
    # Fire trouble.
    FireTrouble = 0b_00000000_00000000_00000000_00000000_00000000_00000010
    # Fire alarm.
    Fire = 0b_00000000_00000000_00000000_00000000_00000000_00000100
    # Pulsing buzzer.
    PulsingBuzzer = 0b_00000000_00000000_00000000_00000000_00000000_00001000
    # TLM (Telephone Line Monitoring) fault memory.
    TLMFaultMemory = 0b_00000000_00000000_00000000_00000000_00000000_00010000
    # Armed.
    Armed = 0b_00000000_00000000_00000000_00000000_00000000_01000000
    # Instant.
    Instant = 0b_00000000_00000000_00000000_00000000_00000000_10000000
    # Previous alarm.
    PreviousAlarm = 0b_00000000_00000000_00000000_00000000_00000001_00000000
    # Siren on.
    SirenOn = 0b_00000000_00000000_00000000_00000000_00000010_00000000
    # Steady siren on.
    SteadySirenOn = 0b_00000000_00000000_00000000_00000000_00000100_00000000
    # Alarm memory.
    AlarmMemory = 0b_00000000_00000000_00000000_00000000_00001000_00000000
    # Tamper.
    Tamper = 0b_00000000_00000000_00000000_00000000_00010000_00000000
    # Cancel entered.
    CancelEntered = 0b_00000000_00000000_00000000_00000000_00100000_00000000
    # Code entered.
    CodeEntered = 0b_00000000_00000000_00000000_00000000_01000000_00000000
    # Cancel pending.
    CancelPending = 0b_00000000_00000000_00000000_00000000_10000000_00000000
    # Silent exit enabled.
    SilentExitEnabled = 0b_00000000_00000000_00000000_00000010_00000000_00000000
    # Entryguard.
    Entryguard = 0b_00000000_00000000_00000000_00000100_00000000_00000000
    # Chime mode.
    ChimeMode = 0b_00000000_00000000_00000000_00001000_00000000_00000000
    # Entry.
    Entry = 0b_00000000_00000000_00000000_00010000_00000000_00000000
    # Delay expiration warning.
    DelayExpirationWarn = 0b_00000000_00000000_00000000_00100000_00000000_00000000
    # Exit 1.
    Exit1 = 0b_00000000_00000000_00000000_01000000_00000000_00000000
    # Exit 2.
    Exit2 = 0b_00000000_00000000_00000000_10000000_00000000_00000000
    # LED extinguish.
    LEDExtinguish = 0b_00000000_00000000_00000001_00000000_00000000_00000000
    # Cross timing.
    CrossTiming = 0b_00000000_00000000_00000010_00000000_00000000_00000000
    # Recent close being timed.
    RecentCloseTimed = 0b_00000000_00000000_00000100_00000000_00000000_00000000
    # Exit error triggered.
    ExitErrorTriggered = 0b_00000000_00000000_00010000_00000000_00000000_00000000
    # Auto home inhibited.
    AutoHomeInhibited = 0b_00000000_00000000_00100000_00000000_00000000_00000000
    # Sensor low battery.
    SensorLowBattery = 0b_00000000_00000000_01000000_00000000_00000000_00000000
    # Sensor lost supervision.
    SensorLostSupervision = 0b_00000000_00000000_10000000_00000000_00000000_00000000
    # Zone bypassed.
    ZoneBypassed = 0b_00000000_00000001_00000000_00000000_00000000_00000000
    # Force arm triggered.
    ForceArmTriggered = 0b_00000000_00000010_00000000_00000000_00000000_00000000
    # Ready to arm.
    ReadyToArm = 0b_00000000_00000100_00000000_00000000_00000000_00000000
    # Ready to force arm.
    ReadyToForceArm = 0b_00000000_00001000_00000000_00000000_00000000_00000000
    # Valid PIN accepted.
    ValidPINAccepted = 0b_00000000_00010000_00000000_00000000_00000000_00000000
    # Chime on (sounding).
    ChimeOn = 0b_00000000_00100000_00000000_00000000_00000000_00000000
    # Error beep (triple beep).
    ErrorBeep = 0b_00000000_01000000_00000000_00000000_00000000_00000000
    # Tone on (activation tone).
    ToneOn = 0b_00000000_10000000_00000000_00000000_00000000_00000000
    # Entry 1.
    Entry1 = 0b_00000001_00000000_00000000_00000000_00000000_00000000
    # Open period.
    OpenPeriod = 0b_00000010_00000000_00000000_00000000_00000000_00000000
    # Alarm sent using phone 1.
    AlarmSentPhone1 = 0b_00000100_00000000_00000000_00000000_00000000_00000000
    # Alarm sent using phone 2.
    AlarmSentPhone2 = 0b_00001000_00000000_00000000_00000000_00000000_00000000
    # Alarm sent using phone 3.
    AlarmSentPhone3 = 0b_00010000_00000000_00000000_00000000_00000000_00000000
    # Cancel report is in the stack.
    CancelInStack = 0b_00100000_00000000_00000000_00000000_00000000_00000000
    # Keyswitch armed.
    KeyswitchArmed = 0b_01000000_00000000_00000000_00000000_00000000_00000000
    # Delay trip in progress.
    DelayTripInProgress = 0b_10000000_00000000_00000000_00000000_00000000_00000000


class ZoneTypeFlags(IntEnum):
    Fire = 0b_00000000_00000000_00000001  # Zone is a fire zone.
    Hour24 = 0b_00000000_00000000_00000010  # Zone is a 24-hour zone.
    KeySwitch = 0b_00000000_00000000_00000100  # Zone is a keyswitch zone.
    Follower = 0b_00000000_00000000_00001000  # Zone is a follower zone.
    EntryExitDelay1 = (
        0b_00000000_00000000_00010000  # Zone is an entry/exit delay 1 zone.
    )
    EntryExitDelay2 = (
        0b_00000000_00000000_00100000  # Zone is an entry/exit delay 2 zone.
    )
    Interior = 0b_00000000_00000000_01000000  # Zone is an interior zone.
    LocalOnly = 0b_00000000_00000000_10000000  # Zone is local only.
    KeypadSounder = 0b_00000000_00000001_00000000  # Zone is a keypad sounder zone.
    YelpingSiren = 0b_00000000_00000010_00000000  # Zone is a yelping siren zone.
    SteadySiren = 0b_00000000_00000100_00000000  # Zone is a steady siren zone.
    Chime = 0b_00000000_00001000_00000000  # Zone is a chime zone.
    Bypassable = 0b_00000000_00010000_00000000  # Zone is bypassable.
    GroupBypassable = 0b_00000000_00100000_00000000  # Zone is group bypassable.
    ForceArmable = 0b_00000000_01000000_00000000  # Zone is force armable.
    EntryGuard = 0b_00000000_10000000_00000000  # Zone is an entry guard zone.
    FastLoopResponse = (
        0b_00000001_00000000_00000000  # Zone is a fast loop response zone.
    )
    DoubleEOLTamper = 0b_00000010_00000000_00000000  # Zone is a double EOL tamper zone.
    Trouble = 0b_00000100_00000000_00000000  # Zone is a trouble zone.
    CrossZone = 0b_00001000_00000000_00000000  # Zone is a cross zone.
    DialerDelay = 0b_00010000_00000000_00000000  # Zone is a dialer delay zone.
    SwingerShutdown = 0b_00100000_00000000_00000000  # Zone is a swinger shutdown zone.
    Restorable = 0b_01000000_00000000_00000000  # Zone is restorable.
    ListenIn = 0b_10000000_00000000_00000000  # Zone is a listen-in zone.


class ZoneConditionFlags(IntEnum):
    Faulted = 0b_00000000_00000001  # Zone is faulted (aka "triggered").
    Tampered = 0b_00000000_00000010  # Zone is tampered.
    Trouble = 0b_00000000_00000100  # Zone showing trouble state.
    Bypassed = 0b_00000000_00001000  # Zone is bypassed.
    Inhibited = 0b_00000000_00010000  # Zone is inhibited.
    LowBattery = 0b_00000000_00100000  # Zone has low battery.
    SupervisionLost = 0b_00000000_01000000  # Zone has lost supervision.
    AlarmMemory = 0b_00000001_00000000  # Zone triggered the last alarm event.
    BypassMemory = (
        0b_00000010_00000000  # Zone was bypassed during the last alarm event.
    )


class PrimaryKeypadFunctions(IntEnum):
    TurnOffAlarm = 0x00
    Disarm = 0x01
    ArmAway = 0x02
    ArmStay = 0x03
    Cancel = 0x04
    InitiateAutoArm = 0x05
    StartWalkTest = 0x06
    StopWalkTest = 0x07
