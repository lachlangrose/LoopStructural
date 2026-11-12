"""MMG CLI runner: keep every input, solution, mapping, output and transcript."""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

from .mesh import read_mesh, write_mesh


def find_mmg(explicit=None):
    if explicit:
        return str(Path(explicit).resolve())
    env = os.environ.get("MMG3D")
    if env:
        return str(Path(env).resolve())
    local = Path(__file__).resolve().parents[2] / ".mmg-runtime/bin/mmg3d_O3.exe"
    if local.exists():
        return str(local)
    for name in ("mmg3d_O3", "mmg3d"):
        if shutil.which(name):
            return shutil.which(name)
    raise FileNotFoundError("Install conda-forge::mmgsuite or set MMG3D to its executable")


def run_levelset(
    mesh, values, directory, mapping=None, executable=None, frozen=True, extra=(), timeout=120
):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    values = np.asarray(values)
    if values.shape != (len(mesh.points),) or not np.all(np.isfinite(values)):
        raise ValueError("MMG requires one finite scalar per global vertex")
    write_mesh(directory / "input.mesh", mesh)
    with (directory / "input.sol").open("w", newline="\n") as f:
        f.write(f"MeshVersionFormatted 2\nDimension 3\nSolAtVertices\n{len(values)}\n1 1\n")
        np.savetxt(f, values, fmt="%.17g")
        f.write("End\n")
    command = [
        find_mmg(executable),
        "-in",
        "input.mesh",
        "-sol",
        "input.sol",
        "-out",
        "output.mesh",
        "-ls",
        "0",
        "-hmin",
        "0.015",
        "-hmax",
        "0.35",
        "-hausd",
        "1e-8",
        "-v",
        "5",
    ]
    if mapping is not None:
        lines = ["LSReferences", str(len(mapping))]
        for ref, pair in sorted(mapping.items()):
            lines.append(f"{ref} nosplit" if pair is None else f"{ref} {pair[0]} {pair[1]}")
        (directory / "input.mmg3d").write_text("\n".join(lines) + "\n")
        command += ["-f", "input.mmg3d"]
    if frozen:
        command += ["-noinsert", "-nomove", "-noswap"]
    command += list(extra)
    start = time.monotonic()
    result = subprocess.run(
        command,
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=timeout,
        errors="replace",
        check=False,
    )
    (directory / "mmg.log").write_text(result.stdout + result.stderr)
    record = {
        "command": command,
        "returncode": result.returncode,
        "elapsed_seconds": time.monotonic() - start,
        "input_vertices": len(mesh.points),
        "input_tets": len(mesh.tets),
        "warning_lines": [
            line
            for line in (result.stdout + result.stderr).splitlines()
            if "Warning" in line or "Error" in line
        ],
    }
    (directory / "invocation.json").write_text(json.dumps(record, indent=2))
    # MMG's low-failure output must not be treated as a successful experiment.
    if result.returncode != 0 or not (directory / "output.mesh").exists():
        raise RuntimeError(f"MMG failed ({result.returncode}); inspect {directory / 'mmg.log'}")
    output = read_mesh(directory / "output.mesh")
    return output, record


def retag_interfaces(mesh, reference):
    """CLI uses reserved interface reference 10; protect it before the next load."""
    mesh.tri_refs[mesh.tri_refs == 10] = reference
    return mesh


def run_remesh(
    mesh,
    directory,
    executable=None,
    *,
    size=0.18,
    hausd=1e-8,
    optimize_only=False,
    extra=(),
    timeout=180,
):
    """Ordinary MMG adaptation: enable insertion, collapse, swaps and movement.

    No level-set field is supplied. Existing material interfaces constrain the
    remesher, but geometry and adjacency must still be independently verified.
    """
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "output.mesh").exists():
        raise FileExistsError(f"Choose a fresh remeshing directory: {directory}")
    write_mesh(directory / "input.mesh", mesh)
    command = [
        find_mmg(executable),
        "-in",
        "input.mesh",
        "-out",
        "output.mesh",
        "-hausd",
        str(hausd),
        "-hgrad",
        "1.3",
        "-v",
        "5",
    ]
    command += ["-optim"] if optimize_only else ["-hsiz", str(size)]
    command += list(extra)
    record = {
        "command": command,
        "mode": "adaptation",
        "level_set": False,
        "input_vertices": len(mesh.points),
        "input_tets": len(mesh.tets),
    }
    (directory / "invocation.json").write_text(json.dumps(record, indent=2))
    start = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=timeout,
            errors="replace",
            check=False,
        )
    except subprocess.TimeoutExpired as error:

        def decoded(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else value or ""

        (directory / "mmg.log").write_text(decoded(error.stdout) + decoded(error.stderr))
        record.update({"timed_out": True, "elapsed_seconds": time.monotonic() - start})
        (directory / "invocation.json").write_text(json.dumps(record, indent=2))
        raise
    transcript = result.stdout + result.stderr
    (directory / "mmg.log").write_text(transcript)
    record.update(
        {
            "returncode": result.returncode,
            "elapsed_seconds": time.monotonic() - start,
            "warning_lines": [
                line for line in transcript.splitlines() if "Warning" in line or "Error" in line
            ],
        }
    )
    (directory / "invocation.json").write_text(json.dumps(record, indent=2))
    if result.returncode != 0 or not (directory / "output.mesh").exists():
        raise RuntimeError(
            f"MMG remeshing failed ({result.returncode}); inspect {directory / 'mmg.log'}"
        )
    return read_mesh(directory / "output.mesh"), record
