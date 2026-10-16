"""Build the complete Windows portable directory and versioned release ZIP."""
import hashlib
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != 'win32' or platform.architecture()[0] != '64bit':
        raise SystemExit('Build on 64-bit Windows with 64-bit Python.')
    version = (ROOT / 'VERSION').read_text().strip()
    from PySide6.QtCore import QSize
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    icon = ROOT / 'assets' / 'qingxia.ico'
    if not QIcon(str(ROOT / 'assets' / 'qingxia.svg')).pixmap(QSize(256, 256)).save(str(icon), 'ICO'):
        raise SystemExit('Unable to generate application icon.')
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
        '--name', 'QingXia', '--icon', str(icon), '--collect-all', 'qfluentwidgets',
        '--add-data', 'assets;assets', '--add-data', 'VERSION;.',
        '--add-data', 'LICENSE;.', '--add-data', 'THIRD_PARTY_NOTICES.md;.',
        '--add-data', 'third_party_licenses;third_party_licenses',
        '--exclude-module', 'PySide6.QtWebEngineCore',
        '--exclude-module', 'PySide6.QtWebEngineWidgets',
        'main.py'], cwd=ROOT, check=True)
    bundle = ROOT / 'dist' / 'QingXia'
    for name in ('LICENSE', 'README.md', 'CHANGELOG.md', 'THIRD_PARTY_NOTICES.md', 'VERSION'):
        shutil.copy2(ROOT / name, bundle / name)
    shutil.copytree(ROOT / 'third_party_licenses', bundle / 'third_party_licenses', dirs_exist_ok=True)
    shutil.copytree(ROOT / 'docs', bundle / 'docs', dirs_exist_ok=True)
    archive = Path(shutil.make_archive(str(ROOT / 'dist' / f'QingXia-{version}-windows-x64'),
                                       'zip', ROOT / 'dist', 'QingXia'))
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    (ROOT / 'dist' / 'SHA256SUMS.txt').write_text(f'{digest}  {archive.name}\n', encoding='ascii')
    print(archive)


if __name__ == '__main__':
    main()
