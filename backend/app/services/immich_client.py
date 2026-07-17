"""Immich API client."""

import base64
import hashlib
import os
import random
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
            file_created_at=data["fileCreatedAt"],
            file_modified_at=data["fileModifiedAt"],
        )


class ImmichClient:
    """Client for Immich HTTP API."""

    def __init__(
        self,
        api_base: str,
        api_key: str,
        retry_max: int = 3,
        retry_backoff: int = 2,
        timeout: tuple[int, int] = (10, 300),
    ):
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
            response = None
            try:
                response = requests.request(
                    method, url, headers=merged_headers, timeout=self._timeout, **kwargs
                )

                if response.status_code == 401:
                    raise RuntimeError(
                        "Authentication failed - check IMMICH_API_KEY"
                    ) from None
                if response.status_code == 403:
                    raise RuntimeError(
                        "Forbidden - API key lacks required permissions"
                    ) from None
                if response.status_code == 404:
                    return response

                if response.status_code == 429 or response.status_code >= 500:
                    if attempt < self.retry_max:
                        if response is not None:
                            response.close()
                        time.sleep(
                            self.retry_backoff * (2**attempt) * random.uniform(0.5, 1.5)
                        )
                        continue

                return response

            except requests.RequestException as e:
                last_error = e
                if attempt < self.retry_max:
                    if response is not None:
                        response.close()
                    time.sleep(
                        self.retry_backoff * (2**attempt) * random.uniform(0.5, 1.5)
                    )
                    continue
                raise RuntimeError(f"Request failed: {e}") from e
            finally:
                # If we're retrying, ensure the response body is consumed/closed
                # to prevent connection-pool leaks on streamed requests.
                if response is not None and response.status_code in (
                    429,
                    500,
                    502,
                    503,
                    504,
                ):
                    response.close()

        if last_error:
            raise RuntimeError(f"Request failed: {last_error}")
        # Unreachable — kept only to satisfy type checker.
        raise RuntimeError("Request failed after exhausting all retries")

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
            "withDeleted": with_deleted,
        }
        if not with_archived:
            # Immich has no "exclude archived" flag; restrict to timeline
            # visibility instead. Omitting this when with_archived=True
            # returns everything except locked (pin-protected) assets,
            # which this tool must never touch.
            body["visibility"] = "timeline"

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

    def get_thumbnail(
        self, asset_id: str, size: str = "thumbnail"
    ) -> tuple[bytes | None, str | None, str | None]:
        """Fetch a thumbnail image. Returns (content, content_type, error)."""
        url = urljoin(self.api_base, f"assets/{asset_id}/thumbnail")
        try:
            response = self._request_with_retry("GET", url, params={"size": size})
            if response.status_code != 200:
                return None, None, f"Thumbnail failed: HTTP {response.status_code}"
            return (
                response.content,
                response.headers.get("content-type", "image/jpeg"),
                None,
            )
        except Exception as e:
            return None, None, str(e)

    def download_original(
        self, asset_id: str, output_path: str
    ) -> tuple[int, str | None]:
        """Download original asset binary to file.

        After download, verifies the file size is non-zero and the SHA1
        checksum matches the value reported by Immich.
        """
        url = urljoin(self.api_base, f"assets/{asset_id}/original")

        # Fetch expected checksum before download
        expected_checksum = self._get_asset_checksum(asset_id)

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
            if size == 0:
                return 0, "Downloaded file is empty"

            if expected_checksum:
                actual_checksum = self._sha1_file(output_path)
                expected_hex = base64.b64decode(expected_checksum).hex()
                if actual_checksum.lower() != expected_hex.lower():
                    return (
                        0,
                        f"Checksum mismatch: expected {expected_checksum}, "
                        f"got {actual_checksum}",
                    )

            return size, None
        except Exception as e:
            return 0, f"Download failed: {e}"

    def _get_asset_checksum(self, asset_id: str) -> str | None:
        """Return the SHA1 checksum reported by Immich for an asset."""
        url = urljoin(self.api_base, f"assets/{asset_id}")
        try:
            response = self._request_with_retry("GET", url)
            if response.status_code == 200:
                data = response.json()
                return data.get("checksum")
        except Exception:
            pass
        return None

    @staticmethod
    def _sha1_file(path: str) -> str:
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

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

    def get_asset_full(self, asset_id: str) -> Asset | None:
        """Fetch full asset metadata by ID, or None if it can't be found."""
        url = urljoin(self.api_base, f"assets/{asset_id}")
        try:
            response = self._request_with_retry("GET", url)
            if response.status_code != 200:
                return None
            return Asset.from_dict(response.json())
        except Exception:
            return None

    def upload_asset(
        self,
        file_path: str,
        file_created_at: str,
        file_modified_at: str,
        filename: str | None = None,
    ) -> tuple[str | None, str | None]:
        """Upload a new asset. Returns (asset_id, error)."""
        url = urljoin(self.api_base, "assets")

        data = {
            "fileCreatedAt": file_created_at,
            "fileModifiedAt": file_modified_at,
        }
        if filename:
            data["filename"] = filename

        upload_filename = filename or os.path.basename(file_path)
        last_error = None
        for attempt in range(self.retry_max + 1):
            try:
                with open(file_path, "rb") as f:
                    files = {"assetData": (upload_filename, f)}
                    response = requests.request(
                        "POST",
                        url,
                        headers=self._default_headers,
                        files=files,
                        data=data,
                        timeout=self._timeout,
                    )

                    if response.status_code == 401:
                        return None, "Authentication failed - check IMMICH_API_KEY"
                    if response.status_code == 403:
                        return None, "Forbidden - API key lacks required permissions"

                    if response.status_code == 429 or response.status_code >= 500:
                        if attempt < self.retry_max:
                            time.sleep(
                                self.retry_backoff
                                * (2**attempt)
                                * random.uniform(0.5, 1.5)
                            )
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
                        return (
                            None,
                            f"Upload failed: HTTP {response.status_code} - {error_msg}",
                        )
            except requests.RequestException as e:
                last_error = e
                if attempt < self.retry_max:
                    time.sleep(
                        self.retry_backoff * (2**attempt) * random.uniform(0.5, 1.5)
                    )
                    continue
            except Exception as e:
                return None, str(e)

        return None, f"Upload failed after retries: {last_error}"

    def copy_asset_data(
        self,
        from_asset_id: str,
        to_asset_id: str,
    ) -> tuple[bool, str | None]:
        """Copy asset metadata (favorite, visibility, rating, albums, stack)
        from one asset to another."""
        # 1. Fetch source asset details
        source_url = urljoin(self.api_base, f"assets/{from_asset_id}")
        try:
            source_resp = self._request_with_retry("GET", source_url)
            if source_resp.status_code != 200:
                return False, (
                    f"Source asset not found: HTTP {source_resp.status_code}"
                )
            source_data = source_resp.json()
        except Exception as e:
            return False, str(e)

        # 2. Bulk-update target asset with favorite / visibility / rating.
        #    Only include fields that were explicitly present in the source
        #    so we don't reset state when the API omits keys.
        update_url = urljoin(self.api_base, "assets")
        update_body: dict[str, Any] = {"ids": [to_asset_id]}
        for key in ("isFavorite", "visibility"):
            if key in source_data:
                update_body[key] = source_data[key]
        if "rating" in source_data:
            rating = source_data["rating"]
            # 0 and -1 are no longer valid rating values; unrated is null.
            update_body["rating"] = rating if rating and 1 <= rating <= 5 else None

        if len(update_body) > 1:  # ids is always present
            try:
                update_resp = self._request_with_retry(
                    "PUT", update_url, json=update_body
                )
                if update_resp.status_code not in (200, 204):
                    try:
                        error_detail = update_resp.json()
                        error_msg = error_detail.get("message", str(error_detail))
                    except Exception:
                        error_msg = update_resp.text or "Unknown error"
                    return False, (
                        f"Update failed: HTTP {update_resp.status_code} - {error_msg}"
                    )
            except Exception as e:
                return False, str(e)

        # 3. Copy album and stack associations from source to target.
        copy_url = urljoin(self.api_base, "assets/copy")
        copy_body = {
            "sourceId": from_asset_id,
            "targetId": to_asset_id,
            "albums": True,
            "stack": True,
            "favorite": False,
            "sharedLinks": False,
            "sidecar": False,
        }
        try:
            copy_resp = self._request_with_retry("PUT", copy_url, json=copy_body)
            if copy_resp.status_code not in (200, 204):
                try:
                    error_detail = copy_resp.json()
                    error_msg = error_detail.get("message", str(error_detail))
                except Exception:
                    error_msg = copy_resp.text or "Unknown error"
                return False, (
                    f"Album copy failed: HTTP {copy_resp.status_code} - {error_msg}"
                )
        except Exception as e:
            return False, f"Album copy failed: {e}"

        return True, None

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

    def server_info(self) -> dict[str, Any] | None:
        """Get server version/info."""
        url = urljoin(self.api_base, "server/version")
        try:
            response = self._request_with_retry("GET", url)
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None

    def list_albums(self) -> list[dict[str, Any]]:
        """List all albums with id, name, and asset count."""
        url = urljoin(self.api_base, "albums")
        response = self._request_with_retry("GET", url)
        if response.status_code != 200:
            raise RuntimeError(f"Failed to list albums: HTTP {response.status_code}")
        data = response.json()
        albums = []
        for item in data:
            albums.append(
                {
                    "id": item.get("id", ""),
                    "album_name": item.get("albumName", "Unnamed"),
                    "asset_count": item.get("assetCount", 0),
                }
            )
        return albums

    def get_album_assets(self, album_id: str) -> list[Asset]:
        """Get all assets from a specific album.

        Immich no longer returns an `assets` array from GET /albums/{id};
        the album's assets must be fetched via search instead.
        """
        url = urljoin(self.api_base, "search/metadata")
        assets: list[Asset] = []
        page = 1
        while True:
            body = {
                "albumIds": [album_id],
                "page": page,
                "size": 500,
                "order": "asc",
                "withDeleted": True,
            }
            response = self._request_with_retry("POST", url, json=body)
            if response.status_code != 200:
                raise RuntimeError(f"Failed to get album: HTTP {response.status_code}")
            items = response.json().get("assets", {}).get("items", [])
            if not items:
                break
            assets.extend(Asset.from_dict(item) for item in items)
            page += 1
        return assets
