"""Codec for encoding/decoding selectors and response values."""

import re
from dataclasses import dataclass
from typing import Any

from pytronikon.errors import InvalidSelectorError, ResponseAlignmentError


def hex_str(value: int, length: int) -> str:
    """Format an integer as a hex string of the given length."""
    return format(value, f"0{length}x")


def format_selector(index: int, subindex: int) -> str:
    """Format a selector as a 6-character hex string.

    Args:
        index: 16-bit object index.
        subindex: 8-bit subindex.

    Returns:
        A 6-character hex string in the format IIIICC where I is index, C is subindex.

    Raises:
        InvalidSelectorError: If index or subindex are out of range.
    """
    if not isinstance(index, int) or index < 0 or index > 0xFFFF:
        raise InvalidSelectorError(
            {"index": index, "subindex": subindex},
            "index must be a 16-bit integer",
        )
    if not isinstance(subindex, int) or subindex < 0 or subindex > 0xFF:
        raise InvalidSelectorError(
            {"index": index, "subindex": subindex},
            "subindex must be an 8-bit integer",
        )
    return f"{hex_str(index, 4)}{hex_str(subindex, 2)}"


@dataclass(slots=True, frozen=True)
class Selector:
    """A normalized selector with index and subindex."""

    key: str
    index: int
    subindex: int
    meta: Any = None


def normalize_selector(selector: str | int | dict | tuple | Selector) -> Selector:
    """Normalize a selector to a standard form.

    Args:
        selector: A selector in one of these formats:
            - 6-character hex string "300201"
            - 0xIIII:SS format string (e.g., "0x3002:1" or "3002:01")
            - Dictionary with 'index' and 'subindex' keys
            - Tuple of (index, subindex)
            - Selector object (returned as-is)

    Returns:
        A normalized Selector object.

    Raises:
        InvalidSelectorError: If the selector format is invalid.
    """
    if isinstance(selector, Selector):
        return selector

    if isinstance(selector, str):
        compact = selector.strip().lower()

        # Try 6-hex format: 300201
        raw_match = re.match(r"^[0-9a-f]{6}$", compact)
        if raw_match:
            index = int(compact[:4], 16)
            subindex = int(compact[4:6], 16)
            return Selector(key=compact, index=index, subindex=subindex)

        # Try pair format: "0xIIII:SS", "IIII:SS", "0xIIII:0xSS", etc.
        pair_match = re.match(r"^(?:0x)?([0-9a-f]{4}):(.+)$", compact)
        if pair_match:
            index = int(pair_match.group(1), 16)
            subindex_str = pair_match.group(2).strip()
            # Parse subindex: supports "1", "01", "0x01", "0x1"
            if subindex_str.startswith("0x"):
                subindex = int(subindex_str[2:], 16)
            elif all(c in "0123456789abcdef" for c in subindex_str) and len(subindex_str) <= 2:
                # Looks like hex (but only 1-2 chars, could be decimal too)
                # If there's a leading zero or it's > 99, treat as hex
                if len(subindex_str) == 2 and subindex_str[0] == "0":
                    subindex = int(subindex_str, 16)
                elif len(subindex_str) == 2 and all(c in "0123456789" for c in subindex_str):
                    # Could be decimal, treat as decimal if both chars are 0-9
                    val_dec = int(subindex_str, 10)
                    val_hex = int(subindex_str, 16)
                    # If the value would be > 255, must be decimal. Otherwise, treat as hex.
                    subindex = val_hex if val_hex <= 255 else val_dec
                else:
                    subindex = int(subindex_str, 16)
            else:
                # Decimal number
                subindex = int(subindex_str, 10)
            
            if not (0 <= subindex <= 255):
                raise InvalidSelectorError(selector, "subindex must be 0-255")
            
            key = format_selector(index, subindex)
            return Selector(key=key, index=index, subindex=subindex)

        raise InvalidSelectorError(selector, "expected 6 hex digits or 0xIIII:SS format")

    if isinstance(selector, dict):
        index = selector.get("index")
        subindex = selector.get("subindex")
        if not isinstance(index, int) or not isinstance(subindex, int):
            raise InvalidSelectorError(selector, "dict must have 'index' and 'subindex' keys")
        key = format_selector(index, subindex)
        meta = selector.get("meta")
        return Selector(key=key, index=index, subindex=subindex, meta=meta)

    if isinstance(selector, tuple) and len(selector) == 2:
        index, subindex = selector
        if not isinstance(index, int) or not isinstance(subindex, int):
            raise InvalidSelectorError(selector, "tuple must contain (int, int)")
        key = format_selector(index, subindex)
        return Selector(key=key, index=index, subindex=subindex)

    raise InvalidSelectorError(selector, "selector must be a string, dict, tuple, or Selector")


