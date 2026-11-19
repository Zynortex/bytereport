"""
Currency conversion for note rows, against the Central Bank of Uzbekistan.

Nothing here touches the network: every test drives a stubbed CBU so the suite
stays deterministic and offline. The live behaviour was verified separately
against the real endpoint.
"""

from datetime import date

import pytest

from app.models.voice_note import DraftTransaction
from app.services import fx
from app.services import voice_parser as vp

TODAY = date(2026, 8, 26)

# Real shape of a CBU response, including the fields that matter.
USD = {"Ccy": "USD", "Rate": "11778.52", "Nominal": "1", "Date": "26.08.2026"}
RUB = {"Ccy": "RUB", "Rate": "139.02", "Nominal": "1", "Date": "26.08.2026"}
# CBU quotes small-denomination currencies per 100 or 1000 units.
JPY_LIKE = {"Ccy": "KZT", "Rate": "2195.40", "Nominal": "1000", "Date": "26.08.2026"}


@pytest.fixture(autouse=True)
def _clear_cache():
    fx.cache_clear()
    yield
    fx.cache_clear()


class _Stub:
    """Records every URL asked for, so caching can be observed."""

    def __init__(self, by_ccy: dict, fail: bool = False):
        self.by_ccy = by_ccy
        self.fail = fail
        self.calls: list[str] = []

    def get(self, url, timeout=None):
        self.calls.append(url)
        if self.fail:
            raise OSError("CBU unreachable")
        ccy = url.rstrip("/").split("/")[-2]
        payload = self.by_ccy.get(ccy)
        return _Resp([payload] if payload else [])


class _Resp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def _install(monkeypatch, stub):
    import sys
    import types

    module = types.ModuleType("httpx")
    module.get = stub.get
    monkeypatch.setitem(sys.modules, "httpx", module)
    return stub


# ── Rate lookup ─────────────────────────────────────────────────────────────

def test_rate_is_uzs_per_one_unit(monkeypatch):
    _install(monkeypatch, _Stub({"USD": USD}))
    assert fx.rate_to_uzs("USD", TODAY) == pytest.approx(11778.52)


def test_nominal_is_divided_out(monkeypatch):
    """
    CBU quotes KZT per 1000. Ignoring Nominal is wrong by three orders of
    magnitude and still looks like a plausible number.
    """
    _install(monkeypatch, _Stub({"KZT": JPY_LIKE}))
    assert fx.rate_to_uzs("KZT", TODAY) == pytest.approx(2.1954)


def test_the_base_currency_needs_no_lookup(monkeypatch):
    stub = _install(monkeypatch, _Stub({}))
    assert fx.rate_to_uzs("UZS", TODAY) == 1.0
    assert stub.calls == []


def test_an_unsupported_currency_is_not_requested(monkeypatch):
    stub = _install(monkeypatch, _Stub({}))
    assert fx.rate_to_uzs("BTC", TODAY) is None
    assert stub.calls == []


def test_a_rate_is_fetched_once_per_currency_and_day(monkeypatch):
    stub = _install(monkeypatch, _Stub({"USD": USD}))
    for _ in range(4):
        fx.rate_to_uzs("USD", TODAY)
    assert len(stub.calls) == 1


def test_a_different_date_is_a_different_lookup(monkeypatch):
    stub = _install(monkeypatch, _Stub({"USD": USD}))
    fx.rate_to_uzs("USD", TODAY)
    fx.rate_to_uzs("USD", date(2026, 8, 20))
    assert len(stub.calls) == 2


def test_a_failure_is_cached_too(monkeypatch):
    """
    Five USD rows during a CBU outage must not mean five doomed requests and a
    forty-second stall on the parse.
    """
    stub = _install(monkeypatch, _Stub({}, fail=True))
    for _ in range(5):
        assert fx.rate_to_uzs("USD", TODAY) is None
    assert len(stub.calls) == 1


def test_an_empty_payload_is_not_a_rate(monkeypatch):
    """CBU answers 200 with [] for weekends, holidays and future dates."""
    _install(monkeypatch, _Stub({}))
    assert fx.rate_to_uzs("USD", TODAY) is None


# ── Conversion ──────────────────────────────────────────────────────────────

def test_same_currency_is_not_a_conversion(monkeypatch):
    stub = _install(monkeypatch, _Stub({"USD": USD}))
    assert fx.convert(200, "USD", "USD", TODAY) is None
    assert stub.calls == []


def test_foreign_to_base(monkeypatch):
    _install(monkeypatch, _Stub({"USD": USD}))
    amount, rate = fx.convert(200, "USD", "UZS", TODAY)
    assert amount == pytest.approx(2_355_704.0)
    assert rate == pytest.approx(11778.52)


def test_base_to_foreign(monkeypatch):
    _install(monkeypatch, _Stub({"USD": USD}))
    amount, rate = fx.convert(11_778.52, "UZS", "USD", TODAY)
    assert amount == pytest.approx(1.0)


