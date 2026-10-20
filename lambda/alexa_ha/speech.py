"""Turn Home Assistant's text answer into something Alexa reads naturally.

LLM agents often answer with markdown, emoji and unit symbols. Alexa would
read "**" or "°C" badly (or not at all), so we clean the text, spell out
units and currency, and build SSML. Devanagari text is wrapped in a Hindi
``<lang>`` tag so the voice switches to Hindi for it.
"""

from __future__ import annotations

import re
from typing import List, Tuple

# ---------------------------------------------------------------- markdown

_CODE_FENCE = re.compile(r"```[^\n]*\n?(.*?)```", re.S)
_INLINE_CODE = re.compile(r"`([^`]*)`")
_IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
_URL = re.compile(r"\bhttps?://\S+|\bwww\.\S+", re.I)
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s*(.*?)\s*#*\s*$", re.M)
_BLOCKQUOTE = re.compile(r"^\s*>+\s?", re.M)
_HRULE = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$", re.M)
_BULLET = re.compile(r"^\s*(?:[-*+•▪●◦‣]|\d{1,3}[.)])\s+", re.M)
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", re.M)
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1", re.S)
_ITALIC_STAR = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
_ITALIC_UNDERSCORE = re.compile(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])")
_STRIKE = re.compile(r"~~(.+?)~~", re.S)
_HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")

# Emoji and pictographs (kept away from Devanagari and other letters).
_EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # pictographs, emoticons, transport, symbols
    "\U00002600-\U000027BF"  # misc symbols, dingbats
    "\U00002B00-\U00002BFF"  # arrows and stars
    "\U0000FE0F\U0000200D\U000020E3"  # variation selector, joiner, keycap
    "\U0001F1E6-\U0001F1FF"  # flags
    "]+"
)


def strip_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = _CODE_FENCE.sub(lambda m: m.group(1), text)
    text = _INLINE_CODE.sub(lambda m: m.group(1), text)
    text = _IMAGE.sub(lambda m: m.group(1), text)
    text = _LINK.sub(lambda m: m.group(1), text)
    text = _URL.sub("a link", text)
    text = _HTML_TAG.sub(" ", text)
    text = _HRULE.sub("", text)
    text = _TABLE_SEPARATOR.sub("", text)
    text = _HEADING.sub(lambda m: m.group(1), text)
    text = _BLOCKQUOTE.sub("", text)
    text = _BULLET.sub("", text)
    text = _BOLD.sub(lambda m: m.group(2), text)
    text = _STRIKE.sub(lambda m: m.group(1), text)
    text = _ITALIC_STAR.sub(lambda m: m.group(1), text)
    text = _ITALIC_UNDERSCORE.sub(lambda m: m.group(1), text)
    text = _EMOJI.sub(" ", text)

    # Table rows: "| a | b |" -> "a, b"
    lines = []
    for line in text.split("\n"):
        if line.count("|") >= 2:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            line = ", ".join(c for c in cells if c)
        lines.append(line.strip())

    # Join lines into sentences so list items don't run together.
    sentences: List[str] = []
    for line in lines:
        if not line:
            continue
        if sentences and not re.search(r"[.!?:;,।]$", sentences[-1]):
            sentences[-1] += "."
        sentences.append(line)
    text = " ".join(sentences)

    # Leftover markdown characters.
    text = re.sub(r"(?<!\w)[*_#]+|[*_#]+(?!\w)", " ", text)
    text = text.replace("`", "").replace("|", ", ")
    return text


# ---------------------------------------------------------------- units

_NUM = r"(?P<num>[-−]?\d+(?:[.,]\d+)*)"

# (regex for the unit right after a number, singular, plural)
_UNITS: List[Tuple[str, str, str]] = [
    (r"°\s?C\b|℃", "degree Celsius", "degrees Celsius"),
    (r"°\s?F\b|℉", "degree Fahrenheit", "degrees Fahrenheit"),
    (r"°", "degree", "degrees"),
    (r"%", "percent", "percent"),
    (r"(?:µ|μ|u)g/m(?:³|3)\b", "microgram per cubic metre", "micrograms per cubic metre"),
    (r"mg/m(?:³|3)\b", "milligram per cubic metre", "milligrams per cubic metre"),
    (r"m(?:³|3)/h\b", "cubic metre per hour", "cubic metres per hour"),
    (r"m(?:³|3)(?![\w/])", "cubic metre", "cubic metres"),
    (r"m(?:²|2)(?![\w/])", "square metre", "square metres"),
    (r"km/h\b|kmph\b|kph\b", "kilometre per hour", "kilometres per hour"),
    (r"m/s\b", "metre per second", "metres per second"),
    (r"mph\b", "mile per hour", "miles per hour"),
    (r"kWh\b", "kilowatt hour", "kilowatt hours"),
    (r"MWh\b", "megawatt hour", "megawatt hours"),
    (r"Wh\b", "watt hour", "watt hours"),
    (r"kW\b", "kilowatt", "kilowatts"),
    (r"W\b", "watt", "watts"),
    (r"kVA\b", "kilovolt amp", "kilovolt amps"),
    (r"VA\b", "volt amp", "volt amps"),
    (r"mA\b", "milliamp", "milliamps"),
    (r"V\b", "volt", "volts"),
    (r"A\b", "amp", "amps"),
    (r"Hz\b", "hertz", "hertz"),
    (r"hPa\b", "hectopascal", "hectopascals"),
    (r"mbar\b", "millibar", "millibars"),
    (r"inHg\b", "inch of mercury", "inches of mercury"),
    (r"mm/h\b", "millimetre per hour", "millimetres per hour"),
    (r"mm\b", "millimetre", "millimetres"),
    (r"cm\b", "centimetre", "centimetres"),
    (r"km\b", "kilometre", "kilometres"),
    (r"kg\b", "kilogram", "kilograms"),
    (r"lx\b", "lux", "lux"),
    (r"ppm\b", "part per million", "parts per million"),
    (r"ppb\b", "part per billion", "parts per billion"),
    (r"dBm\b", "dBm", "dBm"),
    (r"dB\b", "decibel", "decibels"),
    (r"ms\b", "millisecond", "milliseconds"),
    (r"Mbps\b|Mbit/s\b", "megabit per second", "megabits per second"),
    (r"Gbps\b", "gigabit per second", "gigabits per second"),
    (r"GB\b", "gigabyte", "gigabytes"),
    (r"MB\b", "megabyte", "megabytes"),
    (r"TB\b", "terabyte", "terabytes"),
    (r"mins?\b", "minute", "minutes"),
    (r"hrs?\b", "hour", "hours"),
    (r"secs?\b", "second", "seconds"),
    (r"L\b", "litre", "litres"),
]

