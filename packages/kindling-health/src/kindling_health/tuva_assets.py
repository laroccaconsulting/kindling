"""Mirror Tuva's versioned data assets (terminology, value sets) to a local directory.

Tuva loads its seeds from the public ``tuva-public-resources`` S3 bucket at ``dbt seed``
time. On DuckDB that requires the ``httpfs`` extension and network access on every run.
Mirroring once lets dbt read local files instead, via Tuva's
``tuva_seed_duckdb_storage_root`` variable. That makes CI, air-gapped networks and the
hosted demo faster and repeatable.

The mirror layout matches what Tuva expects: ``<root>/<bucket>/<asset root>/<version>/...``.
"""

from __future__ import annotations

import gzip
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

BUCKET = "tuva-public-resources"
BASE_URL = f"https://{BUCKET}.s3.amazonaws.com"

# (asset root, version) pairs used by Kindling's dbt project. Keep in sync with dbt/.
DEFAULT_ASSETS: list[tuple[str, str]] = [
    ("tuva-core", "1.0.0"),
    ("data-marts/quality-measures", "1.0.0"),
]

# National provider files (NPPES) are ~720 MB and useless with Synthea's fake NPIs.
# In "slim" mode they are replaced by header-only stubs so the seeds still load.
SLIM_STUBS = (
    "provider_data__provider.csv.gz",
    "provider_data__other_provider_taxonomy.csv.gz",
    "provider_data__provider_taxonomy_unpivot.csv.gz",
)


@dataclass
class AssetObject:
    key: str
    size: int


def list_objects(prefix: str) -> list[AssetObject]:
    objs: list[AssetObject] = []
    token: str | None = None
    pattern = re.compile(r"<Contents>.*?<Key>([^<]+)</Key>.*?<Size>(\d+)</Size>.*?</Contents>", re.S)
    while True:
        q = {"list-type": "2", "prefix": prefix}
        if token:
            q["continuation-token"] = token
        with urllib.request.urlopen(f"{BASE_URL}/?{urllib.parse.urlencode(q)}") as r:
            body = r.read().decode()
        objs += [AssetObject(k, int(s)) for k, s in pattern.findall(body)]
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", body)
        if not m:
            return objs
        token = m.group(1)


def _header_line(key: str) -> bytes:
    """Fetch just enough of a gzipped CSV to recover its header row."""
    req = urllib.request.Request(f"{BASE_URL}/{urllib.parse.quote(key)}", headers={"Range": "bytes=0-65535"})
    with urllib.request.urlopen(req) as r:
        chunk = r.read()
    text = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(chunk)
    return text.split(b"\n", 1)[0] + b"\n"


def mirror(
    root: str | Path,
    assets: Iterable[tuple[str, str]] = DEFAULT_ASSETS,
    *,
    slim: bool = True,
    on_file: Callable[[str, int, bool], None] | None = None,
) -> Path:
    """Download Tuva data assets into ``root``. Existing files of the right size are kept.

    Returns the directory to pass as ``tuva_seed_duckdb_storage_root``.
    """
    root = Path(root)
    for asset_root, version in assets:
        for obj in list_objects(f"{asset_root}/{version}/"):
            if obj.key.endswith("/"):
                continue
            dest = root / BUCKET / obj.key
            name = obj.key.rsplit("/", 1)[-1]
            stub = slim and name in SLIM_STUBS
            if dest.exists() and (stub or dest.stat().st_size == obj.size):
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
                if stub:
                    with gzip.GzipFile(fileobj=tmp, mode="wb", mtime=0) as gz:
                        gz.write(_header_line(obj.key))
                else:
                    url = f"{BASE_URL}/{urllib.parse.quote(obj.key)}"
                    with urllib.request.urlopen(url) as r:
                        shutil.copyfileobj(r, tmp, length=1 << 20)
            os.replace(tmp.name, dest)
            if on_file:
                on_file(obj.key, obj.size, stub)
    return root
