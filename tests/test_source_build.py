import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _source_build import should_build_librtlsdr_from_source


def test_builds_when_nothing_staged(tmp_path):
    lib_dir = tmp_path / 'lib'
    custom_dir = lib_dir / 'custom_build'
    lib_dir.mkdir()
    custom_dir.mkdir()
    assert should_build_librtlsdr_from_source(lib_dir, custom_dir, env={}) is True


def test_skips_when_platform_env_set(tmp_path):
    lib_dir = tmp_path / 'lib'
    custom_dir = lib_dir / 'custom_build'
    lib_dir.mkdir()
    custom_dir.mkdir()
    env = {'PYRTLSDRLIB_PLATFORM': 'linux'}
    assert should_build_librtlsdr_from_source(lib_dir, custom_dir, env=env) is False


def test_skips_when_opted_out(tmp_path):
    lib_dir = tmp_path / 'lib'
    custom_dir = lib_dir / 'custom_build'
    lib_dir.mkdir()
    custom_dir.mkdir()
    env = {'PYRTLSDRLIB_SKIP_SOURCE_BUILD': '1'}
    assert should_build_librtlsdr_from_source(lib_dir, custom_dir, env=env) is False


def test_skips_when_lib_already_bundled(tmp_path):
    lib_dir = tmp_path / 'lib'
    custom_dir = lib_dir / 'custom_build'
    lib_dir.mkdir()
    custom_dir.mkdir()
    (lib_dir / 'librtlsdr.so.0').write_bytes(b'')
    assert should_build_librtlsdr_from_source(lib_dir, custom_dir, env={}) is False


def test_skips_when_custom_build_already_staged(tmp_path):
    lib_dir = tmp_path / 'lib'
    custom_dir = lib_dir / 'custom_build'
    lib_dir.mkdir()
    custom_dir.mkdir()
    (custom_dir / 'librtlsdr.so.0').write_bytes(b'')
    assert should_build_librtlsdr_from_source(lib_dir, custom_dir, env={}) is False
