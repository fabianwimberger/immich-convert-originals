"""Immich API client."""

import os
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests


@dataclass(frozen=True)
class Asset:
    """An Immich asset from search results."""

    id: str
    original_file_name: str
    original_path: str
    original_mime_type: str | None
    type: str
    device_asset_id: str
    device_id: str
    file_created_at: str
    file_modified_at: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Asset":
        return cls(
            id=data["id"],
            original_file_name=data["originalFileName"],
            original_path=data["originalPath"],
            original_mime_type=data.get("originalMimeType"),
            type=data["type"],
            device_asset_id=data["deviceAssetId"],
            device_id=data["deviceId"],
            file_created_at=data["fileCreatedAt"],
            file_modified_at=data["fileModifiedAt"],
        )


class ImmichClient:
    """Client for Immich HTTP API."""

    def __init__(self, api_base: str, api_key: str, retry_max: int = 3, retry_backoff: int = 2,
                 timeout: tuple[int, int] = (10, 300)):
        self.api_base = api_base
        self.api_key = api_key
        self.retry_max = retry_max
        self.retry_backoff = retry_backoff
        self._default_headers = {"x-api-key": api_key}
        self._timeout = timeout  # (connect_timeout, read_timeout)

    def _request_with_retry(self, method: str, url: str, **kwargs) -> requests.Response:
        last_error = None
        extra_headers = kwargs.pop("headers", {})
        merged_headers = {**self._default_headers, **extra_headers}

        for attempt in range(self.retry_max + 1):
            try:
                response = requests.request(method, url, headers=merged_headers, timeout=self._timeout, **kwargs)

                if response.status_code == 401:
                    raise RuntimeError("Authentication failed - check IMMICH_API_KEY") from None
                if response.status_code == 403:
                    raise RuntimeError("Forbidden - API key lacks required permissions") from None
                if response.status_code == 404:
                    return response

                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self.retry_max:
                        time.sleep(self.retry_backoff * (2**attempt))
                        continue

                return response

            except requests.RequestException as e:
                last_error = e
                if attempt < self.retry_max:
                    time.sleep(self.retry_backoff * (2**attempt))
                    continue
                raise RuntimeError(f"Request failed: {e}") from e

        if last_error:
            raise RuntimeError(f"Request failed: {last_error}")
        return None  # type: ignore

    def search_assets(
        self,
        page: int,
        size: int,
        asset_type: str,
        with_archived: bool = False,
        with_deleted: bool = False,
        original_filename: str | None = None,
        original_path: str | None = None,
        taken_after: str | None = None,
        taken_before: str | None = None,
    ) -> list[Asset]:
        """Search for assets of a given type."""
        url = urljoin(self.api_base, "search/metadata")

        body: dict[str, Any] = {
            "type": asset_type,
            "page": page,
            "size": size,
            "order": "asc",
            "withArchived": with_archived,
            "withDeleted": with_deleted,
        }

        if original_filename:
            body["originalFileName"] = original_filename
        if original_path:
            body["originalPath"] = original_path
        if taken_after:
            body["takenAfter"] = taken_after
        if taken_before:
            body["takenBefore"] = taken_before

        response = self._request_with_retry("POST", url, json=body)
        if response.status_code != 200:
            raise RuntimeError(f"Search failed: HTTP {response.status_code}")

        data = response.json()
        items = data.get("assets", {}).get("items", [])
        return [Asset.from_dict(item) for item in items]

    def download_original(self, asset_id: str, output_path: str) -> tuple[int, str | None]:
        """Download original asset binary to file."""
        url = urljoin(self.api_base, f"assets/{asset_id}/original")

        try:
            response = self._request_with_retry("GET", url, stream=True)
            if response.status_code != 200:
                response.close()
                return 0, f"Download failed: HTTP {response.status_code}"

            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            response.close()

            size = os.path.getsize(output_path)
            return size, None
        except Exception as e:
            return 0, f"Download failed: {e}"

    def test_connection(self) -> tuple[bool, str | None]:
        """Test API connection and permissions."""
        try:
            self.search_assets(page=1, size=1, asset_type="IMAGE")
            return True, None
        except Exception as e:
            return False, str(e)

    def get_asset(self, asset_id: str) -> tuple[bool, str | None]:
        """Verify an asset exists by ID."""
        url = urljoin(self.api_base, f"assets/{asset_id}")
        try:
            response = self._request_with_retry("GET", url)
            if response.status_code == 200:
                return True, None
            return False, f"Asset not found: HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)

    def upload_asset(
        self,
        file_path: str,
        device_asset_id: str,
        device_id: str,
        file_created_at: str,
        file_modified_at: str,
        filename: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Upload a new asset. Returns (asset_id, error)."""
        url = urljoin(self.api_base, "assets")

        data = {
            "deviceAssetId": device_asset_id,
            "deviceId": device_id,
            "fileCreatedAt": file_created_at,
            "fileModifiedAt": file_modified_at,
        }
        if filename:
            data["filename"] = filename

        last_error = None
        for attempt in range(self.retry_max + 1):
            try:
                with open(file_path, "rb") as f:
                    files = {"assetData": f}
                    response = requests.request(
                        "POST", url, headers=self._default_headers,
                        files=files, data=data, timeout=self._timeout,
                    )

                    if response.status_code == 401:
                        return None, "Authentication failed - check IMMICH_API_KEY"
                    if response.status_code == 403:
                        return None, "Forbidden - API key lacks required permissions"

                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < self.retry_max:
                            time.sleep(self.retry_backoff * (2 ** attempt))
                            continue

                    if response.status_code in (200, 201):
                        result = response.json()
                        asset_id = result.get("id")
                        return asset_id, None
                    else:
                        try:
                            error_detail = response.json()
                            error_msg = error_detail.get("message", str(error_detail))
                        except Exception:
                            error_msg = response.text or "Unknown error"
                        return None, f"Upload failed: HTTP {response.status_code} - {error_msg}"
            except requests.RequestException as e:
                last_error = e
                if attempt < self.retry_max:
                    time.sleep(self.retry_backoff * (2 ** attempt))
                    continue
            except Exception as e:
                return None, str(e)

        return None, f"Upload failed after retries: {last_error}"

    def copy_asset_data(
        self,
        from_asset_id: str,
        to_asset_id: str,
    ) -> tuple[bool, str | None]:
        """Copy asset data (albums, favorites, etc.) from one asset to another."""
        url = urljoin(self.api_base, "assets/copy")

        body = {
            "sourceId": from_asset_id,
            "targetId": to_asset_id,
            "albums": True,
            "favorite": True,
            "sharedLinks": True,
            "sidecar": True,
            "stack": True,
        }

        try:
            response = self._request_with_retry("PUT", url, json=body)
            if response.status_code == 204:
                return True, None
            try:
                error_detail = response.json()
                error_msg = error_detail.get("message", str(error_detail))
            except Exception:
                error_msg = response.text or "Unknown error"
            return False, f"Copy failed: HTTP {response.status_code} - {error_msg}"
        except Exception as e:
            return False, str(e)

    def delete_assets(self, asset_ids: list[str]) -> tuple[bool, str | None]:
        """Delete assets by ID."""
        url = urljoin(self.api_base, "assets")
        body = {"ids": asset_ids}
        try:
            response = self._request_with_retry("DELETE", url, json=body)
            if response.status_code == 204:
                return True, None
            return False, f"Delete failed: HTTP {response.status_code}"
        except Exception as e:
            return False, str(e)
