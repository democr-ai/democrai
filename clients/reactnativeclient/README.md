# Democr.ai React Native Client

This is the mobile port of the Democr.ai web client, adapted for a premium mobile experience.

## Setup

1. **Install dependencies**:
   ```bash
   npm install
   ```

2. **Start the development server**:
   ```bash
   npm start
   ```

## Running on Emulator (Recommended)

Since your physical device might have an incompatible version of Expo Go, using an emulator is the recommended alternative:

1. **Start your Android Emulator** (via Android Studio).
2. **Run the Android command**:
   ```bash
   npm run android
   ```
   *Expo will automatically detect the emulator and attempt to install the matching version of Expo Go.*

## Running a Development Build

If Expo Go still shows compatibility issues on the emulator, you can create a **Development Build**, which creates a custom version of the app specifically for your project:

1. **Prebuild and Run**:
   ```bash
   npx expo run:android
   ```
   *This builds a native APK and installs it directly on the emulator/device, bypassing Expo Go entirely.*

## Configuration

The backend URL is configured in `src/hooks/useA2UI.ts`. By default, it points to `ws://localhost:8000/ws`. For an Android emulator, you might need to use `ws://10.0.2.2:8000/ws`.
