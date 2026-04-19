"""Tests for immich_api module using responses to mock HTTP."""

import json

import pytest
import requests
import responses

from app.immich_api import Asset, ImmichClient


@pytest.fixture
def client() -> ImmichClient:
    return ImmichClient(
        api_base="https://example.com/api/",
        api_key="test_key",
        retry_max=2,
        retry_backoff=0,
    )


class TestAssetFromDict:
    def test_full_dict(self):
        data = {
            "id": "asset-1",
            "originalFileName": "photo.jpg",
            "originalPath": "/uploads/photo.jpg",
            "originalMimeType": "image/jpeg",
            "type": "IMAGE",
            "deviceAssetId": "device-1",
            "deviceId": "phone-1",
            "fileCreatedAt": "2023-01-01T00:00:00Z",
            "fileModifiedAt": "2023-01-01T00:00:00Z",
        }
        asset = Asset.from_dict(data)
        assert asset.id == "asset-1"
        assert asset.original_file_name == "photo.jpg"
        assert asset.original_mime_type == "image/jpeg"

    def test_missing_optional_mime_type(self):
        data = {
            "id": "asset-2",
            "originalFileName": "photo.jpg",
            "originalPath": "/uploads/photo.jpg",
            "type": "IMAGE",
            "deviceAssetId": "device-1",
            "deviceId": "phone-1",
            "fileCreatedAt": "2023-01-01T00:00:00Z",
            "fileModifiedAt": "2023-01-01T00:00:00Z",
        }
        asset = Asset.from_dict(data)
        assert asset.original_mime_type is None

    def test_unexpected_types_still_parse(self):
        data = {
            "id": "asset-3",
            "originalFileName": 123,
            "originalPath": None,
            "originalMimeType": "image/jpeg",
            "type": "VIDEO",
            "deviceAssetId": "d1",
            "deviceId": "p1",
            "fileCreatedAt": "2023-01-01T00:00:00Z",
            "fileModifiedAt": "2023-01-01T00:00:00Z",
        }
        asset = Asset.from_dict(data)
        assert asset.original_file_name == 123
        assert asset.original_path is None


class TestRequestWithRetry:
    @responses.activate
    def test_retries_on_429_with_backoff(self, client, monkeypatch):
        monkeypatch.setattr("app.immich_api.time.sleep", lambda s: None)
        responses.add(responses.GET, "https://example.com/api/test", status=429)
        responses.add(responses.GET, "https://example.com/api/test", status=429)
        responses.add(responses.GET, "https://example.com/api/test", json={"ok": True})

        response = client._request_with_retry("GET", "https://example.com/api/test")
        assert response.status_code == 200
        assert len(responses.calls) == 3

    @responses.activate
    def test_retries_on_500(self, client, monkeypatch):
        monkeypatch.setattr("app.immich_api.time.sleep", lambda s: None)
        responses.add(responses.GET, "https://example.com/api/test", status=500)
        responses.add(responses.GET, "https://example.com/api/test", json={"ok": True})

        response = client._request_with_retry("GET", "https://example.com/api/test")
        assert response.status_code == 200
        assert len(responses.calls) == 2

    @responses.activate
    def test_raises_on_401(self, client):
        responses.add(responses.GET, "https://example.com/api/test", status=401)
        with pytest.raises(RuntimeError, match="Authentication failed"):
            client._request_with_retry("GET", "https://example.com/api/test")

    @responses.activate
    def test_raises_on_403(self, client):
        responses.add(responses.GET, "https://example.com/api/test", status=403)
        with pytest.raises(RuntimeError, match="Forbidden"):
            client._request_with_retry("GET", "https://example.com/api/test")

    @responses.activate
    def test_no_retry_on_404(self, client):
        responses.add(responses.GET, "https://example.com/api/test", status=404)
        response = client._request_with_retry("GET", "https://example.com/api/test")
        assert response.status_code == 404
        assert len(responses.calls) == 1

    @responses.activate
    def test_request_exception_raises_after_retries(self, client, monkeypatch):
        monkeypatch.setattr("app.immich_api.time.sleep", lambda s: None)
        responses.add(
            responses.GET,
            "https://example.com/api/test",
            body=requests.RequestException("boom"),
        )
        responses.add(
            responses.GET,
            "https://example.com/api/test",
            body=requests.RequestException("boom"),
        )
        responses.add(
            responses.GET,
            "https://example.com/api/test",
            body=requests.RequestException("boom"),
        )
        with pytest.raises(RuntimeError, match="Request failed"):
            client._request_with_retry("GET", "https://example.com/api/test")


