def test_openapi_schema_served():
    from rest_framework.test import APIClient

    resp = APIClient().get("/api/schema/")
    assert resp.status_code == 200
    assert b"ModelScope AI API" in resp.content


def test_error_envelope_consistent():
    from rest_framework.test import APIClient

    resp = APIClient().get("/api/v1/does-not-exist/")
    assert resp.status_code == 404
    assert "error" in resp.json()
