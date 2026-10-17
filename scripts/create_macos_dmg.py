#!/usr/bin/env python3
"""Create one native build DMG, retrying only the observed transient busy error.

The bounded retry follows the native runner issue described at
https://github.com/actions/runner-images/issues/7522; it does not assert a cause
on this host, disable system protections, detach volumes, or change filesystems.
The caller must still verify the final image and perform signing/notarization.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import subprocess
import sys
import time


RESOURCE_BUSY = "hdiutil: create failed - Resource busy"
MAX_ATTEMPTS = 3


class ImageError(ValueError):
    pass


def _metadata(directory: int, name: str):
    try:
        return os.stat(name, dir_fd=directory, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _regular_owned(metadata) -> bool:
    return metadata is not None and stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.getuid() and metadata.st_nlink == 1


def _remove_partial(directory: int, name: str) -> None:
    metadata = _metadata(directory, name)
    if metadata is None:
        return
    if not _regular_owned(metadata):
        raise ImageError("Retry refused: partial image is not a regular, owned, single-link file; it was preserved")
    # Open without following links and recheck the inode before unlinking only
    # this leaf inside the already-opened, owner-controlled build directory.
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
    try:
        opened = os.fstat(descriptor)
        current = _metadata(directory, name)
        if not _regular_owned(opened) or not _regular_owned(current) or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino) or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise ImageError("Retry refused: partial image changed; it was preserved")
        os.unlink(name, dir_fd=directory)
    finally:
        os.close(descriptor)


def create_image(source: Path, output: Path, *, runner=None, wait=None) -> int:
    """Return native failure status; injected runners are isolated test fixtures."""
    source, output = Path(source), Path(output)
    if output.suffix != ".dmg" or ".." in output.parts or source.is_symlink():
        raise ImageError("DMG requires a new .dmg leaf and regular staging directory")
    parent = output.parent.resolve(strict=True)
    source = source.resolve(strict=True)
    if not source.is_dir() or source.parent != parent:
        raise ImageError("Staging and image must be siblings inside the owned build directory")
    directory = os.open(parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        metadata = os.fstat(directory)
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o022:
            raise ImageError("Build directory must belong to this user and forbid writes by other users")
        if _metadata(directory, output.name) is not None:
            raise ImageError("DMG output already exists; it was preserved")
        output = parent / output.name
        execute, pause = runner or subprocess.run, wait or time.sleep
        for attempt in range(1, MAX_ATTEMPTS + 1):
            result = execute(["/usr/bin/hdiutil", "create", "-volname", "Mia", "-srcfolder", str(source), "-format", "UDZO", "-o", str(output)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, errors="replace", check=False)
            sys.stdout.write(result.stdout)
            sys.stdout.flush()
            sys.stderr.write(result.stderr)
            sys.stderr.flush()
            if result.returncode == 0:
                if not _regular_owned(_metadata(directory, output.name)):
                    raise ImageError("Native tool did not produce a regular, owned, single-link DMG")
                return 0
            # Do not reinterpret any other error or an ambiguous stderr log.
            if result.returncode != 1 or result.stderr.splitlines() != [RESOURCE_BUSY] or attempt == MAX_ATTEMPTS:
                return result.returncode
            try:
                _remove_partial(directory, output.name)
            except (ImageError, OSError) as error:
                print(str(error), file=sys.stderr)
                return result.returncode
            delay = attempt * 2
            print(f"Mia DMG: transient Resource busy; retry {attempt + 1}/{MAX_ATTEMPTS} after {delay}s.", file=sys.stderr, flush=True)
            pause(delay)
        raise AssertionError("Bounded DMG attempts exhausted unexpectedly")
    finally:
        os.close(directory)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        status = create_image(args.source, args.output)
    except (ImageError, OSError) as error:
        parser.exit(2, str(error) + "\n")
    # Match a direct shell invocation when the native child dies by signal.
    raise SystemExit(status if status >= 0 else 128 - status)


if __name__ == "__main__":
    main()