class TestSearchAssets:
    @responses.activate
    def test_pagination_body_shape(self, client):
        responses.add(
            responses.POST,
            "https://example.com/api/search/metadata",
            json={"assets": {"items": []}},
        )
        result = client.search_assets(page=2, size=100, asset_type="IMAGE")
        assert result == []
        body = json.loads(responses.calls[0].request.body)
        assert body == {
            "type": "IMAGE",
            "page": 2,
            "size": 100,
            "order": "asc",
            "withArchived": False,
            "withDeleted": False,
        }

    @responses.activate
    def test_date_filters_included_when_set(self, client):
        responses.add(
            responses.POST,
            "https://example.com/api/search/metadata",
            json={"assets": {"items": []}},
        )
        client.search_assets(
            page=1,
            size=10,
            asset_type="VIDEO",
            taken_after="2023-01-01T00:00:00Z",
            taken_before="2023-12-31T23:59:59Z",
        )
        body = json.loads(responses.calls[0].request.body)
        assert body["takenAfter"] == "2023-01-01T00:00:00Z"
        assert body["takenBefore"] == "2023-12-31T23:59:59Z"

    @responses.activate
    def test_date_filters_omitted_when_none(self, client):
        responses.add(
            responses.POST,
            "https://example.com/api/search/metadata",
            json={"assets": {"items": []}},
        )
        client.search_assets(page=1, size=10, asset_type="IMAGE")
        body = json.loads(responses.calls[0].request.body)
        assert "takenAfter" not in body
        assert "takenBefore" not in body

    @responses.activate
    def test_returns_asset_dataclasses(self, client):
        responses.add(
            responses.POST,
            "https://example.com/api/search/metadata",
            json={
                "assets": {
                    "items": [
                        {
                            "id": "a1",
                            "originalFileName": "x.jpg",
                            "originalPath": "/p/x.jpg",
                            "originalMimeType": "image/jpeg",
                            "type": "IMAGE",
                            "deviceAssetId": "d1",
                            "deviceId": "p1",
                            "fileCreatedAt": "2023-01-01T00:00:00Z",
                            "fileModifiedAt": "2023-01-01T00:00:00Z",
                        }
                    ]
                }
            },
        )
        result = client.search_assets(page=1, size=10, asset_type="IMAGE")
        assert len(result) == 1
        assert isinstance(result[0], Asset)
        assert result[0].id == "a1"

    @responses.activate
    def test_non_200_raises(self, client):
        responses.add(
            responses.POST, "https://example.com/api/search/metadata", status=500
        )
        with pytest.raises(RuntimeError, match="Search failed: HTTP 500"):
            client.search_assets(page=1, size=10, asset_type="IMAGE")


class TestDownloadOriginal:
    @responses.activate
    def test_streams_bytes_and_returns_size(self, client, tmp_path):
        responses.add(
            responses.GET,
            "https://example.com/api/assets/a1/original",
            body=b"hello world",
            status=200,
        )
        out_path = str(tmp_path / "downloaded.bin")
        size, error = client.download_original("a1", out_path)
        assert size == 11
        assert error is None
        with open(out_path, "rb") as f:
            assert f.read() == b"hello world"

    @responses.activate
    def test_404_returns_error_tuple(self, client, tmp_path):
        responses.add(
            responses.GET,
            "https://example.com/api/assets/a1/original",
            status=404,
        )
        out_path = str(tmp_path / "downloaded.bin")
        size, error = client.download_original("a1", out_path)
        assert size == 0
        assert "Download failed: HTTP 404" in error

    @responses.activate
    def test_500_returns_error_tuple(self, client, tmp_path):
        responses.add(
            responses.GET,
            "https://example.com/api/assets/a1/original",
            status=500,
        )
        out_path = str(tmp_path / "downloaded.bin")
        size, error = client.download_original("a1", out_path)
        assert size == 0
        assert "Download failed: HTTP 500" in error


