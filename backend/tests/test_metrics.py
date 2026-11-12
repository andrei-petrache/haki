"""Request metrics, served on their own port and never by the API.

The registry is global to the process, so each test reads the change in a
counter, never its absolute value. Other tests run without the metrics
server (METRICS_PORT=0 in conftest.py); these give it a free port.
"""

import socket
import urllib.error
import urllib.request

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.config import settings
from app.main import app


@pytest.fixture(autouse=True)
def metrics_port(monkeypatch: pytest.MonkeyPatch) -> int:
    """A free port for the metrics server, set before the test client starts."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    monkeypatch.setattr(settings, "metrics_port", port)
    return port


def requests_total(method: str, route: str, status: str) -> float:
    labels = {"method": method, "route": route, "status": status}
    return REGISTRY.get_sample_value("haki_http_requests_total", labels) or 0


def duration_count(method: str, route: str) -> float:
    labels = {"method": method, "route": route}
    value = REGISTRY.get_sample_value(
        "haki_http_request_duration_seconds_count", labels
    )
    return value or 0


def scrape() -> tuple[int, str, str]:
    """GET /metrics from the metrics server, as Prometheus does."""
    port = app.state.metrics_server.server_port
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics") as response:
        return (
            response.status,
            response.headers["Content-Type"],
            response.read().decode(),
        )


def test_no_metrics_server_when_the_port_is_0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "metrics_port", 0)

    with TestClient(app):
        assert app.state.metrics_server is None


def test_metrics_server_listens_on_the_configured_port(
    client: TestClient, metrics_port: int
) -> None:
    assert app.state.metrics_server.server_port == metrics_port


def test_metrics_server_returns_prometheus_text(client: TestClient) -> None:
    client.get("/health")

    status, content_type, text = scrape()

    assert status == 200
    assert content_type.startswith("text/plain")
    assert "haki_http_requests_total{" in text
    assert "haki_http_request_duration_seconds_bucket{" in text


@pytest.mark.parametrize("path", ["/metrics", "/api/metrics", "//metrics"])
def test_the_api_does_not_serve_metrics(client: TestClient, path: str) -> None:
    # Nginx forwards /api/* to the API with the prefix stripped: a route here
    # would make the metrics public
    response = client.get(path)

    assert response.status_code == 404
    assert "haki_http_requests_total" not in response.text


def test_metrics_are_not_in_the_api_schema(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert not [path for path in schema["paths"] if "metrics" in path]


def test_metrics_server_stops_with_the_app(client: TestClient) -> None:
    port = app.state.metrics_server.server_port

    client.__exit__(None, None, None)

    with pytest.raises(urllib.error.URLError):
        urllib.request.urlopen(f"http://127.0.0.1:{port}/metrics", timeout=2)


def test_requests_are_counted_by_route_template(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    before = requests_total("GET", "/workouts/{workout_id}", "404")
    timed = duration_count("GET", "/workouts/{workout_id}")

    for workout_id in (101, 202, 303):
        client.get(f"/workouts/{workout_id}", headers=auth_headers)

    assert requests_total("GET", "/workouts/{workout_id}", "404") == before + 3
    assert duration_count("GET", "/workouts/{workout_id}") == timed + 3
    # The ids never become labels
    assert "/workouts/101" not in scrape()[2]


def test_status_is_a_label(client: TestClient) -> None:
    before = requests_total("GET", "/foods", "401")

    client.get("/foods")

    assert requests_total("GET", "/foods", "401") == before + 1


def test_unknown_paths_share_one_label(client: TestClient) -> None:
    before = requests_total("GET", "unmatched", "404")

    client.get("/no-such-page-1")
    client.get("/no-such-page-2")

    assert requests_total("GET", "unmatched", "404") == before + 2
    assert "no-such-page" not in scrape()[2]


def test_made_up_methods_share_one_label(client: TestClient) -> None:
    # The client picks the method: each made-up one must not be a new series
    before = sum(requests_total("OTHER", "/foods", status) for status in ("401", "405"))

    for method in ("FOOBAR", "BAZQUX", "X-ANYTHING"):
        client.request(method, "/foods")

    after = sum(requests_total("OTHER", "/foods", status) for status in ("401", "405"))
    assert after == before + 3
    text = scrape()[2]
    assert "FOOBAR" not in text and "BAZQUX" not in text


def test_known_methods_keep_their_label(client: TestClient) -> None:
    before = requests_total("DELETE", "/foods/{food_id}", "401")

    client.delete("/foods/1")

    assert requests_total("DELETE", "/foods/{food_id}", "401") == before + 1
