from pathlib import Path
import os
from PyInstaller.utils.hooks import collect_submodules, copy_metadata

root = Path(os.environ['WORKBENCH_SOURCE']).resolve()
resources = Path(os.environ['WORKBENCH_RESOURCES']).resolve()
hidden = []
for package in ('desktop', 'agent', 'literature', 'rag', 'ml_inference'):
    hidden.extend(collect_submodules(package))
hidden.extend(['keyring.backends.Windows', 'keyring.backends.chainer', 'openpyxl', 'openai'])
hidden.extend(collect_submodules('win32ctypes'))
datas = [(str(root / 'LICENSE'), '.'), (str(root / 'example_antibodies.csv'), 'examples'),
         (str(resources / 'THIRD_PARTY_NOTICES'), 'THIRD_PARTY_NOTICES'),
         (str(resources / 'VERSION.txt'), '.'),
         (str(root / 'docs/INSTALL_WINDOWS.md'), 'docs'),
         (str(root / 'docs/ML_DEPLOYMENT_CHECKLIST.md'), 'docs')]
datas += [(str(root / 'docs/WINDOWS_THIRD_PARTY_AUDIT.md'), 'docs')]
datas += [(str(root / 'docs/WINDOWS_DELIVERY_ACCEPTANCE.md'), 'docs')]
datas += [(str(image), 'docs/images/windows') for image in (root / 'docs/images/windows').glob('*.png')]
for package in ('keyring', 'openai', 'numpy', 'pandas', 'PySide6'):
    datas += copy_metadata(package)
a = Analysis([str(root / 'packaging/windows/launcher.py')], pathex=[str(root)], datas=datas,
             hiddenimports=hidden,
             excludes=['torch', 'transformers', 'huggingface_hub', 'sklearn', 'scipy', 'gradio',
                       'ml', 'validation', 'pytest', 'IPython', 'matplotlib', 'PyQt5', 'PyQt6',
                       'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtQml',
                       'PySide6.QtQuick', 'PySide6.QtPdf', 'PySide6.QtMultimedia'],
             noarchive=False)
# QtGui's generic plugin hook also picks PDF/virtual-keyboard plugins. They are
# unused by this Widgets product and bring additional module/license scope.
unused_qt = ('qt6pdf', 'qpdf.dll', 'qtvirtualkeyboardplugin', 'qt6virtualkeyboard', 'qt6qml', 'qt6quick')
a.binaries = [entry for entry in a.binaries if not any(token in Path(entry[0]).name.lower() for token in unused_qt)]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='AntibodyResearchWorkbench',
          console=False, debug=False, strip=False, upx=False,
          version=str(resources / 'version_info.txt'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='AntibodyResearchWorkbench')
