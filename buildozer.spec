[app]

android.extra_manifest_xml = ./src/android/extra_manifest.xml
android.add_src = src/android/java
android.add_resources = src/android/res
title = Laiba Assistant
package.name = laibaassistant
package.domain = com.moeen
source.dir = .
icon.filename = %(source.dir)s/assets/laiba_icon.png
presplash.filename = %(source.dir)s/assets/laiba_icon.png
android.presplash_color = #000000
source.include_exts = py,kv,png,jpg,jpeg,json,txt,md,obj,stl,ply
source.exclude_dirs = .git,venv,.venv,env,__pycache__,.buildozer,bin,exports,.laiba_backups,backup
version = 1.0.4
requirements = python3,kivy,requests,plyer,pyjnius,certifi
android.gradle_dependencies = androidx.core:core:1.13.1
orientation = portrait, landscape
fullscreen = 0

android.api = 35
android.ndk = 28c
android.ndk_path = /root/.buildozer/android/platform/android-ndk-r28c
android.minapi = 24
android.archs = arm64-v8a
android.permissions = REQUEST_INSTALL_PACKAGES,INTERNET,ACCESS_NETWORK_STATE,RECORD_AUDIO,MODIFY_AUDIO_SETTINGS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_MICROPHONE,READ_MEDIA_IMAGES,READ_MEDIA_VIDEO,READ_MEDIA_AUDIO,READ_MEDIA_VISUAL_USER_SELECTED,READ_EXTERNAL_STORAGE,CAMERA,WRITE_EXTERNAL_STORAGE
android.accept_sdk_license = True
android.allow_backup = False

p4a.branch = develop
p4a.source_dir = .buildozer/android/platform/python-for-android-aab

[buildozer]
log_level = 2
warn_on_root = 1
android.jobs = 1
