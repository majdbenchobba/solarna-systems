# Solarna PV

An official Solarna Systems application that searches for the **fixed monofacial panel
orientation maximizing modeled annual AC electrical energy**. Results remain model
estimates rather than certified roof designs.

## Repository layout

- `solarna/` — Python model, API, and web application.
- `mobile/` — Android and iPhone native projects and build tooling.
- `scripts/build/` — release packaging.
- `scripts/development/` — local, LAN, and HTTPS preview launchers.
- `scripts/production/` — production setup and service launchers.
- `deploy/` — AWS, Cloudflare Tunnel, and reverse-proxy configuration.
- `tests/` — Python and workflow tests.
- `docs/` and `examples/` — research notes and Tunisia datasets.

## Interactive application

Start the local application:

```powershell
.\scripts\development\start-solarna.cmd
```

Then open `http://127.0.0.1:8765/`.

The launcher works without installing the project itself as an editable package,
provided the existing `.venv` contains the dependencies. The equivalent explicit
command remains `.\.venv\Scripts\python.exe -m solarna.app`.

The application provides:

- Tunisia city presets, custom coordinates, and browser geolocation.
- All 24 governorate-capital presets use coordinates from Tunisia's Ministry of
  Interior open-data catalogue; Djerba remains an additional research location.
- PVGIS terrain elevation is applied automatically by default, with a manual
  elevation option for surveyed site data.
- Panel count and module wattage sizing, inverter AC rating, mounting type,
  albedo, temperature coefficient, inverter efficiency, and additional-loss inputs.
- A normalized orientation-only mode when system size is unknown. It reports
  kWh/kWp using an explicit 1 kWp, DC/AC 1.20 reference instead of guessing
  installed capacity.
- An exact Sungrow SG4.0RS preset: 4 kW AC, 97.2% European efficiency, and
  7.2 kWp recommended maximum PV input. Actual installed DC capacity still
  requires the panel count and module wattage from the roof or module label.
- A queued background calculation with live coarse/refined search progress.
- Corrected PVGIS timing, with an optional zero-offset sensitivity comparison.
- Optional winter, spring, summer, autumn, or custom-month electrical-energy
  optimization alongside the unchanged all-year optimum.
- An optional independent PVGIS PVcalc benchmark of optimum fixed angles, annual
  yield, monthly error, and provider-reported interannual variation.
- Optional comparison with an existing installation's tilt and direction, using
  the same weather, optical, thermal and electrical model as the optimizer.
- Optional 2005–2023 historical range for the TMY optimum, 30° south, and the
  entered installation. It reports annual values, P10/median/P90, and yearly
  comparison gains without presenting them as confidence bounds.
- Best sampled tilt/azimuth, a practical setting rounded to 5°, annual and monthly
  energy, 30°-south comparison, accessible heatmap data, near-optimal
  interpretation, assumptions, and provenance.
- Atomic JSON report files under `outputs/app/`.
- Private saved projects linked to the signed-in Supabase user, with row-level
  security. Local deployments without Supabase retain server report files.
- CSV import of daily or monthly inverter production using `date` and
  `actual_kwh` columns, with actual-versus-estimated monthly charts and totals.
- JSON and spreadsheet-safe CSV downloads, print-to-PDF styling, and native Web
  Share support where the browser provides it.
- A responsive installable web application with a manifest, icons, service worker,
  cached shell, last-report browser storage, and a concise iPhone installation
  action. New calculations still require the Python server and PVGIS access when
  weather is not cached. Installer downloads bypass the offline cache so a failed
  connection cannot produce a corrupt APK or ZIP.

The included server binds to loopback by default. It is a local research server, not
a hardened public deployment. For temporary testing from another device on the same
network, `--host 0.0.0.0` can expose it over unencrypted LAN HTTP. Do not expose that
mode to the public Internet or treat it as the final iOS deployment.

For a phone on the same private Wi-Fi network, start the LAN server and build the
isolated Android package:

```powershell
.\scripts\development\start-solarna-lan.ps1
.\mobile\build-android-lan-test.ps1 -ApiUrl http://192.168.1.20:8766
```

