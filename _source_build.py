"""Fallback build of librtlsdr from source.

Used by setup.py when a build is *not* one of the maintainer's per-platform
release builds (those set PYRTLSDRLIB_PLATFORM and stage their own binaries
via tools/get_releases.py). That's the case whenever pip has to build
pyrtlsdrlib from the sdist because no pre-built wheel matches the installer's
platform: this module downloads the latest librtlsdr release source from
GitHub and compiles it with cmake, so the install still ends up with a
working library instead of an empty package.

Kept dependency-free (stdlib only) since it runs during an end user's
`pip install`, outside of build-system.requires isolation guarantees for
this project's own dev/build dependency group.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

LIBRTLSDR_REPO = 'librtlsdr/librtlsdr'
GITHUB_LATEST_RELEASE_URL = f'https://api.github.com/repos/{LIBRTLSDR_REPO}/releases/latest'

PROJECT_ROOT = Path(__file__).resolve().parent
LIB_DIR = PROJECT_ROOT / 'src' / 'pyrtlsdrlib' / 'lib'
CUSTOM_BUILD_DIR = LIB_DIR / 'custom_build'


def _is_musl_libc() -> bool:
    return sys.platform == 'linux' and platform.libc_ver()[0] == ''


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'pyrtlsdrlib-setup.py',
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def fetch_latest_source_tarball(dest_dir: Path) -> Path:
    release = json.loads(_http_get(GITHUB_LATEST_RELEASE_URL))
    archive_path = dest_dir / 'librtlsdr-source.tar.gz'
    archive_path.write_bytes(_http_get(release['tarball_url']))
    return archive_path


def extract_single_dir(archive_path: Path, extract_to: Path) -> Path:
    with tarfile.open(archive_path) as tf:
        try:
            tf.extractall(extract_to, filter='data')
        except TypeError:
            # `filter` isn't available on older 3.10/3.11 patch releases.
            tf.extractall(extract_to)
    dirs = [p for p in extract_to.iterdir() if p.is_dir()]
    if len(dirs) != 1:
        raise RuntimeError(f'Expected a single extracted source directory, found: {dirs}')
    return dirs[0]


def cmake_build(source_dir: Path) -> Path:
    if shutil.which('cmake') is None:
        raise RuntimeError('cmake was not found on PATH')
    build_dir = source_dir / 'build'
    build_dir.mkdir()
    configure_cmd = [
        'cmake', '-S', str(source_dir), '-B', str(build_dir),
        '-DCMAKE_BUILD_TYPE=Release',
    ]
    if _is_musl_libc():
        # musl libc has no timelocal(), a glibc/BSD-only synonym for mktime()
        # used by convenience.c. Redirect it via the preprocessor instead of
        # patching the fetched source. Also strip _FORTIFY_SOURCE: musl
        # doesn't implement glibc's fortify "_chk" functions (__printf_chk
        # etc), and some toolchains enable it by default regardless of
        # target libc, which only fails at dlopen time under musl.
        configure_cmd.append('-DCMAKE_C_FLAGS=-Dtimelocal=mktime -U_FORTIFY_SOURCE')
    subprocess.run(configure_cmd, check=True)
    subprocess.run(
        ['cmake', '--build', str(build_dir), '--config', 'Release', '--parallel'],
        check=True,
    )
    return build_dir


def copy_built_libs(build_dir: Path, dest_dir: Path) -> None:
    src_dir = (build_dir / 'src').resolve()
    found = list(src_dir.glob('librtlsdr*'))
    if not found:
        raise RuntimeError(f'No librtlsdr build output found in {src_dir}')
    dest_dir.mkdir(parents=True, exist_ok=True)
    symlinks = [p for p in found if p.is_symlink()]
    files = [p for p in found if not p.is_symlink()]
    for p in files:
        shutil.copy2(p, dest_dir / p.name)
    for p in symlinks:
        target_name = p.resolve().relative_to(src_dir).name
        link_path = dest_dir / p.name
        if link_path.exists() or link_path.is_symlink():
            link_path.unlink()
        link_path.symlink_to(target_name)


def build_librtlsdr_from_source(dest_dir: Path) -> None:
    with tempfile.TemporaryDirectory(prefix='pyrtlsdrlib-src-') as tmp:
        tmp_path = Path(tmp)
        archive = fetch_latest_source_tarball(tmp_path)
        source_dir = extract_single_dir(archive, tmp_path)
        build_dir = cmake_build(source_dir)
        copy_built_libs(build_dir, dest_dir)


def _has_bundled_library(directory: Path) -> bool:
    return directory.is_dir() and any(directory.glob('librtlsdr*'))


def should_build_librtlsdr_from_source(
    lib_dir: Path = LIB_DIR,
    custom_build_dir: Path = CUSTOM_BUILD_DIR,
    env: dict = os.environ,
) -> bool:
    """Whether this build should compile librtlsdr itself.

    This is the sdist->wheel fallback path: it only applies to a plain,
    unplatformed build (no PYRTLSDRLIB_PLATFORM override, which is how the
    maintainer's per-platform release wheels are built) that doesn't already
    have a bundled or custom-built library staged.
    """
    if env.get('PYRTLSDRLIB_SKIP_SOURCE_BUILD', '').lower() in ('1', 'true'):
        return False
    if 'PYRTLSDRLIB_PLATFORM' in env:
        return False
    if _has_bundled_library(lib_dir):
        return False
    if _has_bundled_library(custom_build_dir):
        return False
    return True


def maybe_build_librtlsdr_from_source() -> None:
    if not should_build_librtlsdr_from_source():
        return
    print('pyrtlsdrlib: no pre-built wheel for this platform; building librtlsdr from source...')
    try:
        build_librtlsdr_from_source(CUSTOM_BUILD_DIR)
    except Exception as exc:
        raise SystemExit(
            f'pyrtlsdrlib: failed to build librtlsdr from source ({exc.__class__.__name__}: {exc}).\n'
            'Building from source requires a C compiler, cmake, and libusb development '
            'headers (e.g. "libusb-1.0-0-dev" on Debian/Ubuntu, "libusb" on Homebrew).\n'
            'Set PYRTLSDRLIB_SKIP_SOURCE_BUILD=1 to install without a bundled library.'
        ) from exc
    print('pyrtlsdrlib: librtlsdr built from source successfully.')
