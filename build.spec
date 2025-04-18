# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_dynamic_libs
cuda_binaries = collect_dynamic_libs('nvidia')
ffmpeg_binaries = collect_dynamic_libs('ffmpeg_binaries')

a = Analysis(
    ['main.py', './resource/config.py', './resource/model_utils.py', './resource/argos_utils.py', './resource/subtitle_creator.py', './resource/srt_translator.py', './resource/TTSUtils.py'],
    pathex=[],
    binaries=cuda_binaries,
    datas=[('resource','resource'), ('.\\.venv\\Lib\\site-packages\\ffmpeg_binaries','ffmpeg_binaries'), ('.\\.venv\\Lib\\site-packages\\TTS','TTS'), ('.\\.venv\\Lib\\site-packages\\inflect','inflect'), ('.\\.venv\\Lib\\site-packages\\typeguard','typeguard'), ('.\\.venv\\Lib\\site-packages\\gruut','gruut'), ('.\\.venv\\Lib\\site-packages\\gruut_ipa','gruut_ipa'),('.\\.venv\\Lib\\site-packages\\gruut_lang_de','gruut_lang_de'),  ('.\\.venv\\Lib\\site-packages\\gruut_lang_en','gruut_lang_en'),  ('.\\.venv\\Lib\\site-packages\\gruut_lang_es','gruut_lang_es'),  ('.\\.venv\\Lib\\site-packages\\gruut_lang_fr','gruut_lang_fr'),  ('.\\.venv\\Lib\\site-packages\\ffmpeg','ffmpeg') ],
    hiddenimports=['PyQt6', 'winrt.windows.ui.viewmanagement', 'qfluentwidgets', 'numpy', 'faster_whisper', 'TTS', 'inflect', 'typeguard', 'gruut', 'gruut_ipa', 'gruut_lang_de', 'gruut_lang_en', 'gruut_lang_es', 'gruut_lang_fr', 'ffmpeg' ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Alstroemeria',
    version="version.txt",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    manifest=None,
    icon='./resource/assets/icon.ico',
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='main',
)