Use the IPv4 address printed by the first command. The LAN package is for local
testing only and the build process restores the Android project to HTTPS-only mode.
The LAN web application exposes the current APK at
`/downloads/solarna-android.apk` and the verified Xcode package at
`/downloads/solarna-ios-project.zip`.

The mathematical and literature basis is recorded in
[`docs/RESEARCH_NOTES.md`](docs/RESEARCH_NOTES.md). A source-by-source matrix of
verified Tunisian findings, missing evidence, and appropriate validation uses is in
[`docs/TUNISIA_LITERATURE_MATRIX.md`](docs/TUNISIA_LITERATURE_MATRIX.md).

## Install and run (PowerShell, Python 3.11+)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m solarna --output outputs/sfax.json
.\.venv\Scripts\python.exe -m solarna --pvgis-benchmark --output outputs/sfax.json
.\.venv\Scripts\python.exe -m solarna --period-analysis winter --output outputs/sfax-winter.json
```

The first actual run requires internet access to the European Commission's PVGIS API and can take a few minutes. It downloads hourly typical-meteorological-year (TMY) weather and caches it in `.cache/pvgis/`. No API key is needed. Failures are surfaced; there is **no synthetic-data fallback**. Subsequent runs reuse the provenance-bearing cache. Use `--refresh-weather` to fetch again. Package installation also requires internet access. pvlib is pinned; this is not a fully locked dependency environment.

The default CLI site is **34.7406 N, 10.7603 E**, approximate Sfax city centre,
**not a particular roof**. The web application resolves terrain elevation from
PVGIS by default. The CLI accepts a surveyed/site-specific altitude, for example:

```powershell
.\.venv\Scripts\python.exe -m solarna --latitude 36.8065 --longitude 10.1815 --name Tunis --altitude-m 0 --output outputs/tunis.json
```

Coordinates are illustrative city-centre coordinates. No nationwide angle table has been computed or verified.

## Model and assumptions

1. PVGIS 5.3 supplies hourly GHI, DNI, DHI (W/m2), air temperature (C) and wind (m/s). `usehorizon=True` requests the provider's far-horizon treatment; no second horizon mask is added here. Source metadata is saved in the cache and report.
2. TMY samples are assigned to the continuous non-leap year 1990, in UTC. They are representative months from historical years, **not a forecast**. Solar geometry and extraterrestrial DNI use nominal timestamps **plus** PVGIS `inputs.location.irradiance_time_offset` (hours). Weather rows, temperature/wind pairing, nominal month labels and one-hour energy integration stay unchanged. Raw caches are not shifted or rewritten; the offset is applied once per simulation. Missing, nonnumeric or out-of-range timing metadata fails explicitly: refresh older provider responses rather than assuming zero. Subhourly/cloud approximation remains.
   The optional historical range instead uses complete PVGIS-SARAH3 calendar
   years 2005–2023 at the dataset's returned UTC minute. It reconstructs DNI
   from horizontal beam irradiance and provider sun height, then applies no
   additional TMY timing offset.
3. pvlib NREL SPA gives apparent solar position, including atmospheric refraction. Measured/satellite-derived irradiance already contains atmospheric effects; we do **not** multiply by another atmospheric attenuation factor.
4. Continuous Perez-Driesse transposition estimates direct, sky-diffuse and
   ground-reflected plane-of-array irradiance. It avoids discontinuities in the
   original Perez coefficient bins during orientation optimization. Constant
   ground albedo defaults to 0.2. Below-horizon production is set to zero.
5. Physical incidence-angle modifiers represent glass reflection/refraction and absorption with pvlib's default glass properties, not measured properties of a selected module. Direct radiation uses its own incidence angle; sky and ground use separate Marion-integrated diffuse modifiers. Applying an isotropic-integrated modifier to aggregate anisotropic Perez sky radiation is an approximation.
6. A selectable SAPM module/mounting thermal preset estimates cell temperature from
   total incident irradiance, air temperature and wind. Available presets are
   open-rack glass/glass, open-rack glass/polymer, close-mount glass/glass, and
   insulated-back glass/polymer. These are representative parameter sets, not a
   calibrated model of an individual roof.
7. PVWatts DC uses a user-selectable power temperature coefficient (default
   -0.004/°C). PVWatts inverter efficiency and clipping produce AC output. The web
   form calculates DC capacity from panel count and module wattage, then derives the
   DC/AC ratio from the selected inverter rating.
8. Additional DC losses default to **zero**. `--other-dc-loss-fraction` can specify a lumped loss, but no local soiling, wiring, mismatch or degradation estimate is invented. Do not include the optical losses again in this parameter.
9. Hourly energy = sum(AC watts × 1 hour) / 1000. Full-year optimization rejects missing hours, NaNs, naive timestamps and incomplete years.

The objective is electrical kWh, **not** total optical energy absorbed, revenue, self-consumption, or power at noon. No nearby building/tree shading, inter-row shading, terrain reconstruction, mounting limits, structural/wind checks, snow, bifacial gain, module spectral response, or detailed MPPT behavior is modeled.

## Orientation search and report

Angles: tilt from horizontal (0 degrees flat, 90 vertical); azimuth clockwise from **true north** (0 north, 90 east, 180 south, 270 west). PVGIS's orientation API uses a different convention; this engine only requests its weather, not its optimum-angle answer.

The default search scans tilt 0..90 degrees and all azimuths at 5-degree spacing, then refines within 5 degrees of the best coarse point at 1-degree spacing. `--fine-step 0.5` changes numerical resolution, not scientific accuracy. A coarse-to-fine search does not prove a continuous global optimum, especially after future shading constraints are introduced.

JSON includes:

- Best sampled tilt/azimuth, modeled annual AC kWh, kWh/kWp, incident POA kWh/m2 and monthly AC energy.
- Comparisons with 30 degrees south and latitude tilt facing the equator; these baselines participate in the candidate search.
- Every sampled orientation within 1% of the best modeled energy. These alternatives are **not confidence bounds**, nor an assertion that every angle between them is equally good.
- Weather provenance, software versions, configuration and limitations.
- When requested, a separate selected-period optimum, energy gain during those
  months, annual-energy tradeoff, baselines, near-optimal alternatives, and coarse
  period-energy grid. It does not relabel the primary annual result.

No genuine Sfax numerical optimum is asserted until a real-weather run succeeds. Even then, weather/model uncertainty may matter more than small angle differences. Use a near-optimal practical angle, subject to actual installation constraints.

## Timing comparison and mobile report

```powershell
.\.venv\Scripts\python.exe -m solarna --timing-sensitivity --output outputs/sfax.json
.\.venv\Scripts\python.exe -m solarna.dashboard --reports outputs --output outputs/web
.\.venv\Scripts\python.exe -m solarna.dashboard --reports outputs --output outputs/web --check
```

Schema v2 reports include timing provenance, generation time and a complete **coarse** energy grid (tilt rows, azimuth columns). Optional timing sensitivity reoptimizes identical weather/system/search with zero offset, records both optima, cross-evaluates their orientations, and reports the change. This is **not** a comparison against PVGIS's independent production model, field validation or uncertainty estimate. Existing v1 reports must be regenerated; the dashboard rejects them rather than inventing missing data.

With `--pvgis-benchmark`, the report also asks PVGIS 5.3 `PVcalc` to optimize both
fixed angles for a normalized 1 kWp crystalline-silicon, free-standing system using
PVGIS-SARAH3 and the provider horizon. Solarna combines its inverter efficiency and
additional DC loss into PVGIS's single system-loss input. The report converts
PVGIS's south-based aspect convention to true-north azimuth and compares angles,
annual specific yield, monthly MAE/RMSE, and PVGIS's `SD_y` interannual standard
deviation. This is a useful independent-model check, but it is not a matched
simulation or field validation: TMY versus multi-year aggregation, elevation,
transposition, optics, temperature, low-light behavior, inverter behavior and
clipping differ.

The dashboard generator reads only `*.json` directly inside the reports directory, validates numeric/grid/monthly invariants, then produces self-contained HTML with responsive layout, a labeled SVG heatmap, accessible numeric table, monthly yields, baseline gain, assumptions and provenance. All report text is HTML-escaped. There is no JavaScript, CDN, browser-side PVGIS call or secret. `--check` is read-only and verifies all six generated artifacts exactly match current source reports. It is not a browser/device rendering test.

For local desktop preview, run this server manually and stop it with Ctrl+C:

```powershell
.\.venv\Scripts\python.exe -m http.server 8000 --bind 127.0.0.1 --directory outputs/web
```

Open `http://127.0.0.1:8000`. This loopback server is not accessible from your phone.

