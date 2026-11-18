# Solarna research and mathematics notes

Last reviewed: 2026-09-18

This document records the scientific basis of the current prototype and separates
implemented behavior from future validation. It is not a certification report.

## Current objective

For a fixed monofacial array at a specified site, find the sampled tilt and azimuth
that maximize modeled annual AC electrical energy:

\[
(\beta^*, \gamma^*) =
\underset{(\beta,\gamma)\in\mathcal F}{\arg\max}
\sum_t P_{\mathrm{AC},t}(\beta,\gamma)\Delta t
\]

where:

- \(\beta\) is tilt from horizontal, from 0° to 90°;
- \(\gamma\) is azimuth clockwise from true north, so south is 180°;
- \(\mathcal F\) is the set of allowed fixed orientations;
- the current timestep is one hour.

The objective is not instantaneous irradiance, optical absorption alone, revenue,
self-consumption, or structural suitability.

## Hourly calculation chain

### 1. Solar position and incidence angle

The application calculates apparent solar zenith \(z_t\) and solar azimuth
\(\gamma_{s,t}\). The incidence angle between the solar beam and panel normal is:

\[
\cos\theta_t =
\cos z_t \cos\beta +
\sin z_t \sin\beta \cos(\gamma_{s,t}-\gamma)
\]

The NREL SPA implementation in pvlib supplies apparent solar position, including
atmospheric refraction near the horizon.

PVGIS TMY timestamps represent nominal hours. The provider's
`inputs.location.irradiance_time_offset` is added when calculating solar geometry,
because the JRC documentation says the offset locates the raw irradiance value
relative to the TMY hour and should be applied when calculating sun height. Weather
rows, temperature/wind pairing, calendar labels, and one-hour energy integration are
not shifted.

### 2. Irradiance on the panel plane

\[
G_{\mathrm{POA},t} =
G_{\mathrm{beam},t} +
G_{\mathrm{sky},t} +
G_{\mathrm{ground},t}
\]

The current implementation uses:

- PVGIS GHI, DNI, and DHI weather inputs;
- direct irradiance projected using incidence angle;
- continuous Perez-Driesse anisotropic sky-diffuse transposition;
- a constant-albedo ground-reflected component;
- no additional atmospheric attenuation multiplier, because the weather irradiance
  already contains atmospheric effects.

The web application reads the terrain elevation returned in the PVGIS location
metadata and applies it to solar-position calculations by default. A surveyed
elevation can still be entered manually. This removes the former 0 m placeholder
from normal use without presenting PVGIS grid elevation as a roof survey.

### 3. Cover optics

\[
G_{\mathrm{eff},t} =
IAM_{\mathrm{beam},t}G_{\mathrm{beam},t} +
IAM_{\mathrm{sky},t}G_{\mathrm{sky},t} +
IAM_{\mathrm{ground},t}G_{\mathrm{ground},t}
\]

The physical IAM model represents reflection, refraction, and absorption through the
module cover as incidence angle changes. Direct, sky-diffuse, and ground-diffuse
components do not receive one shared beam-angle correction.

The current optical properties are pvlib defaults, not measurements from a selected
module. Applying an isotropic-integrated diffuse IAM to aggregate Perez sky diffuse
is an approximation.

### 4. Cell temperature and electrical output

A selectable SAPM module-construction and mounting preset estimates cell
temperature from incident plane-of-array irradiance, air temperature, and wind
speed. The default remains open-rack glass/glass.

PVWatts-style DC power is:

\[
P_{\mathrm{DC},t} \approx
P_{\mathrm{STC}}
\frac{G_{\mathrm{eff},t}}{1000}
\left[1+\mu_P(T_{\mathrm{cell},t}-25)\right]
\]

The inverter model then applies nominal efficiency and clipping. Optional additional
DC losses are applied once after optical and temperature effects.

## Search method

The engine evaluates a complete coarse grid over tilt and azimuth, identifies the
best coarse point, and evaluates a finer local grid around it. The 30°-south and
latitude-tilt baselines also participate in the final candidate comparison.

This is transparent and reproducible, but it is not proof of a continuous global
optimum—particularly after future roof, shading, or row-spacing constraints are
introduced. The report therefore includes all sampled orientations within 1% of the
maximum. They are practical alternatives, not statistical confidence bounds.

An optional second search can optimize winter, spring, summer, autumn, or a
user-selected month set while leaving the primary all-year optimum unchanged. If
\(\mathcal M\) is the selected month set, its objective is:

