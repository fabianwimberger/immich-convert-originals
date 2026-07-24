"""Tests for the settings API routes."""

import responses


class TestHealth:
    async def test_health_check(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}


class TestReadSettings:
    async def test_defaults_after_seed(self, client):
        resp = await client.get("/api/settings")
        assert resp.status_code == 200
        data = resp.json()
        assert data["immich_api_base"] == ""
        assert data["immich_api_key_set"] is False
        assert data["asset_types"] == "IMAGE,VIDEO"
        assert data["concurrency"] == 2
        assert data["convert_image_formats"] == "jpg,png,webp,heic,avif,tiff,gif,bmp"


class TestUpdateSettings:
    async def test_partial_update_only_changes_given_fields(self, client):
        resp = await client.put("/api/settings", json={"video_crf": 30})
        assert resp.status_code == 200
        data = resp.json()
        assert data["video_crf"] == 30
        assert data["video_preset"] == 4  # unchanged

    async def test_update_persists(self, client):
        await client.put("/api/settings", json={"concurrency": 5})
        resp = await client.get("/api/settings")
        assert resp.json()["concurrency"] == 5

    async def test_setting_api_key_reflects_in_key_set_flag(self, client):
        resp = await client.put("/api/settings", json={"immich_api_key": "secret-key"})
        assert resp.json()["immich_api_key_set"] is True
        assert "secret-key" not in resp.text

    async def test_out_of_range_video_crf_rejected(self, client):
        resp = await client.put("/api/settings", json={"video_crf": 999})
        assert resp.status_code == 422

    async def test_convert_image_formats_persists(self, client):
        resp = await client.put(
            "/api/settings", json={"convert_image_formats": "jpg,heic"}
        )
        assert resp.json()["convert_image_formats"] == "jpg,heic"


class TestConnectionCheck:
    async def test_missing_credentials(self, client):
        resp = await client.post("/api/settings/test-connection", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is False
        assert "required" in data["error"]

    @responses.activate
    async def test_success_reports_server_version(self, client):
        responses.add(
            responses.POST,
            "https://immich.example.com/api/search/metadata",
            json={"assets": {"items": []}},
        )
        responses.add(
            responses.GET,
            "https://immich.example.com/api/server/version",
            json={"major": 3, "minor": 0, "patch": 3},
        )
        resp = await client.post(
            "/api/settings/test-connection",
            json={
                "immich_api_base": "https://immich.example.com/api/",
                "immich_api_key": "key",
            },
        )
        data = resp.json()
        assert data["ok"] is True
        assert data["server_version"] == "3.0.3"

    @responses.activate
    async def test_uses_saved_credentials_when_override_omitted(self, client):
        await client.put(
            "/api/settings",
            json={
                "immich_api_base": "https://saved.example.com/api/",
                "immich_api_key": "saved-key",
            },
        )
        responses.add(
            responses.POST,
            "https://saved.example.com/api/search/metadata",
            json={"assets": {"items": []}},
        )
        resp = await client.post("/api/settings/test-connection", json={})
        assert resp.json()["ok"] is True