## Web deployment

The repository includes a containerized web server with persistent weather and
report volumes:

```powershell
docker compose up --build
```

The service listens on port 8765. For public deployment, place it behind an HTTPS
reverse proxy or a managed container platform and restrict access as appropriate.
Set `SOLARNA_ALLOWED_ORIGINS` to the exact native application origins that may call
the API.

An HTTPS production profile using Caddy is included. Copy
`.env.production.example` to `.env.production`, replace the example domain,
ACME email, Supabase URL, publishable key and authorized email list, point the
domain's DNS records at the server,
then run:

```powershell
docker compose --env-file .env.production -f compose.production.yaml up --build -d
```

Before deploying version 0.5.0, apply the SQL migration documented in
[`supabase/README.md`](supabase/README.md) to the configured Supabase project.

Caddy obtains and renews public TLS certificates automatically. The production
profile exposes only ports 80 and 443; the Python service remains on the internal
container network. Reports and calculations require login;
the health endpoint exposes only service and bounded-queue status. The server
accepts at most four active or queued calculations and returns a retryable HTTP
429 response when full. The browser and native applications store an expiring
session, not the password. Build the mobile applications with the same HTTPS
origin:

```powershell
.\mobile\build-android.ps1 -ApiUrl https://your-domain.example
```

For a Cloudflare named tunnel, use the isolated profile. It publishes no host
ports and includes the web application, Android APK and iOS project download:

