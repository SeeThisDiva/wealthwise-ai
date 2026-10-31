import pytest

from web import server


@pytest.fixture(autouse=True)
def _fresh_limiter():
    server.rate_limiter.history.clear()
    yield
    server.rate_limiter.history.clear()


@pytest.fixture(autouse=True)
def _csrf_for_test_clients(monkeypatch):
    """Clients created with app.test_client() behave like the dashboard and send the token."""
    original = type(server.app).test_client

    def make_client(*args, **kwargs):
        client = original(server.app, *args, **kwargs)
        client.environ_base["HTTP_X_CSRF_TOKEN"] = server.CSRF_TOKEN
        return client

    monkeypatch.setattr(server.app, "test_client", make_client)


@pytest.fixture
def raw_client():
    """A client with no token, for testing what is rejected."""
    return type(server.app).test_client(server.app)


@pytest.fixture
def client():
    return server.app.test_client()
