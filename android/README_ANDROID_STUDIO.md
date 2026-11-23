# Yuktix Android Studio source (v1.4.3)

This folder contains the existing Android WebView wrapper, local API adapter, packaged web interface, Android resources, and Gradle project files. It is the v1.4.3 source previously supplied for development; it is **not** the exact build source for the separately released v1.4.1 APK.

The large offline database `app/src/main/assets/offline.db.gz` is excluded from the Git source tree. To open a complete offline project, download the [original Android Studio ZIP](https://github.com/AdityaHiremath88/Crowd-intelligent-public-transport-journey-planning-platform/releases/download/v1.4.3-source/Yuktix-Delhi-Transit-v1.4.3-Android-Studio.zip) from GitHub Releases. That ZIP includes the historical data snapshot. Confirm the data provider's redistribution terms before reusing the snapshot.

Extract the ZIP, then use **File > Open** in Android Studio and select the extracted folder containing `settings.gradle`. Let Gradle sync, install Android SDK Platform 35 if prompted, and run the `app` configuration on an emulator or Android phone. The project declares Android Gradle Plugin 9.4.1 and needs a compatible Gradle installation. It does not include the Android SDK, Gradle binaries, or a signing key.

A debug build is signed by Android Studio's own debug key. Installing it over a differently signed APK requires removing the old installation, which deletes that app's local data.
