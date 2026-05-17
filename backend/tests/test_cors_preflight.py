def test_cors_preflight_for_skills(client):
    resp = client.options(
        "/skills",
        headers={
            "Origin": "http://localhost:1420",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "content-type,x-user,x-api-key",
        },
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:1420"
