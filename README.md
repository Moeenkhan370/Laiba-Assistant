# Laiba Assistant (Python + Kivy)

This is a repair of the supplied Laiba project, not a replacement application. The desktop Tkinter interface is retained in `desktop_main.py`; `main.py` is now the platform-aware launcher and starts `app_kivy.py` on Android.

## Implemented in this repair

- Kivy Android entry point and Buildozer configuration (`buildozer.spec`).
- Gemini REST text/image request path using `requests` (no desktop-only Gemini SDK).
- API key trimming and local config persistence. Keep `laiba_config.json` private; it is excluded from ZIP export.
- Conservative command routing for update checks, ZIP export, 3D status, and project file listing.
- Project-root constrained file operations, Python syntax validation, backups, atomic writes, and confirmation gates.
- OBJ, STL (binary and ASCII), and ASCII PLY mesh parsing; cube/pyramid geometry and rotation.
- Real configured-manifest update checking and SHA-256 file verification helper. APK installation is intentionally not automatic.
- ZIP export excludes build caches, backups, virtual environments, archives, and local credentials.

## Not implemented / not claimed

- Continuous Urdu speech recognition, female TTS, wake word, and background microphone service. These need a tested Android native speech/audio bridge and runtime permission flow.
- Camera preview/capture and Android image picker. The Gemini request engine can analyze an image path supplied by a future Android picker integration.
- GLTF/GLB parsing, binary PLY, cryptographic update-signature verification, APK installation UI, rollback of installed APKs, and unrestricted Android system control.
- The update manifest URL is blank by default. Configure a real HTTPS JSON manifest before using update checks.

## Gemini configuration

Set `GEMINI_API_KEY` in the process environment before launch, or call `ChatbotEngine.set_api_key()` from a settings UI. The app stores the key in its private app configuration file. Do not include that file in shared archives. `GEMINI_MODEL` defaults to `gemini-2.0-flash`; verify model availability for your Google AI account.

## Desktop

Install host requirements and run:

```bash
python -m pip install -r requirements.txt
python main.py
```

On desktop, `main.py` launches the retained Tkinter application from `desktop_main.py`.

## Android / Termux + Ubuntu + Buildozer

Buildozer is generally more reliable inside a supported Linux/Ubuntu ARM64 or x86_64 build host than directly inside Android Termux. The phone's ARM64 CPU does not make every Android-hosted build tool compatible; SDK tools such as `aidl` must match the host execution architecture. Do not copy x86-64 SDK binaries into an ARM64 Ubuntu environment.

Inside a supported Ubuntu environment, install the system prerequisites recommended by the selected Buildozer release, then:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install buildozer cython
buildozer android debug
```

The first build downloads Android SDK/NDK components and can require substantial storage, RAM, and network data. Check the selected Buildozer/python-for-Android release supports `android.api = 35`; if not, use a supported target API and document the change. APK output is normally under `bin/`.

## Tests

Run basic host checks:

```bash
python -m compileall -q .
python - <<'PY'
from engines.threed_engine import ThreeDEngine
from engines.file_modifier import FileModifierEngine
from engines.self_update import SelfUpdateEngine
from engines.chatbot_engine import ChatbotEngine
m = ThreeDEngine()
assert len(m.mesh_vertices) == 8 and len(m.mesh_faces) == 6
m.load_pyramid(); assert len(m.mesh_vertices) == 5
assert FileModifierEngine('.').list_dir('.')
assert SelfUpdateEngine(update_url='').check_for_updates()['status'] == 'not_configured'
assert ChatbotEngine().process_message('check update').startswith('Update check:')
print('Core smoke tests passed')
PY
```

A successful host smoke test does not prove Android packaging, microphone, camera, or live speech behavior. Those require a real Android build and device tests.
