"""Interactive wizard for first-time setup."""

import logging
from typing import Any, Protocol

from app.config import Config
from app.immich_api import ImmichClient

logger = logging.getLogger(__name__)


class Prompt(Protocol):
    """Protocol for prompt implementations (questionary or test mocks)."""

    def text(self, message: str, default: str = "") -> str: ...
    def password(self, message: str, default: str = "") -> str: ...
    def confirm(self, message: str, default: bool = False) -> bool: ...
    def select(
        self, message: str, choices: list[tuple[str, str]], default: str | None = None
    ) -> str: ...
    def checkbox(self, message: str, choices: list[tuple[str, str]]) -> list[str]: ...


class QuestionaryPrompt:
    """Real TTY prompts via questionary."""

    def text(self, message: str, default: str = "") -> str:
        import questionary

        return questionary.text(message, default=default).unsafe_ask()

    def password(self, message: str, default: str = "") -> str:
        import questionary

        return questionary.password(message, default=default).unsafe_ask()

    def confirm(self, message: str, default: bool = False) -> bool:
        import questionary

        return questionary.confirm(message, default=default).unsafe_ask()

    def select(
        self, message: str, choices: list[tuple[str, str]], default: str | None = None
    ) -> str:
        import questionary

        qc = [questionary.Choice(title=label, value=value) for value, label in choices]
        return questionary.select(message, choices=qc, default=default).unsafe_ask()

    def checkbox(self, message: str, choices: list[tuple[str, str]]) -> list[str]:
        import questionary

        qc = [questionary.Choice(title=label, value=value) for value, label in choices]
        return questionary.checkbox(message, choices=qc).unsafe_ask()


class FakePrompt:
    """Scripted prompt answers for unit tests."""

    __test__ = False

    def __init__(self, answers: list[Any]) -> None:
        self._answers = list(answers)
        self._calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def _pop(self, expected_method: str, *args: Any, **kwargs: Any) -> Any:
        self._calls.append((expected_method, args, kwargs))
        if not self._answers:
            raise RuntimeError(
                f"FakePrompt exhausted: {expected_method}({args}, {kwargs})"
            )
        return self._answers.pop(0)

    def text(self, message: str, default: str = "") -> str:
        val = self._pop("text", message, default=default)
        return default if val == "" else val

    def password(self, message: str, default: str = "") -> str:
        val = self._pop("password", message, default=default)
        return default if val == "" else val

    def confirm(self, message: str, default: bool = False) -> bool:
        return self._pop("confirm", message, default=default)

    def select(
        self, message: str, choices: list[tuple[str, str]], default: str | None = None
    ) -> str:
        return self._pop("select", message, choices=choices, default=default)

    def checkbox(self, message: str, choices: list[tuple[str, str]]) -> list[str]:
        return self._pop("checkbox", message, choices=choices)

    @property
    def calls(self) -> list[tuple[str, tuple[Any, ...], dict[str, Any]]]:
        return self._calls


def _default_client_factory(api_base: str, api_key: str) -> ImmichClient:
    return ImmichClient(
        api_base=api_base, api_key=api_key, retry_max=1, retry_backoff=0
    )


