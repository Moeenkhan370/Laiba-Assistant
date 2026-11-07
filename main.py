"""Platform-aware launcher. Buildozer starts this file on Android."""
import os
import sys

IS_ANDROID = sys.platform == "android" or "ANDROID_ARGUMENT" in os.environ

if IS_ANDROID:
    from app_kivy import LaibaKivyApp
    LaibaKivyApp().run()
else:
    from desktop_main import main
    main()
