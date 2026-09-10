"""Business presentation settings cannot grant roles or change accounting data."""

import pytest
from backend.app.db.database import SessionLocal
from backend.app.db.models import User
from fastapi.testclient import TestClient
from sqlalchemy import select


@pytest.mark.parametrize("category", ["RETAIL", "EDUCATION", "ONLINE", "SERVICES"])
def test_register_business_profile_and_persist(client: TestClient, category: str) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={
            "email": "profile@example.com",
            "password": "profile-test-password-123",
            "first_name": "Demo",
            "last_name": "Owner",
            "business_category": category,
        },
    )
    assert response.status_code == 201
    assert response.json()["business_category"] == category
    assert response.json()["roles"] == ["OWNER"]
    assert response.json()["plan_status"] == "FREE"
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == "profile@example.com"))
        assert user is not None and user.business_category == category


def test_profile_update_is_self_only_and_preserves_finances(client: TestClient) -> None:
    for email in ["profile@example.com", "other@example.com"]:
        created = client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "password": "profile-test-password-123",
                "first_name": "Demo",
                "last_name": "Owner",
            },
        )
        assert created.status_code == 201
        assert created.json()["business_category"] == "RETAIL"
    login = client.post(
        "/api/v1/auth/login",
        json={
            "email": "profile@example.com",
            "password": "profile-test-password-123",
        },
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    original = client.get("/api/v1/auth/me", headers=headers).json()
    party = client.post(
        "/api/v1/parties", headers=headers, json={"name": "Existing customer", "is_customer": True}
    ).json()
    dashboard = client.get("/api/v1/dashboard", headers=headers).json()
    for category in ["EDUCATION", "ONLINE", "SERVICES", "RETAIL"]:
        response = client.patch(
            "/api/v1/auth/me/business-profile",
            headers=headers,
            json={"business_category": category},
        )
        assert response.status_code == 200
        assert response.json()["business_category"] == category
        assert response.json()["roles"] == original["roles"]
        assert response.json()["permissions"] == original["permissions"]
        assert response.json()["plan_status"] == "FREE"
        assert (
            client.get("/api/v1/auth/me", headers=headers).json()["business_category"] == category
        )
        assert client.get("/api/v1/dashboard", headers=headers).json() == dashboard
        assert client.get(f"/api/v1/parties/{party['id']}", headers=headers).json() == party
    with SessionLocal() as session:
        other = session.scalar(select(User).where(User.email == "other@example.com"))
        assert other is not None and other.business_category == "RETAIL"
    for extra in [{"roles": ["ADMIN"]}, {"plan_status": "PRO"}, {"user_id": original["id"]}]:
        assert (
            client.patch(
                "/api/v1/auth/me/business-profile",
                headers=headers,
                json={"business_category": "ONLINE", **extra},
            ).status_code
            == 422
        )
    assert (
        client.patch(
            "/api/v1/auth/me/business-profile",
            headers=headers,
            json={"business_category": "UNKNOWN"},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            "/api/v1/auth/me/business-profile", json={"business_category": "ONLINE"}
        ).status_code
        == 401
    )


def test_registration_rejects_unknown_profile(client: TestClient) -> None:
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "email": "profile@example.com",
                "password": "profile-test-password-123",
                "first_name": "Demo",
                "last_name": "Owner",
                "business_category": "UNKNOWN",
            },
        ).status_code
        == 422
    )
