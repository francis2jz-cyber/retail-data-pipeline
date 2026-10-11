"""The seeding script against a fake Paystack: first run without a test card, normal run, and re-run."""
import json

import pytest

import scripts.seed_paystack_demo as seed
from tests.test_paystack import FakePaystack, response


class FakePaystackWithCharges(FakePaystack):
    def __init__(self, has_card=True):
        card = {"id": 1, "status": "success", "reference": "checkout1", "amount": 10000, "currency": "ZAR",
                "channel": "card", "paid_at": "2026-01-01T10:00:00.000Z", "metadata": "",
                "customer": {"email": "tester@example.com"},
                "authorization": {"authorization_code": "AUTH_test123", "reusable": True}}
        super().__init__([card] if has_card else [])
        self.references = set()

    def post(self, url, data, timeout):
        body = json.loads(data)
        if url.endswith("/transaction/initialize"):
            return response(200, {"status": True, "data": {"authorization_url": "https://checkout.paystack.com/x"}})
        assert url.endswith("/transaction/charge_authorization")
        assert body["authorization_code"] == "AUTH_test123" and body["email"] == "tester@example.com"
        assert json.loads(body["metadata"])["order_id"]
        if body["reference"] in self.references:
            return response(400, {"status": False, "message": "Duplicate Transaction Reference"})
        self.references.add(body["reference"])
        return response(200, {"status": True, "message": "Charge attempted", "data": {"status": "success"}})


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_fake")
    monkeypatch.setattr(seed, "DEMO_DIR", tmp_path / "demo")
    return tmp_path


def test_first_run_without_card_prints_checkout_link(env, monkeypatch, capsys):
    monkeypatch.setattr(seed, "make_session", lambda key: FakePaystackWithCharges(has_card=False))
    assert seed.main(["--delay", "0"]) == 0
    assert "https://checkout.paystack.com/x" in capsys.readouterr().out


def test_seeds_every_successful_payment_once(env, monkeypatch, capsys):
    fake = FakePaystackWithCharges()
    monkeypatch.setattr(seed, "make_session", lambda key: fake)
    assert seed.main(["--delay", "0"]) == 0
    payments = json.loads((env / "demo" / "api" / "payments.json").read_text())
    expected = {p["payment_id"] for p in payments if p["status"] == "success" and (p["amount"] or 0) > 0}
    assert {r.rsplit("-", 1)[0] for r in fake.references} == expected

    # Running again must not create anything new
    assert seed.main(["--delay", "0"]) == 0
    assert f"0 new, {len(expected)} already there" in capsys.readouterr().out


def test_refuses_live_key(env, monkeypatch, capsys):
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_live_real_money")
    assert seed.main(["--delay", "0"]) == 1
    assert "non-test" in capsys.readouterr().err
