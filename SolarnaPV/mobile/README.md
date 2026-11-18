# Solarna mobile applications

The Android and iOS projects package the Solarna interface locally and connect to
the deployed Python server over HTTPS. Users can enter or change the server address
inside the application.

```powershell
cd mobile
npm install
npm run prepare:web
npx cap add android
npx cap add ios
npm run sync
```

The native platform projects and generated application icons are included in this
repository. Run `cap add` only if a platform directory is intentionally recreated.

For a fixed production server, embed its origin when preparing the web bundle:

```powershell
npm run prepare:web -- --api-url https://solarna.example.com
npx cap sync
```

Production mobile builds require HTTPS. For local emulator development only, pass
`--allow-http` together with a loopback or development server URL.

For a complete Android emulator test against a server listening on port 8766:

```powershell
.\.venv\Scripts\python.exe -m solarna.app --port 8766 --allowed-origin http://localhost
.\mobile\build-android-emulator-e2e.ps1
```

The isolated test package is written to
`outputs/mobile/Solarna-android-emulator-e2e.apk`. The build script restores the
native project to its HTTPS-only production configuration before exiting.

For a physical Android phone on the same private Wi-Fi network:

```powershell
.\scripts\development\start-solarna-lan.ps1
.\mobile\build-android-lan-test.ps1 -ApiUrl http://192.168.1.20:8766
```

Replace the example address with the IPv4 address printed by the LAN server.
Install `outputs/deliverables/Solarna-android-LAN-test.apk` on the phone. This
package permits unencrypted HTTP and is only for a trusted private network. The
LAN web application also exposes the current installer at
`/downloads/solarna-android.apk`.

Android builds require Android Studio, Android SDK and JDK 21. iOS builds and
signing require macOS, Xcode and an Apple developer configuration. The Python
optimizer remains on the deployed server; it is not bundled into the mobile apps.
When the server has `SOLARNA_SUPABASE_URL` and
`SOLARNA_SUPABASE_PUBLISHABLE_KEY` configured, sign in through the dedicated
login page. Supabase manages the expiring session; the application does not
store the password.

For a signed Google Play App Bundle, set these environment variables without
committing their values:

```powershell
$env:SOLARNA_ANDROID_KEYSTORE_PATH = "C:\secure\solarna-upload.jks"
$env:SOLARNA_ANDROID_KEYSTORE_PASSWORD = "..."
$env:SOLARNA_ANDROID_KEY_ALIAS = "solarna-upload"
$env:SOLARNA_ANDROID_KEY_PASSWORD = "..."
.\build-android-release.ps1
```

The script refuses HTTP origins or incomplete signing settings, verifies the
bundle signature and writes `outputs/deliverables/Solarna-android-release.aab`.
The URL-neutral build asks for the server address in the application. Pass
`-ApiUrl https://your-domain.example` only to embed a fixed production server.
Submission values and the Data safety draft are in
`ANDROID-STORE-SUBMISSION.md`.

On macOS, create a signed Xcode archive with:

```bash
export SOLARNA_IOS_TEAM_ID="YOURTEAMID"
./build-ios-release.sh
```

To export an IPA, first export a suitable `ExportOptions.plist` from Xcode, then
set `SOLARNA_IOS_EXPORT_OPTIONS_PLIST` to its path. The script uses automatic
signing and writes timestamped artifacts under `outputs/deliverables/ios/`.
Pass a permanent HTTPS origin as the optional argument to embed it in the app.

## Native tooling dependency maintenance

Capacitor's `xcode` 3.x dependency still requests UUID 7. The scoped
`xcode@3` override selects the patched UUID 11 line for
GHSA-w5hq-g745-h8pq while retaining Xcode's CommonJS `uuid.v4()` interface.
Revisit this override when the upstream Xcode tooling adopts a compatible,
patched dependency.

Run `npm run test:dependencies` after installing the lockfile to check project
UUID generation and invalid output-buffer handling. Both native CI jobs run
this check. The full `npm test` suite also checks generated iOS configuration
and synchronized web assets, so CI runs it after the iOS simulator build.
