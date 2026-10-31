import importlib.util
import os
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('static_publisher',
    Path(__file__).resolve().parents[1] / 'deploy/publish_static.py')
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


def test_private_staging_under_restrictive_umask_publishes_service_readable_assets(tmp_path):
    source, target = tmp_path/'staging', tmp_path/'public'
    source.mkdir(mode=0o700)
    (source/'assets').mkdir(mode=0o700)
    (source/'index.html').write_text('<script src="/assets/app.js"></script>')
    (source/'assets/app.js').write_text('console.log("published")')
    (source/'assets/app.js').chmod(0o600)
    target.mkdir(mode=0o700)
    (target/'old-hash.js').write_text('old')
    previous = os.umask(0o077)
    try:
        publisher.publish(source,target)
    finally:
        os.umask(previous)
    assert (target/'index.html').read_text()==(source/'index.html').read_text()
    assert (target/'old-hash.js').exists()
    for path in [target,*target.rglob('*')]:
        assert path.stat().st_mode & 0o777 == (0o755 if path.is_dir() else 0o644)
    assert source.stat().st_mode & 0o777 == 0o700


def test_frontend_symlink_is_rejected(tmp_path):
    source=tmp_path/'staging';source.mkdir()
    (source/'index.html').write_text('public')
    (source/'private-link').symlink_to('/etc/passwd')
    with pytest.raises(ValueError,match='symlinks'):
        publisher.publish(source,tmp_path/'public')