class TestUploadAsset:
    @responses.activate
    def test_happy_path_returns_id(self, client, tmp_path):
        responses.add(
            responses.POST,
            "https://example.com/api/assets",
            json={"id": "new-asset-1"},
            status=201,
        )
        file_path = tmp_path / "upload.bin"
        file_path.write_bytes(b"data")
        asset_id, error = client.upload_asset(
            file_path=str(file_path),
            device_asset_id="da1",
            device_id="phone1",
            file_created_at="2023-01-01T00:00:00Z",
            file_modified_at="2023-01-01T00:00:00Z",
            filename="upload.bin",
        )
        assert asset_id == "new-asset-1"
        assert error is None

    @responses.activate
    def test_retries_on_500(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("app.immich_api.time.sleep", lambda s: None)
        responses.add(responses.POST, "https://example.com/api/assets", status=500)
        responses.add(
            responses.POST,
            "https://example.com/api/assets",
            json={"id": "new-asset-2"},
            status=201,
        )
        file_path = tmp_path / "upload.bin"
        file_path.write_bytes(b"data")
        asset_id, error = client.upload_asset(
            file_path=str(file_path),
            device_asset_id="da1",
            device_id="phone1",
            file_created_at="2023-01-01T00:00:00Z",
            file_modified_at="2023-01-01T00:00:00Z",
        )
        assert asset_id == "new-asset-2"
        assert error is None

    @responses.activate
    def test_error_extracts_json_message(self, client, tmp_path):
        responses.add(
            responses.POST,
            "https://example.com/api/assets",
            json={"message": "Bad request"},
            status=400,
        )
        file_path = tmp_path / "upload.bin"
        file_path.write_bytes(b"data")
        asset_id, error = client.upload_asset(
            file_path=str(file_path),
            device_asset_id="da1",
            device_id="phone1",
            file_created_at="2023-01-01T00:00:00Z",
            file_modified_at="2023-01-01T00:00:00Z",
        )
        assert asset_id is None
        assert "Bad request" in error

    @responses.activate
    def test_error_falls_back_to_text(self, client, tmp_path):
        responses.add(
            responses.POST,
            "https://example.com/api/assets",
            body="plain text error",
            status=400,
        )
        file_path = tmp_path / "upload.bin"
        file_path.write_bytes(b"data")
        asset_id, error = client.upload_asset(
            file_path=str(file_path),
            device_asset_id="da1",
            device_id="phone1",
            file_created_at="2023-01-01T00:00:00Z",
            file_modified_at="2023-01-01T00:00:00Z",
        )
        assert asset_id is None
        assert "plain text error" in error


class TestCopyAssetData:
    @responses.activate
    def test_happy_path(self, client):
        responses.add(responses.PUT, "https://example.com/api/assets/copy", status=204)
        success, error = client.copy_asset_data("src", "dst")
        assert success is True
        assert error is None

    @responses.activate
    def test_error_path(self, client):
        responses.add(
            responses.PUT,
            "https://example.com/api/assets/copy",
            json={"message": "Not found"},
            status=404,
        )
        success, error = client.copy_asset_data("src", "dst")
        assert success is False
        assert "Not found" in error


class TestDeleteAssets:
    @responses.activate
    def test_happy_path(self, client):
        responses.add(responses.DELETE, "https://example.com/api/assets", status=204)
        success, error = client.delete_assets(["a1", "a2"])
        assert success is True
        assert error is None

    @responses.activate
    def test_error_path(self, client):
        responses.add(responses.DELETE, "https://example.com/api/assets", status=500)
        success, error = client.delete_assets(["a1"])
        assert success is False
        assert "Delete failed: HTTP 500" in error


class TestGetAlbumAssets:
    @responses.activate
    def test_happy_path(self, client):
        responses.add(
            responses.GET,
            "https://example.com/api/albums/album-1",
            json={
                "assets": [
                    {
                        "id": "a1",
                        "originalFileName": "x.jpg",
                        "originalPath": "/p/x.jpg",
                        "type": "IMAGE",
                        "deviceAssetId": "d1",
                        "deviceId": "p1",
                        "fileCreatedAt": "2023-01-01T00:00:00Z",
                        "fileModifiedAt": "2023-01-01T00:00:00Z",
                    }
                ]
            },
        )
        result = client.get_album_assets("album-1")
        assert len(result) == 1
        assert result[0].id == "a1"

    @responses.activate
    def test_error_raises(self, client):
        responses.add(
            responses.GET, "https://example.com/api/albums/album-1", status=404
        )
        with pytest.raises(RuntimeError, match="Failed to get album: HTTP 404"):
            client.get_album_assets("album-1")


class TestServerInfo:
    @responses.activate
    def test_happy_path(self, client):
        responses.add(
            responses.GET,
            "https://example.com/api/server/version",
            json={"major": 1, "minor": 2, "patch": 3},
        )
        info = client.server_info()
        assert info == {"major": 1, "minor": 2, "patch": 3}

    @responses.activate
    def test_non_200_returns_none(self, client):
        responses.add(
            responses.GET, "https://example.com/api/server/version", status=500
        )
        assert client.server_info() is None

    @responses.activate
    def test_exception_returns_none(self, client):
        responses.add(
            responses.GET,
            "https://example.com/api/server/version",
            body=requests.ConnectionError("refused"),
        )
        assert client.server_info() is None


class TestListAlbums:
    @responses.activate
    def test_happy_path(self, client):
        responses.add(
            responses.GET,
            "https://example.com/api/albums",
            json=[
                {
                    "id": "album-1",
                    "albumName": "Vacation",
                    "assetCount": 42,
                },
                {
                    "id": "album-2",
                    "albumName": "Screenshots",
                    "assetCount": 3,
                },
            ],
        )
        albums = client.list_albums()
        assert len(albums) == 2
        assert albums[0]["id"] == "album-1"
        assert albums[0]["album_name"] == "Vacation"
        assert albums[0]["asset_count"] == 42

    @responses.activate
    def test_empty_list(self, client):
        responses.add(
            responses.GET,
            "https://example.com/api/albums",
            json=[],
        )
        albums = client.list_albums()
        assert albums == []

    @responses.activate
    def test_error_raises(self, client):
        responses.add(responses.GET, "https://example.com/api/albums", status=500)
        with pytest.raises(RuntimeError, match="Failed to list albums: HTTP 500"):
            client.list_albums()
