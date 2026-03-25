from setuptools import setup

APP = ["main.py"]

OPTIONS = {
    "argv_emulation": False,
    "packages": ["rumps"],
    "plist": {
        "CFBundleName": "AutoResponder",
        "CFBundleDisplayName": "AutoResponder",
        "CFBundleIdentifier": "com.autoresponder.app",
        "CFBundleVersion": "1.0.0",
        "LSUIElement": True,  # menu bar only — no dock icon
        "NSAppleEventsUsageDescription": "AutoResponder uses AppleScript to send iMessages on your behalf.",
        "NSPrivacyAccessedAPITypes": [],
    },
}

setup(
    name="AutoResponder",
    app=APP,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