def run_interactive(
    prompt: Prompt,
    env_defaults: dict[str, str],
    auto_confirm: bool = False,
    client_factory: Any = _default_client_factory,
) -> Config | None:
    """Run the interactive wizard and return a Config (dry_run=True), or None if aborted."""

    # Step 1: Connect
    api_base_default = env_defaults.get("api_base", "")
    api_key_default = env_defaults.get("api_key", "")

    api_base = ""
    api_key = ""
    client: ImmichClient | None = None

    for attempt in range(1, 4):
        api_base = prompt.text("Immich API base URL", default=api_base_default).strip()
        if not api_base:
            logger.error("API base URL is required")
            return None
        api_key = prompt.password("Immich API key", default=api_key_default).strip()
        if not api_key:
            logger.error("API key is required")
            return None

        client = client_factory(api_base, api_key)
        ok, error = client.test_connection()
        if ok:
            info = client.server_info()
            version = ""
            if info:
                version = (
                    f"{info.get('major', '')}.{info.get('minor', '')}.{info.get('patch', '')}"
                ).strip(".")
            logger.info("Connected to Immich server (version %s)", version or "unknown")
            break
        logger.warning("Connection failed: %s", error)
        if attempt < 3:
            prompt.text(
                f"Connection failed ({error}). Press Enter to retry...", default=""
            )
        else:
            logger.error("Could not connect after 3 attempts")
            return None

    assert client is not None

    # Step 2: Asset types
    asset_type_choices: list[tuple[str, str]] = [
        ("IMAGE", "Images (JPEG XL)"),
        ("VIDEO", "Videos (AV1)"),
    ]
    selected_types: list[str] = []
    while not selected_types:
        selected_types = prompt.checkbox(
            "Which asset types to convert?", asset_type_choices
        )
        if not selected_types:
            logger.warning("Please select at least one asset type")

    # Step 3: Scope
    scope_choices: list[tuple[str, str]] = [
        ("library", "Entire library"),
        ("album", "Specific album"),
        ("dates", "Date range"),
    ]
    scope = prompt.select(
        "Which assets should be processed?", scope_choices, default="library"
    )

    filter_album_id: str | None = None
    filter_date_after: str | None = None
    filter_date_before: str | None = None

    if scope == "album":
        albums = client.list_albums()
        if not albums:
            logger.error("No albums found on the server")
            return None
        album_choices = [
            (a["id"], f"{a['album_name']} ({a['asset_count']} assets)") for a in albums
        ]
        filter_album_id = prompt.select("Select album:", album_choices)
    elif scope == "dates":
        preset_choices: list[tuple[str, str]] = [
            ("all", "All time (no filter)"),
            ("last_month", "Last 30 days"),
            ("last_year", "Last 365 days"),
            ("custom", "Custom range"),
        ]
        preset = prompt.select("Date range preset:", preset_choices, default="all")
        if preset == "custom":
            date_after_raw = prompt.text(
                "After date (YYYY-MM-DD, optional):", default=""
            )
            date_before_raw = prompt.text(
                "Before date (YYYY-MM-DD, optional):", default=""
            )
            filter_date_after = _parse_date_input(date_after_raw)
            filter_date_before = _parse_date_input(date_before_raw, end_of_day=True)
        elif preset == "last_month":
            from datetime import datetime, timedelta, timezone

            now = datetime.now(timezone.utc)
            filter_date_after = now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            filter_date_before = None
            # Overwrite with a simpler relative description — actually just set the date
            # Compute 30 days ago
            ago = now - timedelta(days=30)
            filter_date_after = ago.replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            filter_date_after = filter_date_after.replace("+00:00", "Z")
        elif preset == "last_year":
            from datetime import datetime, timedelta, timezone

            now = datetime.now(timezone.utc)
            ago = now - timedelta(days=365)
            filter_date_after = ago.replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            filter_date_after = filter_date_after.replace("+00:00", "Z")
        # "all" leaves both as None

    # Step 4: Limit
    max_assets_raw = prompt.text(
        "Preview on first N assets? (0 = unlimited)", default="25"
    )
    try:
        max_assets = int(max_assets_raw.strip())
        if max_assets < 0:
            max_assets = 25
    except ValueError:
        max_assets = 25

    # Step 5: Encoding
    use_defaults = prompt.confirm("Use recommended encoding settings?", default=True)
    image_distance = 1.0
    video_crf = 36
    if not use_defaults:
        dist_raw = prompt.text(
            "JXL distance (0=lossless, 1=visually lossless):", default="1.0"
        )
        try:
            image_distance = float(dist_raw)
            if image_distance < 0:
                image_distance = 1.0
        except ValueError:
            image_distance = 1.0
        crf_raw = prompt.text("AV1 CRF (0-63, lower=better):", default="36")
        try:
            video_crf = int(crf_raw)
            if video_crf < 0 or video_crf > 63:
                video_crf = 36
        except ValueError:
            video_crf = 36

    # Step 7: Confirm (if not auto-confirmed)
    type_labels = ", ".join(selected_types)
    if not auto_confirm:
        proceed = prompt.confirm(
            f"Proceed with preview on up to {max_assets or 'unlimited'} {type_labels} assets?",
            default=True,
        )
        if not proceed:
            logger.info("Aborted by user")
            return None

    asset_types = tuple(selected_types)

    return Config(
        immich_api_base=api_base,
        immich_api_key=api_key,
        dry_run=True,
        concurrency=1,
        max_assets=max_assets,
        asset_types=asset_types,
        filter_album_id=filter_album_id,
        filter_date_after=filter_date_after,
        filter_date_before=filter_date_before,
        image_distance=image_distance,
        video_crf=video_crf,
    )


def _parse_date_input(value: str, end_of_day: bool = False) -> str | None:
    """Parse YYYY-MM-DD to ISO 8601, or return None if empty."""
    value = value.strip()
    if not value:
        return None
    from datetime import datetime

    # YYYY-MM-DD
    if len(value) == 10 and value.count("-") == 2:
        try:
            year, month, day = value.split("-")
            datetime(int(year), int(month), int(day))
            if end_of_day:
                return f"{value}T23:59:59.999Z"
            return f"{value}T00:00:00.000Z"
        except ValueError as e:
            raise ValueError(f"Invalid date: {value}. Use YYYY-MM-DD.") from e
    # Try ISO
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value
    except ValueError as e:
        raise ValueError(f"Invalid date: {value}. Use YYYY-MM-DD.") from e