\[
(\beta^*_{\mathcal M}, \gamma^*_{\mathcal M}) =
\underset{(\beta,\gamma)\in\mathcal F}{\arg\max}
\sum_{t:\operatorname{month}(t)\in\mathcal M}
P_{\mathrm{AC},t}(\beta,\gamma)\Delta t.
\]

The report compares selected-period gain against retaining the annual-optimum
orientation and reports the annual-energy tradeoff if the period optimum remained
fixed all year.

The primary result retains the best sampled numerical orientation. A separate
practical setting rounds tilt and azimuth to the nearest 5°, evaluates that setting
with the same model, and reports the retained energy and modeled loss. This avoids
presenting one-degree search resolution as installation precision.

## Current Sfax case

Source: PVGIS-SARAH3 irradiance and ERA5 meteorology typical-year data, with months
selected from 2005–2023 in the provider metadata.

For the approximate Sfax city-centre coordinate and the generic 1 kWp system:

- corrected-time optimum: 32° tilt, 182° azimuth;
- modeled annual AC energy: 1861.82 kWh/kWp;
- 30° south baseline: 1861.06 kWh/kWp;
- modeled gain: 0.041%, about 0.76 kWh/kWp/year;
- zero-offset sensitivity optimum: 32° tilt, 176° azimuth.

Interpretation: the timing metadata materially changes the precise east/west
direction reported by the numerical search, but it does not establish a meaningful
energy advantage over a practical 30° south installation. The rounded 30°/180°
setting retains 99.959% of the modeled maximum. Weather, equipment,
shading, soiling, mounting, and construction uncertainty are larger concerns than a
0.041% modeled gain.

## Tunisia-specific literature located

### Experimental multi-region work

Kaouther Belkilani, Afef Ben Othman, and Mongi Besbes,
“Estimation and experimental evaluation of the shortfall of photovoltaic plants in
Tunisia: case study of the use of titled [tilted] surfaces,” *Applied Physics A* 124,
179 (2018), DOI 10.1007/s00339-018-1581-x.

The publisher abstract says mathematical optimum-angle and adjustment-period models
were experimentally tested in northern, central, and southern Tunisia. This is
useful for validating seasonal/manual adjustment logic. It does not by itself
validate Solarna's current annual AC yield, because inputs, equipment, timestamps,
loss models, and objectives must first be matched.

### Bizerte, Nabeul, and Djerba tilted-surface work

Conference and bibliographic search results locate work titled “Global solar
radiation on tilted surfaces in Tunisia: Measurement, estimation and gained energy
assessments,” associated with Belkilani, Ben Othman, and Besbes. The abstract reports
comparison of models with measurements from Bizerte, Nabeul, and Djerba.

Before using numerical values from it, the complete publisher paper must be obtained
and the following extracted: dates, instruments, cleaning rules, angle convention,
tested angles, equations, error metrics, and raw-data availability.

### Tunis solar-collector study

Romdhane Ben Slama, “Incidental Solar Radiation According to the Solar Collector
Slope - Horizontal Measurements Conversion on an Inclined Panel Laws,” *The Open
Renewable Energy Journal* 2 (2009), pages 52-58.

The full primary text was inspected. For a south-facing collector in Tunis, it
reports approximately 40-42° for all-year irradiation, around 50° for a
September-May period, and around 58° for November-March. It also says a ±5° change
around the modeled optimum is tolerable. These are solar-collector irradiation
results using an older simplified model, not modern module-specific annual AC
validation targets.

The source-by-source evidence and applicability assessment are recorded in
`docs/TUNISIA_LITERATURE_MATRIX.md`.

### Gafsa case-study search

Search results locate “Optimization of tilt angle for solar panel: Case study
Tunisia,” attributed to Hatem Tlijani, Abir Aissaoui, and Rached Ben Younes. Its
complete methods and numerical tables still need primary-text extraction before it
is used as a validation target.

## Primary implementation references

- European Commission JRC, PVGIS 5.3 non-interactive API:
  https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/getting-started-pvgis/api-non-interactive-service_en
- European Commission JRC, PVGIS TMY generator and irradiance time offset:
  https://joint-research-centre.ec.europa.eu/photovoltaic-geographical-information-system-pvgis/pvgis-tools/pvgis-typical-meteorological-year-tmy-generator_en
- pvlib total plane-of-array irradiance:
  https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.irradiance.get_total_irradiance.html
- pvlib continuous Perez-Driesse sky-diffuse model:
  https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.irradiance.perez_driesse.html
- pvlib incidence-angle modifier overview:
  https://pvlib-python.readthedocs.io/en/stable/user_guide/modeling_topics/iam.html
- pvlib physical IAM:
  https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.iam.physical.html
