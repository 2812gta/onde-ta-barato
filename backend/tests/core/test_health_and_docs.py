def test_health_ok(api, db):
    response = api.get("/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_is_generated(api, db):
    response = api.get("/api/schema/")
    assert response.status_code == 200
    body = response.content.decode()
    assert "/api/v1/auth/login/" in body
    assert "/api/v1/me/" in body
