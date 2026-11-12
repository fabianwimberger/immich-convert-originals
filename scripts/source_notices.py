import argparse
import json
import re
import subprocess
from collections import defaultdict
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ARCHITECTURES = ("amd64", "arm64")
APORTS = "alpinelinux/aports"
SVT_AV1 = "https://gitlab.com/AOMediaCodec/SVT-AV1/-/raw"
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
COPYLEFT = re.compile(r"(?<![\w-])(?:A?GPL|LGPL)(?:-\d|[+ )]|$)", re.I)


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def image_manifests(image: str) -> dict[str, str]:
    index = json.loads(docker("buildx", "imagetools", "inspect", "--raw", image))
    manifests = {}
    for arch in ARCHITECTURES:
        matches = [
            entry["digest"]
            for entry in index["manifests"]
            if entry["platform"]["os"] == "linux"
            and entry["platform"]["architecture"] == arch
        ]
        if len(matches) != 1 or not DIGEST.fullmatch(matches[0]):
            raise ValueError(f"Expected one linux/{arch} manifest in {image}")
        manifests[arch] = matches[0]
    return manifests


def installed_database(repository: str, digest: str, arch: str) -> str:
    image = f"{repository}@{digest}"
    container = docker("create", "--platform", f"linux/{arch}", image)
    try:
        with TemporaryDirectory() as directory:
            database = Path(directory) / "installed"
            docker("cp", f"{container}:/lib/apk/db/installed", str(database))
            return database.read_text(encoding="utf-8")
    finally:
        docker("rm", "-v", container)


def packages(database: str) -> Iterator[tuple[tuple[str, str, str, str], str]]:
    for record in database.strip().split("\n\n"):
        fields = dict(line.split(":", 1) for line in record.splitlines() if ":" in line)
        license_name = fields["L"]
        if fields.get("o") != "svt-av1" and not COPYLEFT.search(license_name):
            continue
        name, origin, version, commit = (fields[key] for key in ("P", "o", "V", "c"))
        if not re.fullmatch(r"[0-9a-f]{40}", commit) or not re.fullmatch(
            r"[\w.+-]+", origin
        ):
            raise ValueError(f"Invalid Alpine source metadata for {name}")
        yield (origin, version, commit, license_name), name


def packaging_url(source: tuple[str, str]) -> str:
    origin, commit = source
    for section in ("main", "community", "testing"):
        path = f"{commit}/{section}/{origin}"
        request = Request(
            f"https://raw.githubusercontent.com/{APORTS}/{path}/APKBUILD", method="HEAD"
        )
        try:
            with urlopen(request, timeout=20):
                return f"https://github.com/{APORTS}/tree/{path}"
        except HTTPError as error:
            if error.code != 404:
                raise
    raise ValueError(f"No Alpine APKBUILD for {origin} at {commit}")


def svt_notices(version: str) -> list[str]:
    upstream_version, _, _ = version.rpartition("-r")
    if not re.fullmatch(r"[\w.]+", upstream_version):
        raise ValueError(f"Invalid SVT-AV1 version: {version}")
    lines = ["", f"## SVT-AV1 {upstream_version}"]
    for filename in ("LICENSE.md", "PATENTS.md"):
        with urlopen(
            f"{SVT_AV1}/v{upstream_version}/{filename}", timeout=20
        ) as response:
            notice = response.read().decode("utf-8").strip()
        lines.extend(["", f"### {filename}", "", "```text", notice, "```"])
    return lines


def render_notice(
    image: str, tag: str, manifests: dict[str, str], databases: dict[str, str]
) -> str:
    rows = defaultdict(set)
    for arch in ARCHITECTURES:
        installed = list(packages(databases[arch]))
        if not installed:
            raise ValueError(f"No copyleft Alpine packages found for linux/{arch}")
        for package, name in installed:
            rows[package, name].add(arch)

    groups = defaultdict(set)
    for (package, name), arches in rows.items():
        groups[package, tuple(sorted(arches))].add(name)

    sources = sorted({(origin, commit) for (origin, _, commit, _), _ in groups})
    with ThreadPoolExecutor(max_workers=8) as pool:
        urls = dict(zip(sources, pool.map(packaging_url, sources), strict=True))

    lines = [
        f"# Source and notices for Immich Convert Originals {tag}",
        "",
        f"- Image index `{image}`",
        *(f"- `linux/{arch}` manifest `{manifests[arch]}`" for arch in ARCHITECTURES),
        "",
        "The installed Alpine packages below are listed by architecture. Each source directory "
        "contains the Alpine patches and build files. Its `APKBUILD` identifies the upstream "
        "source archives and their checksums.",
        "",
        "| Alpine source | Package version | Installed packages | Package license | Architecture |",
        "| --- | --- | --- | --- | --- |",
    ]
    for ((origin, version, commit, license_name), arches), names in sorted(
        groups.items()
    ):
        license_name = license_name.replace("|", r"\|")
        lines.append(
            f"| [{origin}]({urls[origin, commit]}) | `{version}` | {', '.join(sorted(names))} "
            f"| {license_name} | {', '.join(arches)} |"
        )
    for version in sorted(
        {version for (origin, version, _, _), _ in groups if origin == "svt-av1"}
    ):
        lines.extend(svt_notices(version))
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", help="Container image pinned to its index digest")
    parser.add_argument("tag", help="Release tag")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    repository, separator, digest = args.image.rpartition("@")
    if not separator or not DIGEST.fullmatch(digest):
        parser.error("image must end with @sha256:<64 lowercase hex digits>")
    manifests = image_manifests(args.image)
    databases = {
        arch: installed_database(repository, digest, arch)
        for arch, digest in manifests.items()
    }
    args.output.write_text(
        render_notice(args.image, args.tag, manifests, databases), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
