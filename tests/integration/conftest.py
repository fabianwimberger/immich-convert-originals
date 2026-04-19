"""Session-scoped fixtures for integration tests."""

import contextlib
import os
import socket
import subprocess
import time
from typing import Any

import pytest
import requests

from app.immich_api import ImmichClient


def _get_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _docker_available() -> bool:
    try:
        subprocess.run(
            ["docker", "info"],
            capture_output=True,
            check=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


@pytest.fixture(scope="session")
def immich_stack() -> str:
    if not _docker_available():
        pytest.skip("Docker not available")

    compose_file = os.path.join(os.path.dirname(__file__), "docker-compose.test.yml")
    port = _get_free_port()
    project = "immich-convert-test"
    env = {**os.environ, "IMMICH_TEST_PORT": str(port), "COMPOSE_PROJECT_NAME": project}

    # Tear down any stale resources first
    subprocess.run(
        ["docker", "compose", "-f", compose_file, "-p", project, "down", "-v"],
        capture_output=True,
        env=env,
    )
    with contextlib.suppress(subprocess.CalledProcessError):
        subprocess.run(
            ["docker", "network", "rm", "immich-test-net"],
            capture_output=True,
            check=True,
        )

    # Start stack
    subprocess.run(
        ["docker", "compose", "-f", compose_file, "-p", project, "up", "-d"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    api_base = f"http://127.0.0.1:{port}/api/"

    # Poll until healthy
    deadline = time.time() + 120
    last_error = ""
    while time.time() < deadline:
        try:
            resp = requests.get(f"{api_base}server/ping", timeout=5)
            if resp.status_code == 200:
                break
        except Exception as e:
            last_error = str(e)
        time.sleep(5)
    else:
        # Collect logs for debugging
        logs = subprocess.run(
            ["docker", "logs", "immich-test-server"],
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["docker", "compose", "-f", compose_file, "-p", project, "down", "-v"],
            capture_output=True,
            env=env,
        )
        pytest.fail(
            f"Immich server did not become healthy within 120s.\n"
            f"Last error: {last_error}\n"
            f"Server logs:\n{logs.stdout}\n{logs.stderr}"
        )

    yield api_base

    # Teardown
    subprocess.run(
        ["docker", "compose", "-f", compose_file, "-p", project, "down", "-v"],
        capture_output=True,
        env=env,
    )
    with contextlib.suppress(subprocess.CalledProcessError):
        subprocess.run(
            ["docker", "network", "rm", "immich-test-net"],
            capture_output=True,
            check=True,
        )


@pytest.fixture(scope="session")
def admin_client(immich_stack: str) -> ImmichClient:
    api_base = immich_stack
    admin_email = "admin@example.com"
    admin_password = "admin-password-123"

    # Sign up admin
    signup_resp = requests.post(
        f"{api_base}auth/admin-sign-up",
        json={
            "email": admin_email,
            "password": admin_password,
            "name": "Admin",
        },
        timeout=10,
    )
    if signup_resp.status_code not in (200, 201):
        # Admin may already exist; try logging in
        pass

    # Login
    login_resp = requests.post(
        f"{api_base}auth/login",
        json={"email": admin_email, "password": admin_password},
        timeout=10,
    )
    login_resp.raise_for_status()
    access_token = login_resp.json()["accessToken"]

    # Create API key
    key_resp = requests.post(
        f"{api_base}api-keys",
        json={"name": "integration-tests", "permissions": ["all"]},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    key_resp.raise_for_status()
    api_key = key_resp.json()["secret"]

    return ImmichClient(api_base=api_base, api_key=api_key)


@pytest.fixture(scope="session")
def seeded_library(admin_client: ImmichClient, tmp_path_factory: Any) -> dict[str, Any]:
    from .seeder import seed_library

    return seed_library(admin_client, tmp_path_factory)