@dataclass(slots=True, frozen=True)
class Answer:
    """A single answer from the controller."""

    key: str
    index: int
    subindex: int
    raw: str
    meta: Any = None


def split_aligned_answers(
    selectors: list[Selector],
    response_text: str,
) -> list[Answer]:
    """Parse a response string into aligned answers.

    Each selector gets either 8 hex characters or 'X' (missing).

    Args:
        selectors: List of Selector objects queried.
        response_text: The response text from the controller.

    Returns:
        List of Answer objects in the same order as selectors.

    Raises:
        ResponseAlignmentError: If the response is malformed.
    """
    offset = 0
    answers = []

    for selector in selectors:
        if offset >= len(response_text):
            raise ResponseAlignmentError(
                "Response ended before all selectors were decoded",
                {
                    "selector": selector.key,
                    "offset": offset,
                    "response_length": len(response_text),
                },
            )

        if response_text[offset] == "X":
            offset += 1
            answers.append(Answer(key=selector.key, index=selector.index, subindex=selector.subindex, raw="X", meta=selector.meta))
            continue

        raw = response_text[offset : offset + 8]
        if len(raw) != 8 or not re.match(r"^[0-9a-fA-F]{8}$", raw):
            raise ResponseAlignmentError(
                "Encountered malformed 8-hex answer while decoding response",
                {
                    "selector": selector.key,
                    "offset": offset,
                    "raw": raw,
                },
            )

        offset += 8
        answers.append(Answer(key=selector.key, index=selector.index, subindex=selector.subindex, raw=raw.upper(), meta=selector.meta))

    if offset != len(response_text):
        raise ResponseAlignmentError(
            "Response contained trailing undecoded data",
            {
                "consumed": offset,
                "response_length": len(response_text),
                "trailing": response_text[offset : min(len(response_text), offset + 32)],
            },
        )

    return answers


def read_uint32(raw: str) -> int:
    """Read a 32-bit unsigned integer from an 8-character hex string."""
    return int(raw, 16)


def read_int32(raw: str) -> int:
    """Read a 32-bit signed integer from an 8-character hex string."""
    value = int(raw, 16)
    # Two's complement: if the sign bit (bit 31) is set, treat as negative
    if value >> 31:
        value = -2147483648 + (value & 0x7FFFFFFF)
    return value


def read_uint16(raw: str, word: int) -> int:
    """Read a 16-bit unsigned integer from a specific word (0 or 1).

    Word 0 is the low word (bits 0-15, chars 4-8).
    Word 1 is the high word (bits 16-31, chars 0-4).
    """
    start = (1 - word) * 4
    end = (2 - word) * 4
    return int(raw[start:end], 16)


def read_int16(raw: str, word: int) -> int:
    """Read a 16-bit signed integer from a specific word (0 or 1)."""
    value = read_uint16(raw, word)
    # Two's complement: if the sign bit (bit 15) is set, treat as negative
    if value >> 15:
        value = -32768 + (value & 0x7FFF)
    return value


def read_byte(raw: str, byte_index: int) -> int:
    """Read a single byte from a specific position (0-3).

    Byte 0 is the low byte (bits 0-7, chars 6-8).
    Byte 1 is (bits 8-15, chars 4-6).
    Byte 2 is (bits 16-23, chars 2-4).
    Byte 3 is the high byte (bits 24-31, chars 0-2).
    """
    start = (3 - byte_index) * 2
    end = (4 - byte_index) * 2
    return int(raw[start:end], 16)


@dataclass(slots=True)
class RawDecoded:
    """Decoded representation of a raw 8-hex-char response value."""

    raw: str
    missing: bool
    uint32: int | None = None
    int32: int | None = None
    uint16_word0: int | None = None
    uint16_word1: int | None = None
    int16_word0: int | None = None
    int16_word1: int | None = None
    bytes: list[int] | None = None


def decode_raw_value(raw: str) -> RawDecoded:
    """Decode a raw 8-character hex value into its component parts.

    Args:
        raw: An 8-character hex string or 'X' (missing).

    Returns:
        A RawDecoded object with all decoded fields.
    """
    if raw == "X":
        return RawDecoded(raw=raw, missing=True)

    return RawDecoded(
        raw=raw,
        missing=False,
        uint32=read_uint32(raw),
        int32=read_int32(raw),
        uint16_word0=read_uint16(raw, 0),
        uint16_word1=read_uint16(raw, 1),
        int16_word0=read_int16(raw, 0),
        int16_word1=read_int16(raw, 1),
        bytes=[read_byte(raw, 0), read_byte(raw, 1), read_byte(raw, 2), read_byte(raw, 3)],
    )
