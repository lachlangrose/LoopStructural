"""Fetch the non-VTK Windows MMG package into this experiment only.

Uses conda's extractor when available; no change to the user's environments.
The downloaded archive is checked against conda-forge's SHA256 metadata.
"""

import hashlib
import json
import sys
import urllib.request
from pathlib import Path


def main():
    root = Path(__file__).resolve().parents[1] / ".mmg-runtime"
    root.mkdir(exist_ok=True)
    metadata = json.load(
        urllib.request.urlopen("https://api.anaconda.org/package/conda-forge/mmgsuite", timeout=60)
    )
    candidates = [
        f for f in metadata["files"] if f["basename"] == "win-64/mmgsuite-5.8.0-h83b8f9d_15.conda"
    ]
    package = candidates[-1]
    url = "https:" + package["download_url"]
    data = urllib.request.urlopen(url, timeout=60).read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != package["sha256"]:
        raise RuntimeError("MMG package SHA256 mismatch")
    archive = root / Path(package["basename"]).name
    archive.write_bytes(data)
    from conda_package_handling.api import extract

    extract(str(archive), dest_dir=str(root))
    provenance = {"url": url, "sha256": digest, "package": package["basename"]}
    sources = root / "source"
    sources.mkdir(exist_ok=True)
    for name in (
        "src/mmg3d/mmg3d2.c",
        "src/mmg3d/inout_3d.c",
        "src/mmg3d/mmg3d.c",
        "src/mmg3d/libmmg3d.h",
        "src/common/mmg2.c",
        "src/common/inout.c",
    ):
        source_url = "https://raw.githubusercontent.com/MmgTools/mmg/v5.8.0/" + name
        (sources / Path(name).name).write_bytes(
            urllib.request.urlopen(source_url, timeout=60).read()
        )
    (root / "provenance.json").write_text(json.dumps(provenance, indent=2))
    print(json.dumps(provenance, indent=2))
    print("MMG:", list(root.rglob("mmg3d*.exe")))


if __name__ == "__main__":
    if sys.platform != "win32":
        raise SystemExit("On other platforms use conda install -c conda-forge mmgsuite=5.8.0")
    main()
