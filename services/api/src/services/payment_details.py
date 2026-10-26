"""Validation of a venue's payment details (what guests are shown to pay into)."""

import re
import unicodedata
from typing import Any

ALLOWED = {"raast_id", "jazzcash", "easypaisa", "iban", "account_title", "sample"}
METHOD_FIELDS = ("raast_id", "jazzcash", "easypaisa", "iban")
MOBILE = re.compile(r"^03[0-9]{9}$", re.ASCII)
MOBILE_INTL = re.compile(r"^(?:0092|92)(3[0-9]{9})$", re.ASCII)
IBAN = re.compile(r"^PK[0-9]{2}[A-Z]{4}[0-9]{16}$", re.ASCII)
BIDI = re.compile("[\u202a-\u202e\u2066-\u2069]")
MAX_VALUE_LEN = 80


class PaymentDetailsError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def _iban_ok(iban: str) -> bool:
    if not iban.isascii() or not IBAN.match(iban):
        return False
    moved = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def _mobile(value: str) -> str | None:
    """Return the 03XXXXXXXXX form of a Pakistani mobile (03, +92, 0092 or 92 prefix), or None."""
    c = re.sub(r"[\s-]", "", value).lstrip("+")
    m = MOBILE_INTL.match(c)
    if m:
        return "0" + m.group(1)
    return c if MOBILE.match(c) else None


def validate_payment_details(raw: dict[str, Any], *, allow_sample: bool) -> dict[str, Any]:
    """Return the cleaned details, or raise PaymentDetailsError naming the bad field.

    `sample` (placeholder values) is honoured only when allow_sample is set (demo venues).
    """
    for key in raw:
        if key not in ALLOWED:
            raise PaymentDetailsError(str(key)[:40], "Unknown field")
    sample = raw.get("sample", False)
    if not isinstance(sample, bool):
        raise PaymentDetailsError("sample", "Must be true or false")
    if sample and not allow_sample:
        raise PaymentDetailsError("sample", "Sample details are only allowed on demo venues")

    out: dict[str, Any] = {}
    for key in ALLOWED - {"sample"}:
        value = raw.get(key)
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise PaymentDetailsError(key, "Must be text")
        value = value.strip()
        if len(value) > MAX_VALUE_LEN:
            raise PaymentDetailsError(key, f"At most {MAX_VALUE_LEN} characters")
        if key == "account_title":
            if BIDI.search(value):
                raise PaymentDetailsError(key, "Account title contains invalid characters")
            # Cc = control, Cf = invisible format chars (zero-width, direction marks).
            value = "".join(c for c in value if unicodedata.category(c) not in ("Cc", "Cf")).strip()
            if not 2 <= len(value) <= 80:
                raise PaymentDetailsError(key, "Account title must be 2 to 80 characters")
        elif not sample:
            if key == "iban":
                value = re.sub(r"[\s-]", "", value).upper()
                if not _iban_ok(value):
                    raise PaymentDetailsError(key, "Not a valid Pakistani IBAN")
            elif key == "raast_id":
                mobile = _mobile(value)
                iban = re.sub(r"[\s-]", "", value).upper()
                if mobile:
                    value = mobile
                elif _iban_ok(iban):
                    value = iban
                else:
                    raise PaymentDetailsError(key, "Use a mobile number (03XXXXXXXXX) or IBAN")
            else:  # jazzcash, easypaisa
                mobile = _mobile(value)
                if not mobile:
                    raise PaymentDetailsError(key, "Use a mobile number like 03XXXXXXXXX")
                value = mobile
        out[key] = value
    if any(k in out for k in METHOD_FIELDS) and "account_title" not in out:
        raise PaymentDetailsError(
            "account_title", "Account title is required when you add payment details"
        )
    if sample:
        out["sample"] = True
    return out
