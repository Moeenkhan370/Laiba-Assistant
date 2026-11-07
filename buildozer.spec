[app]
title = Laiba Assistant
package.name = laibaassistant
package.domain = com.moeen
source.dir = .
icon.filename = %(source.dir)s/assets/laiba_icon.png
source.include_exts = py,kv,png,jpg,jpeg,json,txt,md,obj,stl,ply
source.exclude_dirs = .git,venv,.venv,env,__pycache__,.buildozer,bin,exports,.laiba_backups,backup
version = 1.0.1
requirements = python3,kivy,requests
orientation = portrait
fullscreen = 0

# Keep the initial target at API 35 only when the selected p4a/Buildozer
# toolchain supports it. Verify the installed toolchain before building.
android.api = 35
android.ndk = 28c
android.ndk_path = /root/.buildozer/android/platform/android-ndk-r28c
android.minapi = 24
android.archs = arm64-v8a
android.permissions = INTERNET,ACCESS_NETWORK_STATE,RECORD_AUDIO,FOREGROUND_SERVICE,FOREGROUND_SERVICE_MICROPHONE,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO,READ_MEDIA_AUDIO,READ_MEDIA_VISUAL_USER_SELECTED,READ_EXTERNAL_STORAGE
android.accept_sdk_license = True
android.allow_backup = False

# Use the stable python-for-android branch; pinning SDK/NDK blindly is avoided.
p4a.branch = develop
p4a.source_dir = .buildozer/android/platform/python-for-android-aab

[buildozer]
log_level = 2
warn_on_root = 1
android.jobs = 1
