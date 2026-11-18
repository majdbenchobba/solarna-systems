# Solarna PV Google Play submission

## Application

- App name: `Solarna PV`
- Package: `tn.solarna.optimizer`
- Version: `0.5.0`
- Version code: `10`
- Minimum Android: API 24
- Target Android: API 36
- Privacy policy: `https://pv.solarnasystems.com/privacy.html`
- Support: `https://solarnasystems.com/`
- Contact: `contact@solarnasystems.com`

## Release bundle

Set the four `SOLARNA_ANDROID_*` signing variables described in `README.md`,
then run:

```powershell
.\build-android-release.ps1
```

This creates the URL-neutral signed bundle at
`outputs/deliverables/Solarna-android-release.aab`. Pass
`-ApiUrl https://pv.solarnasystems.com` only after that permanent server is
available.

Google Play requires an Android App Bundle for a new application. Target API 36
meets the requirement in effect from 31 August 2026.

## Data safety draft

Solarna does not use advertising, user accounts or cross-app tracking.

Declare these as collected for **App functionality**, not used for advertising
or tracking:

- Precise location: optional coordinates selected by the user can be stored in
  completed reports.
- Other user-generated content: project names, PV-system settings and analysis
  options can be stored in completed reports.

Production traffic is encrypted in transit over HTTPS. Users can request access,
correction or deletion at `contact@solarnasystems.com`.

Coordinates are transmitted to the European Commission Joint Research Centre
PVGIS service when weather or benchmark data is requested. Review Google Play's
current definition of data sharing when completing the final form.

## Permissions

- Internet access is required for the Solarna server and PVGIS.
- Foreground coarse and precise location are optional.
- Location is requested only after the user selects **Use my location**.
- The application does not request background location.

If a future release targets Android 17/API 37 or later, migrate the one-time
precise-location action to the Android Location Button requirement before
submission.

## Technical checks

- The release APK and AAB contain no native `.so` libraries, so no native
  16 KB page-alignment work is required for this version.
- Run the Google Play pre-launch report before production rollout.
- Complete Data safety, content rating, target audience and app-access sections.
- Enable Play App Signing and retain the upload keystore securely.

Official references:

- https://developer.android.com/google/play/requirements/target-sdk
- https://developer.android.com/guide/practices/page-sizes
- https://support.google.com/googleplay/android-developer/answer/9844279
- https://support.google.com/googleplay/android-developer/answer/10787469
- https://support.google.com/googleplay/android-developer/answer/9888170
