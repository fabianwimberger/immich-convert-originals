"""Tests for the asset browsing API routes."""

import responses


async def _configure_connection(client):
    await client.put(
        "/api/settings",
        json={
            "immich_api_base": "https://immich.example.com/api/",
            "immich_api_key": "key",
        },
    )


class TestListAssetsUnconfigured:
    async def test_returns_424_when_not_configured(self, client):
        resp = await client.get("/api/assets")
        assert resp.status_code == 424


class TestListAssets:
    @responses.activate
    async def test_search_path(self, client):
        await _configure_connection(client)
        responses.add(
            responses.POST,
            "https://immich.example.com/api/search/metadata",
            json={
                "assets": {
                    "items": [
                        {
                            "id": "a1",
                            "originalFileName": "photo.jxl",
                            "originalPath": "/p/photo.jxl",
                            "originalMimeType": "image/jxl",
                            "type": "IMAGE",
                            "fileCreatedAt": "2023-01-01T00:00:00Z",
                            "fileModifiedAt": "2023-01-01T00:00:00Z",
                        },
                        {
                            "id": "a2",
                            "originalFileName": "photo.jpg",
                            "originalPath": "/p/photo.jpg",
                            "originalMimeType": "image/jpeg",
                            "type": "IMAGE",
                            "fileCreatedAt": "2023-01-01T00:00:00Z",
                            "fileModifiedAt": "2023-01-01T00:00:00Z",
                        },
                    ]
                }
            },
        )
        resp = await client.get("/api/assets", params={"asset_type": "IMAGE"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["page"] == 1
        assert len(data["items"]) == 2
        assert data["items"][0]["already_jxl"] is True
        assert data["items"][1]["already_jxl"] is False

    @responses.activate
    async def test_album_path_filters_by_type_and_paginates(self, client):
        await _configure_connection(client)
        responses.add(
            responses.POST,
            "https://immich.example.com/api/search/metadata",
            json={
                "assets": {
                    "items": [
                        {
                            "id": f"a{i}",
                            "originalFileName": f"f{i}.jpg",
                            "originalPath": f"/p/f{i}.jpg",
                            "originalMimeType": "image/jpeg",
                            "type": "IMAGE",
                            "fileCreatedAt": "2023-01-01T00:00:00Z",
                            "fileModifiedAt": "2023-01-01T00:00:00Z",
                        }
                        for i in range(3)
                    ]
                }
            },
        )
        responses.add(
            responses.POST,
            "https://immich.example.com/api/search/metadata",
            json={"assets": {"items": []}},
        )
        resp = await client.get(
            "/api/assets",
            params={"asset_type": "IMAGE", "album_id": "album-1", "size": 2},
        )
        data = resp.json()
        assert len(data["items"]) == 2
        assert data["has_more"] is True

    @responses.activate
    async def test_upstream_error_returns_502(self, client, monkeypatch):
        monkeypatch.setattr("app.services.immich_client.time.sleep", lambda s: None)
        await _configure_connection(client)
        responses.add(
            responses.POST,
            "https://immich.example.com/api/search/metadata",
            status=500,
        )
        resp = await client.get("/api/assets")
        assert resp.status_code == 502


class TestThumbnail:
    @responses.activate
    async def test_proxies_image_bytes(self, client):
        await _configure_connection(client)
        responses.add(
            responses.GET,
            "https://immich.example.com/api/assets/a1/thumbnail",
            body=b"fake-image-bytes",
            content_type="image/jpeg",
        )
        resp = await client.get("/api/assets/a1/thumbnail")
        assert resp.status_code == 200
        assert resp.content == b"fake-image-bytes"
        assert resp.headers["content-type"] == "image/jpeg"

    @responses.activate
    async def test_upstream_failure_returns_502(self, client):
        await _configure_connection(client)
        responses.add(
            responses.GET,
            "https://immich.example.com/api/assets/a1/thumbnail",
            status=404,
        )
        resp = await client.get("/api/assets/a1/thumbnail")
        assert resp.status_code == 502


class TestListAlbums:
    @responses.activate
    async def test_happy_path(self, client):
        await _configure_connection(client)
        responses.add(
            responses.GET,
            "https://immich.example.com/api/albums",
            json=[{"id": "album-1", "albumName": "Vacation", "assetCount": 12}],
        )
        resp = await client.get("/api/albums")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == [
            {"id": "album-1", "album_name": "Vacation", "asset_count": 12}
        ]

    async def test_returns_424_when_not_configured(self, client):
        resp = await client.get("/api/albums")
        assert resp.status_code == 424
