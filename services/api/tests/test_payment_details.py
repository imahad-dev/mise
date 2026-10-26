import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from tests.helpers import as_member

from src.config import settings
from src.models.restaurant import Restaurant
from src.services.payment_details import PaymentDetailsError, validate_payment_details

GOOD_IBAN = "PK36SCBL0000001123456702"  # standard published example, passes mod-97


def test_good_iban_passes_mod97():
    moved = GOOD_IBAN[4:] + GOOD_IBAN[:4]
    assert int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


def test_valid_details():
    d = validate_payment_details(
        {
            "raast_id": "03001234567",
            "jazzcash": "03001234567",
            "easypaisa": "03451234567",
            "iban": GOOD_IBAN.lower(),
            "account_title": "Angeethi House",
        },
        allow_sample=False,
    )
    assert d["iban"] == GOOD_IBAN


@pytest.mark.parametrize(
    "field,value",
    [
        ("iban", "PK36SCBL0000001123456703"),  # checksum fails
        ("iban", "GB36SCBL0000001123456702"),  # not PK
        ("iban", "PK36SCBL00000011234567"),  # too short
        ("jazzcash", "3001234567"),
        ("easypaisa", "04001234567"),
        ("raast_id", "hello"),
        ("account_title", "A"),
    ],
)
def test_invalid(field, value):
    with pytest.raises(PaymentDetailsError) as e:
        validate_payment_details({"account_title": "Venue", field: value}, allow_sample=False)
    assert e.value.field == field


def test_unknown_field_rejected():
    with pytest.raises(PaymentDetailsError) as e:
        validate_payment_details({"paypal": "x" * 100}, allow_sample=False)
    assert e.value.field == "paypal"


def test_sample_values_allowed_only_when_sample():
    sample = {"sample": True, "raast_id": "0000 SAMPLE", "account_title": "Sample account"}
    assert validate_payment_details(sample, allow_sample=True)["sample"] is True
    with pytest.raises(PaymentDetailsError):
        validate_payment_details({**sample, "sample": False}, allow_sample=True)
    with pytest.raises(PaymentDetailsError) as e:
        validate_payment_details(sample, allow_sample=False)
    assert e.value.field == "sample"


def test_unknown_key_echo_is_capped():
    with pytest.raises(PaymentDetailsError) as e:
        validate_payment_details({"k" * 100: "x"}, allow_sample=False)
    assert len(e.value.field) == 40


def _swap(text: str, zero: int) -> str:
    """Replace ASCII digits with the digits of another script (Arabic-Indic, fullwidth...)."""
    return "".join(chr(zero + int(c)) if c.isdigit() else c for c in text)


ARABIC, FULLWIDTH = 0x660, 0xFF10


@pytest.mark.parametrize(
    "field,value",
    [
        ("jazzcash", _swap("03001234567", ARABIC)),
        ("easypaisa", _swap("03001234567", FULLWIDTH)),
        ("raast_id", _swap("03001234567", ARABIC)),
        ("iban", _swap(GOOD_IBAN, ARABIC)),
        ("iban", _swap(GOOD_IBAN, FULLWIDTH)),
    ],
)
def test_non_ascii_digits_rejected(field, value):
    with pytest.raises(PaymentDetailsError) as e:
        validate_payment_details({"account_title": "Venue", field: value}, allow_sample=False)
    assert e.value.field == field


@pytest.mark.parametrize(
    "value", ["03001234567", "+923001234567", "00923001234567", "923001234567", "+92 300-1234567"]
)
def test_mobile_prefixes_normalised(value):
    d = validate_payment_details(
        {"account_title": "Venue", "jazzcash": value, "easypaisa": value, "raast_id": value},
        allow_sample=False,
    )
    assert d["jazzcash"] == d["easypaisa"] == d["raast_id"] == "03001234567"


