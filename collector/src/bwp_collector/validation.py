"""Strict parsing: uncertain OCR must not silently become valid game data."""

import re
import unicodedata
from datetime import datetime, timezone

FIELDS = ("player_id", "grade", "bailian_points", "cumulative_wins")
LONG_MAX = 9223372036854775807
GRADES = {"五段": 5, "六段": 6, "七段": 7, "八段": 8, "名士": 9, "大名士": 10}


def utc_millis(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("截图时间必须是带时区的 ISO 8601 字符串")
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("截图时间缺少时区，不能使用文件修改时间代替")
    dt = dt.astimezone(timezone.utc)
    return dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def instant(value: str) -> datetime:
    return datetime.fromisoformat(utc_millis(value).replace("Z", "+00:00"))


def identifier(value, name: str, max_length: int = 64) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} 必须是非空字符串，且不能有首尾空白")
    if len(value) > max_length or any(c.isspace() or unicodedata.category(c)[0] == "C" for c in value):
        raise ValueError(f"{name} 含空白、控制字符或超出长度")
    return value


def decimal_string(value, name: str, maximum=LONG_MAX, minimum=0) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"0|[1-9][0-9]*", value):
        raise ValueError(f"{name} 必须是规范十进制字符串")
    if len(value) > 20 or not minimum <= int(value) <= maximum:
        raise ValueError(f"{name} 超出允许范围")
    return value


def parse_field(field: str, text: str):
    if field == "player_id":
        # O/0 or l/1 substitutions can merge different players. Never guess.
        return identifier(text, field)
    normalized = unicodedata.normalize("NFKC", text).strip()
    if field == "grade":
        # Profile cards add sub-ranks/seats. Match the whole label, never search
        # for "五段" inside "名士五段" (which belongs to the 名士 scoring group).
        match = re.fullmatch(r"(大名士|名士)(?:[一二三四五六七八九十]+段)?(?:\s*[0-9]+席)?", normalized)
        if match:
            return GRADES[match[1]]
        match = re.fullmatch(r"([五六七八]段)(?:(?:初|[一二三四五六七八九十]+)阶)?(?:\s*[0-9]+席)?", normalized)
        if match:
            return GRADES[match[1]]
        raise ValueError("未知段位")
    if field not in FIELDS:
        raise ValueError("不支持的字段")
    if re.fullmatch(r"[0-9]{1,3}(,[0-9]{3})+", normalized):
        normalized = normalized.replace(",", "")
    elif not re.fullmatch(r"[0-9]+", normalized):
        raise ValueError("数字含不确定字符、单位或非法分隔符")
    if len(normalized) > 19:
        raise ValueError("数字超出 Java Long 范围")
    return decimal_string(str(int(normalized)), field)