def test_cross_rate_goes_through_the_som(monkeypatch):
    """USD -> RUB has no direct quote; both legs come from the same day."""
    _install(monkeypatch, _Stub({"USD": USD, "RUB": RUB}))
    amount, rate = fx.convert(100, "USD", "RUB", TODAY)
    assert rate == pytest.approx(11778.52 / 139.02)
    assert amount == pytest.approx(100 * rate, rel=1e-6)


def test_conversion_returns_none_when_a_leg_is_missing(monkeypatch):
    _install(monkeypatch, _Stub({"USD": USD}))   # no RUB
    assert fx.convert(100, "USD", "RUB", TODAY) is None


# ── The row-level behaviour ─────────────────────────────────────────────────

def _row(**kw) -> DraftTransaction:
    base = dict(amount=200, currency="USD", direction="income", description="от заказчика")
    base.update(kw)
    return DraftTransaction(**base)


def test_a_converted_row_carries_the_rate_it_used(monkeypatch):
    _install(monkeypatch, _Stub({"USD": USD}))
    out = vp._convert_row(_row(date="2026-08-26"), "UZS", TODAY, "ru")
    assert out.amount == pytest.approx(2_355_704.0)
    assert out.currency == "UZS"
    assert "amount" in out.uncertain
    note = out.notes["amount"]
    assert "26.08.2026" in note and "USD" in note and "UZS" in note


def test_conversion_uses_the_transactions_own_date(monkeypatch):
    """A rate from the wrong day is a wrong number that looks right."""
    stub = _install(monkeypatch, _Stub({"USD": USD}))
    vp._convert_row(_row(date="2026-08-20"), "UZS", TODAY, "ru")
    assert "2026-08-20" in stub.calls[0]


def test_conversion_falls_back_to_today_when_the_row_has_no_date(monkeypatch):
    stub = _install(monkeypatch, _Stub({"USD": USD}))
    vp._convert_row(_row(date=None), "UZS", TODAY, "ru")
    assert TODAY.isoformat() in stub.calls[0]


def test_an_unresolved_date_fragment_falls_back_to_today(monkeypatch):
    stub = _install(monkeypatch, _Stub({"USD": USD}))
    vp._convert_row(_row(date="прошлая среда"), "UZS", TODAY, "ru")
    assert TODAY.isoformat() in stub.calls[0]


def test_the_row_stays_flagged_after_conversion(monkeypatch):
    """The number is a suggestion. Clearing the flag would present it as fact."""
    _install(monkeypatch, _Stub({"USD": USD}))
    out = vp._convert_row(_row(), "UZS", TODAY, "ru")
    assert "amount" in out.uncertain


def test_a_cbu_outage_degrades_that_row_only(monkeypatch):
    _install(monkeypatch, _Stub({}, fail=True))
    out = vp._convert_row(_row(), "UZS", TODAY, "ru")
    assert out.amount == 200            # untouched
    assert out.currency == "USD"        # still says what unit it is in
    assert "amount" in out.uncertain
    assert "курс" in out.notes["amount"].lower()


def test_a_row_already_in_the_business_currency_is_left_alone(monkeypatch):
    stub = _install(monkeypatch, _Stub({"USD": USD}))
    out = vp._convert_row(_row(currency="UZS", amount=500_000), "UZS", TODAY, "ru")
    assert out.amount == 500_000
    assert out.uncertain == []
    assert stub.calls == []


def test_a_row_with_no_currency_takes_the_business_currency(monkeypatch):
    stub = _install(monkeypatch, _Stub({"USD": USD}))
    out = vp._convert_row(_row(currency=None, amount=500_000), "UZS", TODAY, "ru")
    assert out.currency == "UZS"
    assert out.uncertain == []
    assert stub.calls == []


def test_a_row_with_no_amount_is_not_converted(monkeypatch):
    stub = _install(monkeypatch, _Stub({"USD": USD}))
    out = vp._convert_row(_row(amount=None), "UZS", TODAY, "ru")
    assert out.amount is None
    assert stub.calls == []


@pytest.mark.parametrize("lang", ["ru", "uz", "en"])
def test_the_conversion_note_is_localised(monkeypatch, lang):
    _install(monkeypatch, _Stub({"USD": USD}))
    out = vp._convert_row(_row(), "UZS", TODAY, lang)
    assert out.notes["amount"] == vp._FX_NOTE[lang].format(
        d="26.08.2026", src="USD", rate=vp._fmt_rate(11778.52), dst="UZS",
    )


def test_the_prompt_tells_the_model_not_to_convert():
    """
    Conversion has to happen after the scale is resolved, and with a real rate.
    A model doing it inline would multiply its own ambiguity by twelve thousand.
    """
    assert "do NOT attempt any conversion yourself" in vp.SYSTEM_PROMPT
