"""Sales tax by jurisdiction, payment method and date."""

import json
from datetime import date
from decimal import Decimal

import pytest

from src.services.tax import (
    Jurisdiction,
    TaxRate,
    TaxRateError,
    check_rates_against,
    default_jurisdictions,
    load_jurisdictions,
    load_rates,
    payment_class,
    tax_for,
)

JULY = date(2026, 7, 1)


def test_payment_classes():
    assert payment_class("cash") == "standard"
    assert payment_class("bank_transfer") == "standard"
    for m in ("card", "wallet", "raast"):
        assert payment_class(m) == "digital"


@pytest.mark.parametrize(
    ("jur", "method", "subtotal", "rate", "tax"),
    [
        ("PB", "cash", "5490", "0.16", "878"),  # 878.40 -> 878
        ("PB", "card", "5490", "0.08", "439"),  # 439.20 -> 439
        ("PB", "bank_transfer", "1000", "0.16", "160"),
        ("ICT", "wallet", "2310", "0.05", "116"),  # 115.50 -> 116 (half up)
        ("ICT", "cash", "2310", "0.15", "347"),  # 346.50 -> 347
    ],
)
def test_tax_for(jur, method, subtotal, rate, tax):
    r, t = tax_for(jur, method, JULY, Decimal(subtotal))
    assert r == Decimal(rate)
    assert t == Decimal(tax)


def test_latest_rate_on_or_before_date_wins():
    rates = [
        TaxRate("PB", "digital", Decimal("0.05"), date(2021, 7, 1), "old"),
        TaxRate("PB", "digital", Decimal("0.08"), date(2026, 7, 1), "new"),
    ]
    assert tax_for("PB", "card", date(2026, 6, 30), Decimal("100"), rates)[0] == Decimal("0.05")
    assert tax_for("PB", "card", date(2026, 7, 1), Decimal("100"), rates)[0] == Decimal("0.08")


def test_shipped_punjab_digital_rate_changes_on_1_july_2026():
    assert tax_for("PB", "card", date(2026, 6, 30), Decimal("100"))[0] == Decimal("0.05")
    assert tax_for("PB", "card", date(2026, 7, 1), Decimal("100"))[0] == Decimal("0.08")
    assert tax_for("PB", "cash", date(2026, 6, 30), Decimal("100"))[0] == Decimal("0.16")


def test_no_rate_for_date_raises():
    with pytest.raises(TaxRateError):
        tax_for("PB", "cash", date(2020, 1, 1), Decimal("100"))
    with pytest.raises(TaxRateError):
        tax_for("SD", "cash", JULY, Decimal("100"))


@pytest.mark.parametrize(
    "bad",
    [
        '[{"jurisdiction":"PB","payment_class":"cash","rate":"0.16","effective_from":"2026-07-01","source":"x"}]',
        '[{"jurisdiction":"PB","payment_class":"digital","rate":"1.5","effective_from":"2026-07-01","source":"x"}]',
        '[{"jurisdiction":"PB","payment_class":"digital","rate":"0.08","effective_from":"2026-07-01","source":"x"},'
        ' {"jurisdiction":"PB","payment_class":"digital","rate":"0.09","effective_from":"2026-07-01","source":"y"}]',  # noqa: E501
        '{"not": "a list"}',
        '[{"jurisdiction":"PB","payment_class":"digital","rate":"NaN","effective_from":"2026-07-01","source":"x"}]',
        '[{"jurisdiction":"PB","payment_class":"digital","rate":"0.08","effective_from":"2026-07-01","source":""}]',
        '[{"jurisdiction":"PB","payment_class":"digital","rate":"0.08","effective_from":"2026-07-01","source":null}]',
        '[{"jurisdiction":"","payment_class":"digital","rate":"0.08","effective_from":"2026-07-01","source":"x"}]',
    ],
)
def test_invalid_files_are_rejected(tmp_path, bad):
    p = tmp_path / "rates.json"
    p.write_text(bad, encoding="utf-8")
    with pytest.raises(TaxRateError):
        load_rates(p)


def test_shipped_rates_file_loads():
    rates = load_rates()
    assert len(rates) == 8
    assert {(r.jurisdiction, r.payment_class) for r in rates} == {
        ("PB", "standard"),
        ("PB", "digital"),
        ("ICT", "standard"),
        ("ICT", "digital"),
        ("GB", "any"),
        ("AE-DU", "any"),
    }


def _write(tmp_path, name, data):
    p = tmp_path / name
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_shipped_jurisdictions_load_and_match_rates():
    js = default_jurisdictions()
    assert js["GB"] == Jurisdiction(
        code="GB",
        name="United Kingdom",
        currency="GBP",
        pricing="included",
        rounding=Decimal("0.01"),
        methods=("cash", "card"),
        service_charge="optional_outside_tax",
    )
    assert js["PB"].pricing == "on_top" and js["PB"].rounding == Decimal("1")
    assert js["AE-DU"].service_charge is None


GOOD = {
    "name": "X",
    "currency": "GBP",
    "pricing": "included",
    "rounding": "0.01",
    "methods": ["cash"],
    "service_charge": None,
}


@pytest.mark.parametrize(
    "patch",
    [
        {"pricing": "sometimes"},
        {"rounding": "0"},
        {"rounding": "-1"},
        {"methods": []},
        {"methods": ["cash", "cheque"]},
        {"service_charge": "compulsory"},
        {"currency": ""},
    ],
)
def test_bad_jurisdiction_refused(tmp_path, patch):
    with pytest.raises(TaxRateError):
        load_jurisdictions(_write(tmp_path, "j.json", {"XX": {**GOOD, **patch}}))


def _xx():
    return {"XX": Jurisdiction("XX", "X", "GBP", "included", Decimal("0.01"), ("cash",), None)}


def test_rate_without_jurisdiction_refused():
    rates = [TaxRate("ZZ", "any", Decimal("0.1"), JULY, "s")]
    with pytest.raises(TaxRateError, match="ZZ"):
        check_rates_against(rates, _xx())


def test_any_and_split_rates_cannot_mix():
    rates = [
        TaxRate("XX", "any", Decimal("0.2"), JULY, "s"),
        TaxRate("XX", "standard", Decimal("0.2"), JULY, "s"),
    ]
    with pytest.raises(TaxRateError, match="mixes"):
        check_rates_against(rates, _xx())


def test_any_payment_class_accepted_by_rate_loader(tmp_path):
    rates = load_rates(
        _write(
            tmp_path,
            "r.json",
            [
                {
                    "jurisdiction": "GB",
                    "payment_class": "any",
                    "rate": "0.20",
                    "effective_from": "2011-01-04",
                    "source": "s",
                }
            ],
        )
    )
    assert rates[0].payment_class == "any"
