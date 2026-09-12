"""Thin client for Nango (nango.dev): mints Connect UI links and reads back the GitHub
profile of a connected user. The iPad never sees the Nango secret key."""

from typing import Any

import httpx

from . import config


class Nango:
    def __init__(self, secret_key: str = config.NANGO_SECRET_KEY, integration: str = config.NANGO_INTEGRATION_ID):
        self.integration = integration
        self.configured = bool(secret_key)
        self._http = httpx.AsyncClient(
            base_url="https://api.nango.dev",
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=httpx.Timeout(15, connect=10),
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def create_session(self, user_id: str) -> dict[str, Any]:
        """Hosted Connect UI link for this user, valid 30 minutes."""
        body = {"tags": {"end_user_id": user_id}, "allowed_integrations": [self.integration]}
        r = await self._http.post("/connect/sessions", json=body)
        r.raise_for_status()
        data = r.json()["data"]
        return {"connect_link": data["connect_link"], "expires_at": data.get("expires_at")}

    async def find_connection(self, user_id: str) -> str | None:
        """Newest connection id tagged with this user, or None."""
        r = await self._http.get("/connection", params={"tags[end_user_id]": user_id})
        r.raise_for_status()
        conns = [c for c in r.json().get("connections", []) if c.get("provider_config_key") == self.integration]
        if not conns:
            return None
        conns.sort(key=lambda c: c.get("created") or "", reverse=True)
        return conns[0]["connection_id"]

    async def github_user(self, connection_id: str) -> dict[str, Any]:
        """GitHub /user via Nango's proxy; Nango injects and refreshes the token."""
        r = await self._http.get(
            "/proxy/user",
            headers={"Connection-Id": connection_id, "Provider-Config-Key": self.integration},
        )
        r.raise_for_status()
        u = r.json()
        return {"login": u.get("login"), "avatar_url": u.get("avatar_url"), "name": u.get("name")}
