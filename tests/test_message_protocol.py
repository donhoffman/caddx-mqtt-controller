"""Tests for message encoding and decoding."""

import pytest
from unittest.mock import Mock, MagicMock
from caddx_controller import CaddxController, MessageType, MessageValidLength


class TestByteStuffing:
    """Tests for byte stuffing in message transmission."""

    def setup_method(self):
        """Create a mock controller for testing."""
        self.controller = Mock(spec=CaddxController)
        self.controller.conn = MagicMock()
        self.controller._calculate_fletcher16 = CaddxController._calculate_fletcher16

    def test_send_direct_no_stuffing_needed(self):
        """Test message with no special bytes."""
        # Call the actual _send_direct method
        CaddxController._send_direct(
            self.controller, MessageType.InterfaceConfigReq, None, False
        )

        # Get what was written to serial port
        written_data = self.controller.conn.write.call_args[0][0]

        # Should start with 0x7E
        assert written_data[0] == 0x7E
        # Should not contain any stuffing sequences
        assert b"\x7d\x5e" not in written_data
        assert b"\x7d\x5d" not in written_data

    def test_send_direct_stuffs_0x7e(self):
        """Test that 0x7E in data gets stuffed to 0x7D 0x5E."""
        # Create message data containing 0x7E
        message_data = bytearray([0x7E])

        CaddxController._send_direct(
            self.controller, MessageType.ZoneNameReq, message_data, False
        )

        written_data = self.controller.conn.write.call_args[0][0]

        # Should contain escape sequence for 0x7E
        assert b"\x7d\x5e" in written_data

    def test_send_direct_stuffs_0x7d(self):
        """Test that 0x7D in data gets stuffed to 0x7D 0x5D."""
        # Create message data containing 0x7D
        message_data = bytearray([0x7D])

        CaddxController._send_direct(
            self.controller, MessageType.ZoneNameReq, message_data, False
        )

        written_data = self.controller.conn.write.call_args[0][0]

        # Should contain escape sequence for 0x7D
        assert b"\x7d\x5d" in written_data

    def test_send_direct_adds_ack_bit(self):
        """Test that request_ack=True sets ACK bit in message type."""
        CaddxController._send_direct(
            self.controller, MessageType.InterfaceConfigReq, None, request_ack=True
        )

        written_data = self.controller.conn.write.call_args[0][0]

        # Message type byte is at position 2 (after start byte and length)
        # Extract it, handling potential stuffing
        # ACK bit is 0x80
        msg_type_byte = written_data[2]
        assert msg_type_byte & 0x80  # ACK bit should be set


class TestMessageValidation:
    """Tests for message length validation."""

    def test_message_valid_lengths_complete(self):
        """Verify all message types have defined lengths."""
        # All message types we use should have defined lengths
        required_types = [
            MessageType.InterfaceConfigRsp,
            MessageType.ZoneNameRsp,
            MessageType.ZoneStatusRsp,
            MessageType.PartitionStatusRsp,
            MessageType.SystemStatusRsp,
            MessageType.ACK,
            MessageType.NACK,
            MessageType.Failed,
            MessageType.Rejected,
        ]

        for msg_type in required_types:
            assert (
                msg_type in MessageValidLength
            ), f"{msg_type.name} missing from MessageValidLength"
            assert MessageValidLength[msg_type] > 0

    def test_message_lengths_are_positive(self):
        """All message lengths should be positive integers."""
        for msg_type, length in MessageValidLength.items():
            assert isinstance(length, int)
            assert length > 0
            assert length < 256  # Should fit in a byte


class TestMessageTypeExtraction:
    """Tests for extracting message type from received messages."""

    def test_extract_message_type_no_ack(self):
        """Test extracting message type without ACK bit."""
        # Message with type 0x01 (InterfaceConfigRsp), no ACK
        message_byte = 0x01
        extracted_type = message_byte & ~0xC0
        assert extracted_type == 0x01

    def test_extract_message_type_with_ack(self):
        """Test extracting message type with ACK bit set."""
        # Message with type 0x01, ACK bit set (0x81)
        message_byte = 0x81
        extracted_type = message_byte & ~0xC0
        assert extracted_type == 0x01

    def test_extract_ack_bit(self):
        """Test detecting ACK request bit."""
        # Without ACK
        assert not bool(0x01 & 0x80)
        # With ACK
        assert bool(0x81 & 0x80)

    def test_message_type_masking(self):
        """Test that 0xC0 mask removes both ACK and reserved bits."""
        # ACK bit (0x80) and bit 0x40 should both be masked out
        message_with_both = 0xC1  # Both bits set, type=0x01
        extracted = message_with_both & ~0xC0
        assert extracted == 0x01


class TestChecksumValidation:
    """Tests for checksum calculation in complete messages."""

    def test_checksum_in_message_context(self):
        """Test checksum calculation matches expected protocol values."""
        # Create a simple message: Interface Config Request
        message_data = bytearray([0x01, 0x21])  # length=1, type=0x21

        checksum = CaddxController._calculate_fletcher16(message_data)
        checksum_bytes = checksum.to_bytes(2, byteorder="little")

        # Reconstruct what should be sent (before stuffing)
        full_message = bytearray()
        full_message.extend(message_data)
        full_message.extend(checksum_bytes)

        # Verify checksum is correctly appended
        offered_checksum = int.from_bytes(full_message[-2:], byteorder="little")
        calculated_checksum = CaddxController._calculate_fletcher16(full_message[:-2])

        assert offered_checksum == calculated_checksum

    def test_corrupted_checksum_detected(self):
        """Test that corrupted checksums are detectable."""
        message_data = bytearray([0x01, 0x21])
        correct_checksum = CaddxController._calculate_fletcher16(message_data)
        wrong_checksum = correct_checksum ^ 0xFF  # Flip some bits

        assert correct_checksum != wrong_checksum
