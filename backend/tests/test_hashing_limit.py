import threading
import time

import pytest
from fastapi.testclient import TestClient

from app import security
from app.security import ConcurrencyLimit, HashingBusy


def test_never_lets_more_than_capacity_in_at_once() -> None:
    limit = ConcurrencyLimit(capacity=2, timeout=5)
    active = 0
    most_active = 0
    lock = threading.Lock()

    def work() -> None:
        nonlocal active, most_active
        with limit.slot():
            with lock:
                active += 1
                most_active = max(most_active, active)
            time.sleep(0.05)
            with lock:
                active -= 1

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert most_active == 2


def test_gives_up_after_the_timeout_when_full() -> None:
    limit = ConcurrencyLimit(capacity=1, timeout=0.05)
    holding = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with limit.slot():
            holding.set()
            release.wait()

    holder = threading.Thread(target=hold)
    holder.start()
    holding.wait()
    started = time.monotonic()

    with pytest.raises(HashingBusy), limit.slot():
        pass

    assert time.monotonic() - started < 1  # waited briefly, not forever
    release.set()
    holder.join()


def test_frees_the_slot_when_the_work_fails() -> None:
    limit = ConcurrencyLimit(capacity=1, timeout=0.05)

    with pytest.raises(ValueError), limit.slot():
        raise ValueError("hashing failed")

    with limit.slot():  # would raise HashingBusy if the slot leaked
        pass


def test_login_returns_503_with_retry_after_when_hashing_is_saturated(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    full = ConcurrencyLimit(capacity=1, timeout=0.01)
    monkeypatch.setattr(security, "hashing_limit", full)

    with full.slot():  # every slot taken, as under heavy load
        response = client.post(
            "/auth/login",
            json={"email": "andrei@example.com", "password": "whatever-pass"},
        )

    assert response.status_code == 503
    assert response.json() == {"detail": "Server busy, try again shortly"}
    assert response.headers["Retry-After"] == "2"
