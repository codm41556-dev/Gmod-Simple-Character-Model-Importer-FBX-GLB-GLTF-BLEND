# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['tools\\mmd_character_importer_gui.py'],
    pathex=['C:\\ProgramData\\miniforge3\\Library\\bin', 'C:\\ProgramData\\miniforge3\\DLLs'],
    binaries=[('C:\\ProgramData\\miniforge3\\Library\\bin\\ffi-8.dll', '.'), ('C:\\ProgramData\\miniforge3\\Library\\bin\\libssl-3-x64.dll', '.'), ('C:\\ProgramData\\miniforge3\\Library\\bin\\libcrypto-3-x64.dll', '.'), ('C:\\ProgramData\\miniforge3\\Library\\bin\\libexpat.dll', '.'), ('C:\\ProgramData\\miniforge3\\Library\\bin\\liblzma.dll', '.'), ('C:\\ProgramData\\miniforge3\\Library\\bin\\libbz2.dll', '.'), ('C:\\ProgramData\\miniforge3\\Library\\bin\\zlib.dll', '.'), ('C:\\ProgramData\\miniforge3\\Library\\bin\\sqlite3.dll', '.'), ('C:\\ProgramData\\miniforge3\\zlib.dll', '.'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\external_tools\\vc_runtime\\vc90\\msvcm90.dll', '.'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\external_tools\\vc_runtime\\vc90\\msvcp90.dll', '.'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\external_tools\\vc_runtime\\vc90\\msvcr90.dll', '.')],
    datas=[('C:\\Users\\1peng\\AppData\\Local\\Temp\\mci_build_info_76763d59984c4f2c8bf7ba76c93eac4e\\build_info.json', '.'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\tools', 'tools'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\plugins_software', 'plugins_software'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\external_tools', 'external_tools'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\blender-4.5.10-windows-x64.zip', '.'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\steps.txt', '.'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\Translation Templates Write.txt', '.'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\README.md', '.'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\reference\\ref_motion', 'reference\\ref_motion'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\reference\\proportion_trick_script-main_new\\README.md', 'reference\\proportion_trick_script-main_new'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\reference\\proportion_trick_script-main_new\\operator_proportion_trick.py', 'reference\\proportion_trick_script-main_new'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\reference\\proportion_trick_script-main_new\\Proportion_Trick\\README.md', 'reference\\proportion_trick_script-main_new\\Proportion_Trick'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\reference\\proportion_trick_script-main_new\\Proportion_Trick\\proportion_trick_4.5.10.blend', 'reference\\proportion_trick_script-main_new\\Proportion_Trick'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\reference\\proportion_trick_script-main_new\\Proportion_Trick\\scripts\\4.5.10', 'reference\\proportion_trick_script-main_new\\Proportion_Trick\\scripts\\4.5.10'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\reference\\li_zhiyan_npc\\a_pack', 'reference\\li_zhiyan_npc\\a_pack'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\reference\\li_zhiyan_npc\\3_Flexes\\Blender_p3.py', 'reference\\li_zhiyan_npc\\3_Flexes'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\reference\\!enhanced_animation_importer_arc\\tools', 'reference\\!enhanced_animation_importer_arc\\tools'), ('C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\reference\\dynamic_model_importer', 'reference\\dynamic_model_importer')],
    hiddenimports=['ctypes', '_ctypes', 'numpy', 'PIL', 'PIL.Image', 'PIL.ImageDraw', 'PIL.ImageFilter', 'PIL.ImageFont', 'PIL.ImageOps', 'requests', 'OpenGL.GL', 'OpenGL.GLU', 'OpenGL.arrays.numpymodule', 'OpenGL.platform.win32', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets', 'PySide6.QtOpenGLWidgets'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['IPython', 'OpenGL_accelerate', 'OpenGL.GLE', 'OpenGL.GLUT', 'OpenGL.Tk', 'PyQt5', 'PyQt6', 'PySide2', 'matplotlib', 'pandas', 'pytest', 'scipy', 'sklearn', 'setuptools', 'tkinter', 'torch', 'unittest', 'cv2', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DCore', 'PySide6.Qt3DExtras', 'PySide6.Qt3DInput', 'PySide6.Qt3DLogic', 'PySide6.Qt3DRender', 'PySide6.QtBluetooth', 'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtLocation', 'PySide6.QtNetworkAuth', 'PySide6.QtPdf', 'PySide6.QtPdfWidgets', 'PySide6.QtPositioning', 'PySide6.QtPrintSupport', 'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickControls2', 'PySide6.QtQuickWidgets', 'PySide6.QtRemoteObjects', 'PySide6.QtScxml', 'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtSql', 'PySide6.QtSvg', 'PySide6.QtTest', 'PySide6.QtTextToSpeech', 'PySide6.QtWebChannel', 'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineQuick', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebSockets', 'PySide6.QtXml'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MMDCharacterImporter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\1peng\\Modding\\ipgsupport\\!Github_SCMI\\Gmod-Simple-Character-Model-Importer\\tools\\assets\\mmd_character_importer_icon.ico'],
)
