"""Tests for the codec module."""

import pytest

from pytronikon.codec import (
    Answer,
    Selector,
    decode_raw_value,
    format_selector,
    normalize_selector,
    read_byte,
    read_int16,
    read_int32,
    read_uint16,
    read_uint32,
    split_aligned_answers,
)
from pytronikon.errors import InvalidSelectorError, ResponseAlignmentError


def test_format_selector():
    """Test formatting a selector as a hex string."""
    assert format_selector(0x3002, 0x01) == "300201"
    assert format_selector(0x300E, 0x18) == "300e18"


def test_format_selector_invalid_index():
    """Test that invalid index raises error."""
    with pytest.raises(InvalidSelectorError):
        format_selector(-1, 0x01)

    with pytest.raises(InvalidSelectorError):
        format_selector(0x10000, 0x01)


def test_format_selector_invalid_subindex():
    """Test that invalid subindex raises error."""
    with pytest.raises(InvalidSelectorError):
        format_selector(0x3002, -1)

    with pytest.raises(InvalidSelectorError):
        format_selector(0x3002, 0x100)


def test_normalize_selector_from_hex_string():
    """Test normalizing a 6-character hex string."""
    result = normalize_selector("300201")
    assert isinstance(result, Selector)
    assert result.key == "300201"
    assert result.index == 0x3002
    assert result.subindex == 0x01


def test_normalize_selector_from_pair_format():
    """Test normalizing a pair format string."""
    result = normalize_selector("0x3002:1")
    assert result.key == "300201"
    assert result.index == 0x3002
    assert result.subindex == 0x01

    result2 = normalize_selector("3002:01")
    assert result2.key == "300201"


def test_normalize_selector_from_dict():
    """Test normalizing a dict."""
    result = normalize_selector({"index": 0x3002, "subindex": 1})
    assert result.key == "300201"
    assert result.index == 0x3002
    assert result.subindex == 0x01


def test_normalize_selector_from_tuple():
    """Test normalizing a tuple."""
    result = normalize_selector((0x3002, 1))
    assert result.key == "300201"


def test_normalize_selector_from_selector():
    """Test normalizing a Selector object (should return as-is)."""
    sel = Selector(key="300201", index=0x3002, subindex=0x01)
    result = normalize_selector(sel)
    assert result is sel


def test_normalize_selector_invalid():
    """Test that invalid selectors raise error."""
    with pytest.raises(InvalidSelectorError):
        normalize_selector("3002")  # Too short

    with pytest.raises(InvalidSelectorError):
        normalize_selector("GGGGGG")  # Invalid hex

    with pytest.raises(InvalidSelectorError):
        normalize_selector(12345)  # Wrong type


def test_split_aligned_answers_basic():
    """Test parsing aligned answers."""
    selectors = [
        Selector(key="300201", index=0x3002, subindex=0x01),
        Selector(key="300301", index=0x3003, subindex=0x01),
        Selector(key="300302", index=0x3003, subindex=0x02),
    ]
    response = "1B520080X00010080"

    answers = split_aligned_answers(selectors, response)

    assert len(answers) == 3
    assert answers[0].raw == "1B520080"
    assert answers[1].raw == "X"
    assert answers[2].raw == "00010080"


def test_split_aligned_answers_trailing_data():
    """Test that trailing data raises error."""
    selectors = [Selector(key="300201", index=0x3002, subindex=0x01)]
    response = "1B520080FFFF"  # 4 extra chars

    with pytest.raises(ResponseAlignmentError):
        split_aligned_answers(selectors, response)


def test_split_aligned_answers_incomplete():
    """Test that incomplete response raises error."""
    selectors = [
        Selector(key="300201", index=0x3002, subindex=0x01),
        Selector(key="300301", index=0x3003, subindex=0x01),
    ]
    response = "1B520080"  # Only 1 of 2 answers

    with pytest.raises(ResponseAlignmentError):
        split_aligned_answers(selectors, response)


def test_split_aligned_answers_malformed():
    """Test that malformed answers raise error."""
    selectors = [Selector(key="300201", index=0x3002, subindex=0x01)]
    response = "1B52008G"  # Invalid hex char

    with pytest.raises(ResponseAlignmentError):
        split_aligned_answers(selectors, response)


def test_read_uint32():
    """Test reading a 32-bit unsigned integer."""
    assert read_uint32("00000000") == 0
    assert read_uint32("FFFFFFFF") == 4294967295
    assert read_uint32("12345678") == 0x12345678


def test_read_int32():
    """Test reading a 32-bit signed integer."""
    assert read_int32("00000000") == 0
    assert read_int32("FFFFFFFF") == -1
    assert read_int32("80000000") == -2147483648
    assert read_int32("7FFFFFFF") == 2147483647


def test_read_uint16():
    """Test reading a 16-bit unsigned integer from a word."""
    # Word 0 is the low word (bits 0-15, chars 4-8 of the 8-char string)
    # Word 1 is the high word (bits 16-31, chars 0-4)
    raw = "12345678"
    assert read_uint16(raw, 0) == 0x5678
    assert read_uint16(raw, 1) == 0x1234


def test_read_int16():
    """Test reading a 16-bit signed integer from a word."""
    # Negative number in word 0
    raw = "FFFF0000"
    assert read_int16(raw, 0) == 0
    assert read_int16(raw, 1) == -1


def test_read_byte():
    """Test reading a single byte from a raw value."""
    # Bytes are indexed 0-3, where byte 0 is the low byte
    raw = "12345678"
    assert read_byte(raw, 0) == 0x78  # Low byte
    assert read_byte(raw, 1) == 0x56
    assert read_byte(raw, 2) == 0x34
    assert read_byte(raw, 3) == 0x12  # High byte


def test_decode_raw_value_missing():
    """Test decoding a missing value."""
    decoded = decode_raw_value("X")
    assert decoded.missing is True
    assert decoded.raw == "X"
    assert decoded.uint32 is None


def test_decode_raw_value_present():
    """Test decoding a present value."""
    decoded = decode_raw_value("1B520080")
    assert decoded.missing is False
    assert decoded.raw == "1B520080"
    assert decoded.uint32 == 0x1B520080
    assert decoded.uint16_word1 == 0x1B52
    assert decoded.uint16_word0 == 0x0080
    assert decoded.int16_word1 == 0x1B52
    assert decoded.bytes == [0x80, 0x00, 0x52, 0x1B]


def test_decode_raw_value_sign_extension():
    """Test sign extension in decoded values."""
    decoded = decode_raw_value("FFFFFFFF")
    assert decoded.int32 == -1
    assert decoded.int16_word0 == -1
    assert decoded.int16_word1 == -1

    decoded2 = decode_raw_value("80000000")
    assert decoded2.int32 == -2147483648
