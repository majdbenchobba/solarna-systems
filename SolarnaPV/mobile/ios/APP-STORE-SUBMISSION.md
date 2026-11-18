# Solarna PV App Store submission

Use this checklist after the permanent HTTPS server is available.

## Required values

- App name: `Solarna PV`
- Bundle identifier: `tn.solarna.optimizer`
- Privacy policy URL: `https://pv.solarnasystems.com/privacy.html`
- Support URL: `https://solarnasystems.com/`
- Contact: `contact@solarnasystems.com`

## App Privacy answers

Solarna does not track users and does not use data for advertising.

Declare these data types as collected for **App Functionality**, not linked to
the user's identity, and not used for tracking:

- Precise Location: submitted coordinates can be stored in completed reports.
- Other User Content: project names and user-entered PV-system settings can be
  stored in completed reports.

Review the answers again if analytics, accounts, advertising, crash reporting,
or another third-party service is added.

## Build the packaged project

1. Extract this ZIP on a Mac with Xcode installed.
2. Set `SOLARNA_IOS_TEAM_ID` to the Apple Developer team ID.
3. Run `sh build-ios-release.sh`.
4. Review the generated archive and privacy report in Xcode.
5. Export or upload using the selected distribution profile.

The packaged project is URL-neutral and asks for the server address in the app.
To embed `https://pv.solarnasystems.com`, run `build-ios-release.sh` with that
URL from the full SolarnaPV repository before packaging.

Apple references:

- https://developer.apple.com/help/app-store-connect/manage-app-information/manage-app-privacy/
- https://developer.apple.com/app-store/app-privacy-details/
- https://developer.apple.com/support/third-party-SDK-requirements/
