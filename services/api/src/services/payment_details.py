"""Validation of a venue's payment details (what guests are shown to pay into)."""

import re
from typing import Any

ALLOWED = {"raast_id", "jazzcash", "easypaisa", "iban", "account_title", "sample"}
MOBILE = re.compile(r"^03\d{9}$")
IBAN = re.compile(r"^PK\d{2}[A-Z]{4}\d{16}$")
MAX_VALUE_LEN = 80


class PaymentDetailsError(ValueError):
    def __init__(self, field: str, message: str):
        super().__init__(message)
        self.field = field
        self.message = message


def _iban_ok(iban: str) -> bool:
    if not IBAN.match(iban):
        return False
    moved = iban[4:] + iban[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def validate_payment_details(raw: dict[str, Any]) -> dict[str, Any]:
    """Return the cleaned details, or raise PaymentDetailsError naming the bad field."""
    for key in raw:
        if key not in ALLOWED:
            raise PaymentDetailsError(key, "Unknown field")
    sample = raw.get("sample", False)
    if not isinstance(sample, bool):
        raise PaymentDetailsError("sample", "Must be true or false")

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
            if not 2 <= len(value) <= 80:
                raise PaymentDetailsError(key, "Account title must be 2 to 80 characters")
        elif not sample:
            compact = re.sub(r"[\s-]", "", value)
            if key == "iban":
                value = compact.upper()
                if not _iban_ok(value):
                    raise PaymentDetailsError(key, "Not a valid Pakistani IBAN")
            elif key == "raast_id":
                value = compact.upper()
                if not (MOBILE.match(value) or _iban_ok(value)):
                    raise PaymentDetailsError(key, "Use a mobile number (03XXXXXXXXX) or IBAN")
            else:  # jazzcash, easypaisa
                value = compact
                if not MOBILE.match(value):
                    raise PaymentDetailsError(key, "Use a mobile number like 03XXXXXXXXX")
        out[key] = value
    if sample:
        out["sample"] = True
    return out
