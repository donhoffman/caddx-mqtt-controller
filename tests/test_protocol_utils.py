"""Tests for protocol utility functions."""
import pytest
from caddx_controller import get_nth_bit, pin_to_bytearray, CaddxController


class TestGetNthBit:
    """Tests for bit extraction utility."""

    def test_get_bit_0(self):
        assert get_nth_bit(0b10101010, 0) == 0
        assert get_nth_bit(0b10101011, 0) == 1

    def test_get_bit_7(self):
        assert get_nth_bit(0b10000000, 7) == 1
        assert get_nth_bit(0b01111111, 7) == 0

    def test_get_bit_middle(self):
        assert get_nth_bit(0b00010000, 4) == 1
        assert get_nth_bit(0b11101111, 4) == 0

    def test_get_bit_all_zeros(self):
        assert get_nth_bit(0b00000000, 3) == 0

    def test_get_bit_all_ones(self):
        assert get_nth_bit(0b11111111, 3) == 1

    def test_get_bit_large_number(self):
        # Test with 32-bit number
        num = 0b10000000_00000000_00000000_00000001
        assert get_nth_bit(num, 0) == 1
        assert get_nth_bit(num, 31) == 1
        assert get_nth_bit(num, 15) == 0


class TestPinToBytearray:
    """Tests for PIN encoding function."""

    def test_4_digit_pin(self):
        result = pin_to_bytearray("1234")
        assert len(result) == 3
        assert result[0] == 0x12
        assert result[1] == 0x34
        assert result[2] == 0x00

    def test_6_digit_pin(self):
        result = pin_to_bytearray("123456")
        assert len(result) == 3
        assert result[0] == 0x12
        assert result[1] == 0x34
        assert result[2] == 0x56

    def test_all_zeros(self):
        result = pin_to_bytearray("0000")
        assert result == bytearray([0x00, 0x00, 0x00])

    def test_all_nines(self):
        result = pin_to_bytearray("9999")
        assert result == bytearray([0x99, 0x99, 0x00])

    def test_invalid_length_too_short(self):
        with pytest.raises(ValueError, match="PIN must be 4 or 6 characters long"):
            pin_to_bytearray("123")

    def test_invalid_length_too_long(self):
        with pytest.raises(ValueError, match="PIN must be 4 or 6 characters long"):
            pin_to_bytearray("1234567")

    def test_invalid_length_five(self):
        with pytest.raises(ValueError, match="PIN must be 4 or 6 characters long"):
            pin_to_bytearray("12345")

    def test_non_numeric_characters(self):
        # Should raise ValueError from int() conversion
        with pytest.raises(ValueError):
            pin_to_bytearray("12ab")

    def test_empty_string(self):
        with pytest.raises(ValueError, match="PIN must be 4 or 6 characters long"):
            pin_to_bytearray("")


class TestFletcher16Checksum:
    """Tests for Fletcher-16 checksum calculation."""

    def test_empty_bytearray(self):
        result = CaddxController._calculate_fletcher16(bytearray())
        assert result == 0x0000

    def test_single_byte(self):
        result = CaddxController._calculate_fletcher16(bytearray([0x01]))
        assert result == 0x0101

    def test_two_bytes(self):
        result = CaddxController._calculate_fletcher16(bytearray([0x01, 0x02]))
        # sum1 = (0 + 1) % 255 = 1
        # sum2 = (0 + 1) % 255 = 1
        # sum1 = (1 + 2) % 255 = 3
        # sum2 = (1 + 3) % 255 = 4
        assert result == 0x0403

    def test_known_value_from_protocol(self):
        # Test with actual message from protocol
        # Interface Config Request: length=0x01, msg type=0x21
        data = bytearray([0x01, 0x21])
        result = CaddxController._calculate_fletcher16(data)
        # This should match the checksum in actual protocol messages
        # sum1 = (0 + 1) % 255 = 1, sum2 = (0 + 1) % 255 = 1
        # sum1 = (1 + 33) % 255 = 34, sum2 = (1 + 34) % 255 = 35
        assert result == 0x2322

    def test_all_zeros(self):
        result = CaddxController._calculate_fletcher16(bytearray([0x00, 0x00, 0x00]))
        assert result == 0x0000

    def test_all_ones(self):
        result = CaddxController._calculate_fletcher16(bytearray([0xFF, 0xFF]))
        # sum1 = (0 + 255) % 255 = 0
        # sum2 = (0 + 0) % 255 = 0
        # sum1 = (0 + 255) % 255 = 0
        # sum2 = (0 + 0) % 255 = 0
        assert result == 0x0000

    def test_modulo_wraparound(self):
        # Test that modulo 255 is applied correctly
        data = bytearray([255, 255, 1])
        result = CaddxController._calculate_fletcher16(data)
        # sum1: 0->0->0->1, sum2: 0->0->0->1
        assert result == 0x0101

    def test_checksum_deterministic(self):
        # Same input should always give same output
        data = bytearray([0x12, 0x34, 0x56])
        result1 = CaddxController._calculate_fletcher16(data)
        result2 = CaddxController._calculate_fletcher16(data)
        assert result1 == result2