```powershell
Copy-Item .env.tunnel.example .env.tunnel
docker compose --env-file .env.tunnel -f compose.tunnel.yaml config
docker compose --env-file .env.tunnel -f compose.tunnel.yaml up --build -d
```

Configure the tunnel's public hostname to route to
`http://solarna:8080`. Deployment and rollback instructions are in
`deploy/cloudflare-tunnel/README.md`. A dedicated host with at least 2 GB of
memory is recommended so calculations do not compete with unrelated services.

## Android and iOS applications

Native Capacitor projects are included under `mobile/android/` and `mobile/ios/`.
They package the responsive interface locally and connect to the deployed Python
server over HTTPS. The server address can be entered inside the application or
embedded at build time.

Create the tested Android APK, verified iOS project package, and SHA-256 release
manifest with one command. The same command also creates
`outputs/deliverables/Solarna-server.zip` for production deployment:

```powershell
.\scripts\build\build-release.ps1
```

Use `-ApiUrl https://your-domain.example` to preconfigure the Android APK for a
permanent HTTPS deployment. Without it, the server address is entered inside the
application.

```powershell
cd mobile
npm install
npm run prepare:web -- --api-url https://solarna.example.com
npx cap sync
```

Build the Android debug package on Windows:

```powershell
.\mobile\build-android.ps1 -ApiUrl https://solarna.example.com
```

The APK is written to `outputs/mobile/Solarna-android-debug.apk`. A signed Android
App Bundle for Google Play requires a release keystore. The verified iOS Xcode
package is `outputs/deliverables/Solarna-iOS-project.zip`; its App Store icon is
an opaque 1024 × 1024 RGB PNG. The package includes the application privacy
manifest, synchronized privacy notice, App Store submission checklist and a
standalone macOS archive script.
Compiling, signing and submitting the iOS application requires macOS, Xcode and
an Apple developer configuration.

The Android API 36 emulator workflow verifies login, panel-count,
direct-capacity and normalized sizing modes against the configured server.
The normalized Sfax analysis rendered 32° tilt, 182° azimuth and
1,882.0 kWh/kWp. Against a 20° tilt and 180° azimuth test orientation, it
reported 1,850.7 kWh/kWp and a 31.3 kWh/kWp (1.69%) optimized gain. The
20°/180° values are test data, not measurements from a particular installation.
The 2005–2023 historical range reported a 1,925.7 kWh/kWp median and
1,881.5–1,949.5 kWh/kWp P10–P90 range at the TMY optimum. Its median gain over
30° south was 0.045%, with higher modeled yield in 17 of 19 years. The live
PVGIS benchmark returned 33°/180° and 1,921.4 kWh/kWp. National validation
evidence is stored under `outputs/validation/`.