- pvlib PVWatts DC model:
  https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.pvsystem.pvwatts_dc.html
- pvlib PVWatts inverter model:
  https://pvlib-python.readthedocs.io/en/stable/reference/generated/pvlib.inverter.pvwatts.html

## Validation ladder

The application should not be described as validated merely because software tests
pass. The required ladder is:

1. Software and physics invariants: units, angle conventions, night behavior,
   complete hourly years, timing signs, component separation, clipping, and search
   correctness.
2. Reproducible same-input comparison against PVGIS's independent PV calculation
   under closely matched system assumptions.
3. Multi-year historical analysis to quantify interannual movement of optimum and
   yield, rather than treating one TMY as uncertainty.
4. Reproduction of applicable Tunisian paper tables after matching periods,
   instruments, objectives, and conventions.
5. Comparison against local measured module production with calibrated equipment,
   soiling, thermal, shading, and downtime inputs.
6. Roof-level constraints, obstacle horizon, row shading, structural review, and
   electrical design before issuing an installation recommendation.

## Implemented PVGIS PVcalc benchmark

Solarna can now request PVGIS 5.3's independent grid-connected `PVcalc` model with
`optimalangles=1`. The benchmark fixes the provider inputs to 1 kWp crystalline
silicon, free-standing mounting, PVGIS-SARAH3, and provider horizon data. The
user's inverter efficiency and other DC loss are combined into PVGIS's single
system-loss input:

\[
L_{\mathrm{PVGIS}} =
100\left[1-\eta_{\mathrm{inv}}(1-L_{\mathrm{other}})\right].
\]

PVGIS aspect uses south as 0°, west as positive, and east as negative. Solarna
converts it to true-north clockwise azimuth:

\[
\gamma_{\mathrm{true\ north}} = (180^\circ + a_{\mathrm{PVGIS}}) \bmod 360^\circ.
\]

The report compares optimum angles, annual specific yield, monthly MAE/RMSE and
PVGIS's `SD_y` year-to-year standard deviation. It also records the provider's
calculation years and grid elevation when present.

The live Sfax benchmark was run on 2026-09-18 with an explicit test profile of
10 × 450 W modules (4.5 kWp DC) and the 4 kW Sungrow SG4.0RS preset. This is not
a measured panel configuration for a particular site. Solarna found 32° tilt
and 181° azimuth,
with 8,510.31 kWh/year and 1,891.18 kWh/kWp. PVGIS found 33° and 180°, with
1,921.39 kWh/kWp. Solarna's yield was 1.57% lower; monthly MAE was
6.67 kWh/kWp and RMSE was 7.52 kWh/kWp. PVGIS reported interannual standard
deviation of 29.47 kWh/kWp, or 1.53%.

For this test profile, the 358 sampled orientations within 1% of the modeled
maximum span 23–40° tilt and 170–190° azimuth. This is the bounding range of
qualifying sampled points; it does not mean every tilt/azimuth combination inside
that rectangle qualifies. It is an engineering tolerance indication, not a
statistical confidence interval.

This completes a numerical Sfax comparison for validation-ladder step 2. The
comparison cannot be called exactly matched because PVcalc does not expose the same
DC/AC ratio, clipping, altitude, TMY construction, or component models.

## Implemented historical range

Solarna can optionally request the PVGIS 5.3 historical hourly series for
2005–2023. The request uses a horizontal plane so the returned beam and diffuse
components can be converted to GHI, DHI, and DNI. DNI is reconstructed from
horizontal beam irradiance and the provider's sun-height value. The returned
timestamps already contain the radiation dataset's UTC minute, so the separate TMY
irradiance-time offset is not applied.

The same Solarna optical, thermal, and electrical model is then evaluated for:

- the TMY optimum;
- 30° south;
- the entered installation, when supplied.

For the generic 1 kWp Sfax profile, the 32°/182° TMY orientation produced:

- 1,835.95–1,951.11 kWh/kWp minimum-to-maximum annual modeled yield;
- 1,861.01–1,928.11 kWh/kWp P10–P90 historical range;
- 1,904.86 kWh/kWp median;
- 1.48% coefficient of variation.

Its median modeled gain over 30° south was 0.045%. It was higher in 17 of
19 years; 30° south was slightly higher in two years, with the worst difference
only -0.018%. This strengthens the practical interpretation that exact numerical
azimuth is less important than site constraints and unmodeled installation effects.

These values are model outputs for sampled historical weather. P10–P90 is not a
confidence interval, and the current feature does not re-optimize the angle for each
year. Year-by-year angle search remains separate future work.

