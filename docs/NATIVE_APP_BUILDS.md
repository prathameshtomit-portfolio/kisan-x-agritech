# Build Android APK and Windows installer

The mobile and desktop wrappers use the same KISAN-X web interface. They package the interface locally and call a separately hosted FastAPI backend. The Android build generates launcher/splash resources from `assets/logo.png` and uses the provided KISAN-X mark in the native-only animated opening screen. GitHub Actions builds the APK and Windows NSIS setup executable; GitHub Pages cannot provide the API.

## 1. Deploy the backend first

Host the FastAPI app at an HTTPS origin, for example `https://kisanx-api.example.com`. Set a production `DATABASE_URL`, `KISANX_OWNER_PIN`, and a restrictive `CORS_ORIGINS` on the backend host. Include the native origins below and your web domain if you host the web app separately:

```text
https://localhost,http://localhost,http://tauri.localhost,tauri://localhost,https://your-web-domain.example
```

The Windows app uses `http://tauri.localhost`; Capacitor Android uses `https://localhost`. Never place a database password or owner PIN in the mobile/desktop build. This prototype has no farmer accounts or per-farmer access control, so do not expose real farmer records publicly.

## 2. Configure the GitHub build

1. Push this project to the team's GitHub repository.
2. Open **Settings → Secrets and variables → Actions → Variables**.
3. Add repository variable `KISANX_API_BASE` with only the HTTPS origin, such as `https://kisanx-api.example.com`. Do not append `/api/v1`.
4. Open **Actions → Build Android APK and Windows installer → Run workflow**.
5. When the run succeeds, open the workflow run's **Artifacts** section and download `KISAN-X-Android-debug-APK` or `KISAN-X-Windows-installer`. The Android artifact is an installable debug APK for device testing; Play Store distribution requires a signed release build.

The workflow also runs when you push a tag beginning `app-v`, for example `app-v0.3.2`. It stores downloadable artifacts for 14 days; it does not publish to Google Play or create a public GitHub release.

## 3. Build APK on your Windows computer

Install Node.js 22+, Android Studio (with an Android SDK), and use the JDK installed by Android Studio. From the repository root in PowerShell:

```powershell
npm install
$env:KISANX_API_BASE = "https://kisanx-api.example.com"
npm run native:build
npm run android:init
npm run android:assets
npm run android:sync
npm run android:debug
```

The APK is created at `android/app/build/outputs/apk/debug/app-debug.apk`. Copy it to an Android phone and install it for testing. Android may ask you to allow installation from that file source. Capacitor supports Android API 24 and newer.

For a Google Play release, create and protect an Android upload keystore, configure GitHub Actions secrets, and add a signed release build. The current workflow intentionally creates only a debug APK; do not upload it as a Play Store release.

## 4. Build the Windows installer

Install Node.js 22+, Rust stable with the MSVC toolchain, and Microsoft C++ Build Tools (Desktop development with C++). From the repository root:

```powershell
npm install
$env:KISANX_API_BASE = "https://kisanx-api.example.com"
npm run desktop:build
```

The setup executable is written under `src-tauri/target/release/bundle/nsis/`. Windows 10/11 commonly already has WebView2; install the Evergreen WebView2 Runtime if the app reports that it is missing. The generated installer is unsigned, so Windows SmartScreen may show an unknown-publisher message. A code-signing certificate is needed for a trusted publisher identity.

## 5. What the wrappers do and do not change

They package the existing responsive web app in native shells and point it to the configured backend. They do not add offline satellite data, an AI provider, crop-image diagnosis, Android push alerts, or farmer account security. Network-dependent features still need internet access and the hosted backend. Test the APK and installer on real devices before sharing them widely.