After setting the four `SOLARNA_ANDROID_*` signing variables documented in
`mobile/README.md`, create and verify the signed App Bundle with:

```powershell
.\mobile\build-android-release.ps1
```

This keeps the application URL-neutral. Pass
`-ApiUrl https://your-domain.example` to embed a permanent production server.
Submission values and the Data safety draft are in
`mobile/ANDROID-STORE-SUBMISSION.md`.

On macOS, create a URL-neutral signed iOS archive with:

```bash
export SOLARNA_IOS_TEAM_ID="YOURTEAMID"
./mobile/build-ios-release.sh
```

Set `SOLARNA_IOS_EXPORT_OPTIONS_PLIST` to an options file exported by Xcode when
an IPA is required. Pass a permanent HTTPS origin as the optional script
argument to embed it in the app.

Compile an unsigned iOS Simulator application on macOS with:

```bash
bash mobile/build-ios-simulator.sh
```

The native verification workflow under `.github/workflows/` runs the Python
suite, builds Android on Windows, compiles iOS on macOS, and publishes both test
artifacts.

For an isolated end-to-end Android emulator test, run a second local server with
`--port 8766 --allowed-origin http://localhost`, then run
`.\mobile\build-android-emulator-e2e.ps1`. This creates a separate cleartext test
APK and restores the checked-in native project to its HTTPS-only production
configuration afterwards.

For an already running debuggable WebView, forward its DevTools socket and run
`npm run smoke:android` with `SOLARNA_TEST_SERVER_URL` and
`SOLARNA_TEST_LOGIN_EMAIL` and `SOLARNA_TEST_LOGIN_PASSWORD`. The smoke test
connects the URL-neutral APK, enters a 10 × 450 W system, completes an
optimization, and returns the rendered result.

The browser application can also be installed as a PWA when served over HTTPS.
On an uninstalled iPhone or iPad it shows Install on iPhone with the three
Safari steps needed to add it to the Home Screen. The app shell and last
displayed report are available offline; new calculations require the Python
server.

For a temporary authenticated HTTPS preview from this computer, install
`cloudflared` and run:

```powershell
.\scripts\development\start-solarna-https-preview.ps1 -BuildAndroid
```

The launcher keeps the Python server on loopback, configures a temporary login,
creates a Cloudflare Quick Tunnel, verifies the public health endpoint, and
optionally builds an Android APK for the generated HTTPS address. It prints the
temporary web/iPhone URL, login and Android download URL. Keep its window
open; stopping it ends the preview. Quick Tunnels are for testing and have no
uptime guarantee. Use the Caddy production profile or a named tunnel for
permanent deployment.

For the named production tunnel on this Windows host, prepare the restricted
credential files once, then start the loopback-only service:

```powershell
.\scripts\production\setup-solarna-production.ps1 `
  -SupabaseUrl https://your-project.supabase.co `
  -SupabasePublishableKey sb_publishable_replace_me
.\scripts\production\start-solarna-production.ps1
```

The configured public origin is `https://pv.solarnasystems.com`. The tunnel
token, Supabase configuration and authorized email list are stored only in the
ignored `secrets` directory and are not included in the release archive.

## Tunisia batch foundation

```powershell
.\.venv\Scripts\python.exe -m solarna.batch --sites examples/tunisia-sites.csv --output outputs/tunisia --pause-seconds 1
.\.venv\Scripts\python.exe -m solarna.batch --sites examples/tunisia-governorate-capitals.csv --output outputs/governorates --pause-seconds 1
.\.venv\Scripts\python.exe -m solarna.dashboard --reports outputs/tunisia --output outputs/tunisia-web
```

`examples/tunisia-sites.csv` contains five earlier illustrative locations.
`examples/tunisia-governorate-capitals.csv` contains all 24 governorate capitals
using coordinates published by Tunisia's Ministry of Interior, normalized only for
spelling and safe IDs. Both files retain altitude 0 m placeholders that must be
replaced for direct batch use. The web application and validation workflow resolve
PVGIS terrain elevation automatically. The 24 points are a national comparison
sample, **not continuous coverage and not roof coordinates**.