def test_account_title_required_with_methods():
    with pytest.raises(PaymentDetailsError) as e:
        validate_payment_details({"jazzcash": "03001234567"}, allow_sample=False)
    assert e.value.field == "account_title"
    assert validate_payment_details({}, allow_sample=False) == {}


def test_account_title_controls_and_bidi():
    d = validate_payment_details({"account_title": "Ve\x00nu\ne"}, allow_sample=False)
    assert d["account_title"] == "Venue"
    with pytest.raises(PaymentDetailsError) as e:
        validate_payment_details({"account_title": "Venue\u202e"}, allow_sample=False)
    assert e.value.field == "account_title"


async def _venue(db: AsyncSession, slug: str | None = None) -> Restaurant:
    r = Restaurant(
        name="Settings Venue", slug=slug or f"set-{uuid.uuid4().hex[:8]}", currency="PKR"
    )
    db.add(r)
    await db.flush()
    return r


async def test_owner_saves_and_reads_settings(client: AsyncClient, db_session: AsyncSession):
    r = await _venue(db_session)
    await as_member(client, db_session, r.id, "owner")
    resp = await client.patch(
        f"/api/restaurants/{r.slug}/settings",
        json={
            "payment_details": {"iban": GOOD_IBAN.lower(), "account_title": "Venue"},
            "service_extra_label": "  More naan  ",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {
        "payment_details": {"iban": GOOD_IBAN, "account_title": "Venue"},
        "service_extra_label": "More naan",
    }
    got = await client.get(f"/api/restaurants/{r.slug}/settings")
    assert got.json() == resp.json()
    # omitted fields stay as they are
    resp = await client.patch(f"/api/restaurants/{r.slug}/settings", json={})
    assert resp.json() == got.json()


async def test_invalid_details_name_the_field(client: AsyncClient, db_session: AsyncSession):
    r = await _venue(db_session)
    await as_member(client, db_session, r.id, "owner")
    resp = await client.patch(
        f"/api/restaurants/{r.slug}/settings",
        json={"payment_details": {"jazzcash": "123", "account_title": "Venue"}},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["field"] == "jazzcash"
    resp = await client.patch(
        f"/api/restaurants/{r.slug}/settings", json={"service_extra_label": "x" * 41}
    )
    assert resp.status_code == 422


async def test_staff_cannot_patch_settings(client: AsyncClient, db_session: AsyncSession):
    r = await _venue(db_session)
    await as_member(client, db_session, r.id, "staff")
    resp = await client.patch(f"/api/restaurants/{r.slug}/settings", json={})
    assert resp.status_code == 403


async def test_demo_venue_forces_sample(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    monkeypatch.setattr(settings, "demo_mode", True)
    r = await _venue(db_session, slug="angeethi-house")
    await as_member(client, db_session, r.id, "owner")
    resp = await client.patch(
        f"/api/restaurants/{r.slug}/settings",
        json={
            "payment_details": {
                "raast_id": "0000 SAMPLE",
                "account_title": "Sample",
                "sample": False,
            }
        },
    )
    assert resp.status_code == 200
    assert resp.json()["payment_details"]["sample"] is True


async def test_non_demo_venue_rejects_sample(client: AsyncClient, db_session: AsyncSession):
    r = await _venue(db_session)
    await as_member(client, db_session, r.id, "owner")
    resp = await client.patch(
        f"/api/restaurants/{r.slug}/settings",
        json={"payment_details": {"sample": True, "iban": "junk", "account_title": "Venue"}},
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["field"] == "sample"
    got = await client.get(f"/api/restaurants/{r.slug}/settings")
    assert got.json()["payment_details"] == {}


@pytest.mark.parametrize("title", ["​​", "‎‏", "​A"])
def test_invisible_only_title_rejected(title):
    with pytest.raises(PaymentDetailsError) as e:
        validate_payment_details(
            {"jazzcash": "03001234567", "account_title": title}, allow_sample=False
        )
    assert e.value.field == "account_title"
