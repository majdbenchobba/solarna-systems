# Tunisia solar-orientation literature matrix

Last reviewed: 2026-09-18

This matrix records what the accessible primary text actually establishes, what it
does not establish, and how each source can be used to validate Solarna. Values from
search snippets or earlier conversations are excluded unless the underlying source
was inspected.

## 1. Tunis solar-collector study

**Source**

Romdhane Ben Slama, “Incidental Solar Radiation According to the Solar Collector
Slope - Horizontal Measurements Conversion on an Inclined Panel Laws,” *The Open
Renewable Energy Journal* 2 (2009), 52-58.

Primary text:
https://benthamopen.com/contents/pdf/TOREJ/TOREJ-2-52.pdf

**Site and objective**

- Tunis: latitude 36.85° N, longitude 10.2° E.
- South-facing solar collector.
- Objective: incident solar radiation / solar-water-heater usefulness, not annual AC
  electricity from a modern PV system.
- The paper evaluates all-year use and winter-centered periods of 9, 7, and 5
  months.

**Extracted findings**

- The paper's monthly ideal tilt spans approximately 14° to 60°.
- For all-year use, the text recommends approximately 40° and separately discusses
  about 42° (latitude plus roughly 5°) when albedo contribution is included.
- For September-May use, the reported optimum is around 50°.
- For November-March use, the reported optimum is around 58°; the broader
  interpretation is 50-60° when winter is privileged.
- The paper says a ±5° change around the modeled optimum is tolerable.
- For its five-month winter example, raising albedo from 0.1 to 0.9 moves the
  modeled optimum from about 50° to 65° and increases received energy by about 10%
  at 55°.

**Model and validation limits**

- Uses a Bernard-Menguy-Schwartz clear-sky style calculation and horizontal
  global/diffuse conversion, not PVGIS hourly weather or Solarna's Perez/pvlib
  chain.
- Its appendix compares one clear-sky Gabès day against weather measurements:
  reported instantaneous error remains within ±10%, while the daily total exceeds
  the measurements by 1%.
- Its yearly comparison is against the Tecsol software, not measured PV output; the
  paper reports a 3.3% annual difference.
- It is therefore a useful period-objective and angle-sensitivity reference, but not
  a direct target for Solarna's annual AC yield.

**Solarna validation use**

1. Add winter- and custom-period optimization without changing angle conventions.
2. Reproduce the paper's simplified Tunis irradiation objective separately.
3. Compare whether Solarna's richer weather model preserves the qualitative result:
   winter-prioritized tilt should be steeper than annual-optimum tilt.
4. Do not require Solarna's annual electrical optimum to equal 40-42°.

## 2. North, center, and south experimental PV work

**Source**

Kaouther Belkilani, Afef Ben Othman, and Mongi Besbes, “Estimation and
experimental evaluation of the shortfall of photovoltaic plants in Tunisia: case
study of the use of titled [tilted] surfaces,” *Applied Physics A* 124, 179 (2018).
DOI: 10.1007/s00339-018-1581-x.

Publisher record:
https://link.springer.com/doi/10.1007/s00339-018-1581-x

**What the accessible publisher record establishes**

- Mathematical models determine optimal tilt and how long an angle should remain
  in place before manual adjustment.
- Theoretical results were tested experimentally in northern, central, and southern
  Tunisia.
- The objective is reduction of fixed-panel shortfall relative to tracking.

**What remains unavailable**

- The publisher page exposes the abstract but not the numerical tables, exact sites,
  tested panels, periods, instruments, cleaning rules, error metrics, or optimal
  angles.
- No numeric value from this paper is currently encoded as a Solarna validation
  target.

## 3. Bizerte, Nabeul, Djerba, and Borj Cedria abstract

**Source**

Kaouther Belkilani, “Global solar radiation on tilted surfaces in Tunisia:
Measurement, estimation and gained energy assessments,” conference abstract,
Applied Physics conference, 2018.

Primary abstract:
https://www.alliedacademies.org/conference-abstracts-files/global-solar-radiation-on-tilted-surfaces-in-tunisia-measurement-estimation-and-gained-energy-assessments.pdf

**What the accessible abstract establishes**

- Numerical models estimate monthly, seasonal, and annual global, direct, and
  diffuse energy on tilted surfaces.
- The comparison regions are Bizerte, Nabeul, and Djerba.
- The abstract says modeled and meteorological-station measurements were close, but
  supplies no numeric error metric.
- Practical validation of optimal tilt and adjustment period was performed at the
  Research and Technology Center of Energy in Borj Cedria.

**Validation limit**

The one-page abstract does not expose the data, equations, angle table, sample
period, or error metrics needed for numerical reproduction. It supports the
regional validation plan, not a numeric acceptance threshold.

## 4. Claims still not verified from primary text

The following claims from the earlier conversation are not application inputs:

- a Gafsa paper's exact optimal angle or experimental result;
- a Monastir annual rule of `0.9 × latitude`;
- a nationwide official Tunisian requirement that 30° is universally optimal;
- illustrative values such as 27.4°, 1,842 kWh/kWp, or a 2.8% gain.

They remain research leads until the complete primary paper or technical standard is
inspected and its conditions are extracted.

## 5. Product requirements supported by the literature

- Keep annual fixed-panel electrical optimization as the default.
- Add selectable optimization periods; a winter objective is physically and
  practically different from annual energy.
- Show a near-optimal range or sensitivity rather than false decimal precision.
- Keep albedo explicit because its influence increases at steep tilt.
- Separate solar-thermal irradiation studies from electrical PV validation.
- Validate north, center, and south separately instead of publishing one Tunisia
  lookup angle.
- Store source, period, objective, convention, equipment, and error metric with
  every future literature benchmark.