CSV header/order is `id,name,latitude,longitude,altitude_m`. IDs must be unique
lowercase safe slugs. All rows are validated before requests; broad Tunisia-region
coordinate bounds are only a sanity check, not a border or roof check. Each run
supports 1-200 sites, reuses caches, processes sequentially, and waits at least one
second between sites. No batch is automatically downloaded by installation or
tests.

Reports are named `site-ID.json`. Per-site failures are printed and cause a nonzero
exit after remaining sites are attempted; previous successful reports remain
unchanged and can be stale. Use a fresh output directory or inspect generation
timestamps before publishing after a partial failure. Validation retries transient
provider connection failures at most twice. No synthetic fallback or implicit
nationwide fetch is used. Current batch defaults are the same generic 1 kWp system
as the single-site run.

Run the repeatable national PVGIS comparison with:

```powershell
.\.venv\Scripts\python.exe -m solarna.validation --sites examples/tunisia-governorate-capitals.csv
```

This saves complete reports under `outputs/validation/reports/` and aggregate
metrics in `outputs/validation/tunisia-summary.json`. The default validation
profile is explicitly 4.5 kWp DC, 4 kW AC, 97.2% inverter efficiency and zero
additional DC loss. It is a test profile, not a confirmed configuration for any
particular array.

The live 24-capital run on 2026-09-18 completed without failures. Versus PVGIS
PVcalc, the mean absolute tilt difference was 0.71°, mean absolute azimuth
difference was 1.83°, mean absolute annual-yield difference was 1.37%, and the
maximum absolute annual-yield difference was 5.84%. Mean monthly MAE was
7.70 kWh/kWp and mean monthly RMSE was 9.60 kWh/kWp. The maximum yield
difference occurred at Jendouba; this comparison is not field validation.

Seven downloaded PVGIS TMY files contained one or two negative wind-speed samples,
with 10 repaired rows and a minimum of -0.67 m/s. Because wind speed is a
nonnegative magnitude, Solarna
clips only bounded provider values from -1.0 to 0 m/s to zero and records every
change in weather provenance. Values below -1.0 m/s remain a hard error.

## Validation status and next steps

Offline tests use explicitly synthetic clear-sky weather for physics sanity checks and a known analytic energy surface for search correctness. They exercise timing sign/row pairing/calendar boundaries, bounded provider-data repair, metadata rejection, cache preservation, report/CLI wiring, coarse-grid layout, comparison scenarios, dashboard escaping/schema validation/icons/artifact checks, batch validation/pacing/failure handling, and aggregate multi-site validation, alongside the original physics tests. **Passing tests are not field validation.** Artifact checks do not substitute for visual Safari or iPhone testing.

Remaining research work:

1. Obtain the complete numerical tables and methods for the 2018 north/center/south
   studies; the accessible abstracts are now extracted, but do not expose numeric
   validation targets.
2. Interpret the implemented PVGIS orientation benchmark, then add an independent Global Solar Atlas comparison.
3. Re-optimize individual historical years to measure movement of the sampled
   optimum; the implemented historical range currently evaluates selected
   orientations rather than repeating the full search for each year.
4. Calibrate real panel/cover/thermal parameters and validate against local measurements.
5. Add roof constraints, obstacles and row geometry before claiming a site-specific installation design.
6. Field-test the mobile report against measured plant production.

## Reference documentation

- Tunisia Ministry of Interior governorate-capital coordinates:
  https://opendata.interieur.gov.tn/fr/catalog/coordonnees-des-chefs-lieux-des-gouvernorats-de-la-republique-tunisienne
- PVGIS API: https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/using-pvgis-5/api-non-interactive-service_en
- pvlib TMY acquisition: https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.iotools.get_pvgis_tmy.html
- Physical IAM: https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.iam.physical.html
- Diffuse IAM: https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.iam.marion_diffuse.html
- Perez-Driesse transposition:
  https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.irradiance.perez_driesse.html

Reports are model estimates, not field-certified recommendations. This repository does not include downloaded research papers or proprietary datasets.
