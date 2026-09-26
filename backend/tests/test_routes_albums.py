"""Tests for the album listing route."""

import responses


async def _configure_connection(client):
    await client.put(
        "/api/settings",
        json={
            "immich_api_base": "https://immich.example.com/api/",
            "immich_api_key": "key",
        },
    )


class TestListAlbumsUnconfigured:
    async def test_returns_424_when_not_configured(self, client):
        resp = await client.get("/api/albums")
        assert resp.status_code == 424


class TestListAlbums:
    @responses.activate
    async def test_sorts_alphabetically_case_insensitively(self, client):
        await _configure_connection(client)
        responses.add(
            responses.GET,
            "https://immich.example.com/api/albums",
            json=[
                {"id": "a3", "albumName": "zebra", "assetCount": 1},
                {"id": "a1", "albumName": "Apple", "assetCount": 2},
                {"id": "a2", "albumName": "banana", "assetCount": 3},
            ],
        )
        resp = await client.get("/api/albums")
        assert resp.status_code == 200
        assert [a["album_name"] for a in resp.json()["items"]] == [
            "Apple",
            "banana",
            "zebra",
        ]

    @responses.activate
    async def test_empty_list(self, client):
        await _configure_connection(client)
        responses.add(responses.GET, "https://immich.example.com/api/albums", json=[])
        resp = await client.get("/api/albums")
        assert resp.status_code == 200
        assert resp.json()["items"] == []
