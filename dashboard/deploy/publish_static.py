#!/usr/bin/env python3
"""Publish public frontend files without inheriting private staging permissions."""
import argparse
import os
import tempfile
from pathlib import Path


def publish(source, target):
    source, target = Path(source).resolve(), Path(target).resolve()
    if source == target or source in target.parents or target in source.parents:
        raise ValueError('Source and target must be separate directories')
    files = sorted(source.rglob('*'), key=lambda p: p.name == 'index.html')
    if not (source / 'index.html').is_file():
        raise ValueError('Frontend index.html is missing')
    if any(p.is_symlink() for p in files):
        raise ValueError('Frontend symlinks are not allowed')
    if target.exists() and any(p.is_symlink() for p in target.rglob('*')):
        raise ValueError('Published frontend symlinks are not allowed')
    target.mkdir(parents=True, exist_ok=True)
    target.chmod(0o755)
    for path in files:
        relative = path.relative_to(source)
        destination = target / relative
        if path.is_dir():
            destination.mkdir(parents=True, exist_ok=True)
            destination.chmod(0o755)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        parent = destination.parent
        while parent != target:
            parent.chmod(0o755)
            parent = parent.parent
        fd, temporary = tempfile.mkstemp(prefix='.publish-', dir=destination.parent)
        try:
            with os.fdopen(fd, 'wb') as stream:
                os.fchmod(stream.fileno(), 0o644)
                stream.write(path.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            Path(temporary).unlink(missing_ok=True)
    # Keep previous hashed assets readable for browsers using the previous index.
    for path in target.rglob('*'):
        path.chmod(0o755 if path.is_dir() else 0o644)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('target')
    args = parser.parse_args()
    publish(args.source, args.target)
