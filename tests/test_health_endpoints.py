"""
Tests for health check endpoints.
"""


class TestHealthEndpoints:
    def test_root(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert "version" in data

    def test_health(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    def test_auth_health(self, client):
        resp = client.get("/auth/health")
        assert resp.status_code == 200

    def test_chat_health(self, client):
        resp = client.get("/chat/health")
        assert resp.status_code == 200

    def test_users_health(self, client):
        resp = client.get("/users/health")
        assert resp.status_code == 200

    def test_public_health(self, client):
        resp = client.get("/public/health")
        assert resp.status_code == 200


class TestPreviewEndpoint:
    def test_valid_slug(self, client):
        resp = client.get("/preview/test-company")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "test-company" in resp.text

    def test_invalid_slug_rejected(self, client):
        # Slugs with spaces/special chars are rejected by our regex
        resp = client.get("/preview/a b c!@")
        assert resp.status_code in (400, 404)  # FastAPI may reject the path first

    def test_slug_too_short(self, client):
        resp = client.get("/preview/ab")
        assert resp.status_code == 400