_UNIT_PATTERNS = [
    (re.compile(_NUM + r"\s?(?:" + pattern + r")"), singular, plural) for pattern, singular, plural in _UNITS
]

_RUPEE_BEFORE = re.compile(r"(?:₹|\bRs\.?|\bINR)\s?(?P<num>\d+(?:[.,]\d+)*)(?:\s?(?P<scale>lakh|crore|k)\b)?", re.I)
_DOLLAR_BEFORE = re.compile(r"\$\s?(?P<num>\d+(?:[.,]\d+)*)")
_RANGE_DASH = re.compile(r"(?<=\d)\s?[–—]\s?(?=[-−]?\d)")
_RANGE_HYPHEN_UNIT = re.compile(r"(?<=\d)\s?-\s?(?=\d+(?:[.,]\d+)?\s?(?:°|%|℃|℉))")
_NEGATIVE = re.compile(r"(?:^|(?<=[\s(]))[-−](?=\d)")


def _plural(num: str, singular: str, plural: str) -> str:
    return singular if num.lstrip("-−") in ("1", "1.0") else plural


def _fix_negative(num: str) -> str:
    if num[:1] in ("-", "−"):
        return "minus " + num[1:]
    return num


def speak_units(text: str) -> str:
    text = _RANGE_DASH.sub(" to ", text)
    text = _RANGE_HYPHEN_UNIT.sub(" to ", text)

    def rupees(m: "re.Match[str]") -> str:
        scale = (m.group("scale") or "").lower()
        scale_word = {"k": " thousand", "lakh": " lakh", "crore": " crore"}.get(scale, "")
        word = "rupee" if m.group("num") == "1" and not scale_word else "rupees"
        return "%s%s %s" % (m.group("num"), scale_word, word)

    text = _RUPEE_BEFORE.sub(rupees, text)
    text = _DOLLAR_BEFORE.sub(lambda m: "%s %s" % (m.group("num"), "dollar" if m.group("num") == "1" else "dollars"), text)

    for pattern, singular, plural in _UNIT_PATTERNS:
        text = pattern.sub(
            lambda m, s=singular, p=plural: "%s %s" % (_fix_negative(m.group("num")), _plural(m.group("num"), s, p)),
            text,
        )

    text = _NEGATIVE.sub("minus ", text)
    text = re.sub(r"\s?(?:->|=>|→|⇒)\s?", " to ", text)
    text = re.sub(r"~\s?(?=\d)", "about ", text)
    text = text.replace("±", " plus or minus ")
    text = re.sub(r"\s&\s", " and ", text)
    return text


# ---------------------------------------------------------------- SSML

_DEVANAGARI_RUN = re.compile(r"[ऀ-ॿ꣠-ꣿ][ऀ-ॿ꣠-ꣿ\s,.!?'\"()-]*")
_WS = re.compile(r"\s+")


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "), cut.rfind("। "))
    if end > limit // 2:
        return cut[: end + 1]
    return cut.rsplit(" ", 1)[0] + "."


def clean_text(text: str, max_chars: int = 2500) -> str:
    """Plain text ready to be spoken (no markup)."""
    text = strip_markdown(text or "")
    text = speak_units(text)
    text = _WS.sub(" ", text).strip()
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    text = re.sub(r"([.,!?;:])\1+", r"\1", text)
    text = re.sub(r"^[.,;:\s]+", "", text)
    return _truncate(text, max_chars)


def to_ssml(text: str, hindi: bool = True) -> str:
    """Build SSML for already cleaned text."""
    escaped = _escape(text)
    if hindi:

        def wrap(m: "re.Match[str]") -> str:
            run = m.group(0)
            stripped = run.rstrip()
            return '<lang xml:lang="hi-IN">%s</lang>%s' % (stripped, run[len(stripped):])

        escaped = _DEVANAGARI_RUN.sub(wrap, escaped)
    return "<speak>%s</speak>" % escaped