## 24-location Tunisia comparison

The repeatable validation command is:

```powershell
.\.venv\Scripts\python.exe -m solarna.validation --sites examples\tunisia-governorate-capitals.csv
```

The 2026-09-18 live run used the same explicit 4.5 kWp DC / 4 kW AC SG4.0RS
validation profile as the Sfax comparison. It completed all 24 governorate
capitals with PVGIS terrain elevation applied to each point.

- mean absolute optimum-tilt difference: 0.71°;
- maximum absolute optimum-tilt difference: 1.00°;
- mean absolute optimum-azimuth difference: 1.83°;
- maximum absolute optimum-azimuth difference: 10.00°;
- mean signed annual-yield difference: +0.82% of PVGIS;
- median signed annual-yield difference: +0.41% of PVGIS;
- mean absolute annual-yield difference: 1.37%;
- maximum absolute annual-yield difference: 5.84%;
- annual-yield difference range: -1.89% to +5.84%;
- mean monthly MAE: 7.70 kWh/kWp;
- mean monthly RMSE: 9.60 kWh/kWp.

The maximum yield difference occurred at Jendouba (+5.84%); Beja was next
(+4.58%). These differences remain within a comparison of two non-identical
models and weather aggregations. They are not evidence that either model matches
measured production at those sites.

These are 24 point comparisons, not continuous nationwide coverage or field
validation. The full machine-readable result is
`outputs/validation/tunisia-24-summary-0.4.0.json`.

PVGIS returned one or two negative wind-speed samples at seven of the 24 points,
with 10 repaired rows and a minimum of -0.67 m/s. Wind speed is a nonnegative
physical magnitude.
Solarna therefore clips only provider values in the bounded interval
[-1.0, 0) m/s to zero, records the count and original minimum in weather
provenance, and rejects values below -1.0 m/s as possible corruption.

## Native Android verification

The URL-neutral 0.3.3 APK was installed on an Android API 36 emulator on
2026-09-18. An automated WebView smoke test entered the authenticated HTTPS
server address, confirmed all three system-sizing modes, and completed the
normalized Sfax analysis. It rendered 32° tilt, 182° true-north azimuth and
1,882.0 kWh/kWp. The 2005–2023 historical median was 1,925.7 kWh/kWp, and the
live PVGIS benchmark returned 33°/180° and 1,921.4 kWh/kWp. The machine-readable
result and screenshot are
`outputs/deliverables/android-smoke-result-0.3.3.json` and
`outputs/deliverables/Solarna-android-0.3.3-result.png`.

## Native iOS package verification

The synchronized Capacitor iOS project targets iOS 15 or later and includes the
Solarna Systems assets, location permission text, HTTPS-only production settings,
an application privacy manifest, a synchronized public privacy notice, an App
Store submission checklist, a standalone macOS archive script, and a
1024 × 1024 opaque RGB App Store icon.
Automated checks verify the project metadata, bundle identifier, icon format,
privacy resource wiring, iPhone installation detection, and equality of the
packaged web assets. The HTTPS web release also exposes a concise Install on
iPhone action on an uninstalled iPhone or iPad.
The Windows-built source package is
`outputs/deliverables/Solarna-iOS-project.zip`; a signed IPA still requires
macOS, Xcode, an Apple developer team, and signing credentials.

## Sungrow SG4.0RS preset

The preset follows Sungrow's official SG3.6RS/SG4.0RS datasheet:

https://info-support.sungrowpower.com/application/pdf/2024/05/31/DS_20240528_SG3.6_4.0RS_JO_Datasheet_V1_EN.pdf

- exact model: SG4.0RS;
- nominal AC output: 4 kW;
- recommended maximum PV input power: 7.2 kWp;
- maximum efficiency: 97.9%;
- European efficiency: 97.2%.

Solarna uses the 97.2% European efficiency as its representative inverter
efficiency. The 7.2 kWp value is a datasheet design recommendation, not evidence of
the installed array size. The panel count and module wattage remain required.

SG4.0RS-L is a different inverter variant with different PV-input specifications
and must not be substituted for SG4.0RS.

## Planned model improvements

- year-by-year historical angle re-optimization;
- module database presets for optical and electrical parameters beyond the current
  representative SAPM thermal/mounting sets;
- roof azimuth/tilt constraints and obstacle horizon input;
- custom-month, self-consumption, and tariff-weighted objectives beyond the
  implemented winter/summer presets;
- soiling scenarios and Tunisia-specific calibration;
- bilingual Arabic/French interface;
- HTTPS deployment and real iPhone acceptance testing.
