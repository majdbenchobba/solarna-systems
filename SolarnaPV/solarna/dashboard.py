"""Build a self-contained, read-only mobile report. No CDN or browser API calls."""

import argparse
import calendar
from html import escape
from importlib import resources
import json
import math
from pathlib import Path
import sys


def number(value, minimum=0, maximum=float('inf')):
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not minimum <= value <= maximum):
        raise ValueError('Invalid report number')
    return value


def validate_report(report):
    if report.get('schema_version') != 2:
        raise ValueError('Dashboard requires schema_version 2; regenerate older reports')
    best = report['best']
    number(best['tilt_deg'], 0, 90)
    number(best['azimuth_deg'], 0, 359.999999)
    if number(best['annual_ac_kwh']) <= 0:
        raise ValueError('Report must have positive annual generation')
    number(best['specific_yield_kwh_per_kwp'])
    number(report['system']['dc_capacity_kw'], 0.000001)
    number(report['site']['latitude'], -90, 90)
    number(report['site']['longitude'], -180, 180)
    number(report['timing']['irradiance_time_offset_hours'], -0.999999, 0.999999)
    monthly = best['monthly_ac_kwh']
    if set(monthly) != {str(m) for m in range(1, 13)}:
        raise ValueError('Report needs all twelve months')
    if not math.isclose(sum(number(v) for v in monthly.values()), best['annual_ac_kwh'], rel_tol=1e-8):
        raise ValueError('Monthly energy does not sum to annual energy')
    baseline = report['baselines']['30_degrees_south']
    number(baseline['annual_ac_kwh'])
    if baseline['gain_of_best_percent'] is not None:
        number(baseline['gain_of_best_percent'], -100)
    grid = report['search']['coarse_grid']
    step = report['search']['coarse_step_deg']
    if step not in (5, 10, 15, 30):
        raise ValueError('Invalid coarse step')
    if grid['tilt_deg'] != list(range(0, 91, step)) or grid['azimuth_deg'] != list(range(0, 360, step)):
        raise ValueError('Coarse axes do not match search resolution')
    if len(grid['annual_ac_kwh']) != len(grid['tilt_deg']):
        raise ValueError('Invalid heatmap row count')
    for row in grid['annual_ac_kwh']:
        if len(row) != len(grid['azimuth_deg']):
            raise ValueError('Invalid heatmap column count')
        for value in row:
            number(value, 0, best['annual_ac_kwh'] * (1 + 1e-10))
    if not isinstance(report['site']['name'], str):
        raise ValueError('Site name must be text')
    return report


def heatmap(report, section_id):
    grid, best = report['search']['coarse_grid'], report['best']
    tilts, azimuths, rows = grid['tilt_deg'], grid['azimuth_deg'], grid['annual_ac_kwh']
    width, height = 720 / len(azimuths), 240 / len(tilts)
    cells, table_rows = [], []
    for i, (tilt, row) in enumerate(zip(tilts, rows)):
        table_rows.append(f'<tr><th scope="row">{tilt}°</th>' + ''.join(f'<td>{e:.1f}</td>' for e in row) + '</tr>')
        for j, (azimuth, energy) in enumerate(zip(azimuths, row)):
            ratio = energy / best['annual_ac_kwh']
            color = f'hsl({round(220 - 170 * ratio)},75%,{round(25 + 30 * ratio)}%)'
            title = f'Tilt {tilt}°, azimuth {azimuth}°: {energy:.1f} kWh ({ratio * 100:.1f}% of best)'
            cells.append(f'<rect x="{60+j*width:.3f}" y="{25+i*height:.3f}" width="{width:.3f}" '
                         f'height="{height:.3f}" fill="{color}"><title>{title}</title></rect>')
    x = 60 + (best['azimuth_deg'] / report['search']['coarse_step_deg'] + 0.5) * width
    y = 25 + (best['tilt_deg'] / report['search']['coarse_step_deg'] + 0.5) * height
    x = min(x, 779)
    svg = (f'<svg viewBox="0 0 820 320" role="img" aria-labelledby="{section_id}-map-title">'
           f'<title id="{section_id}-map-title">Annual AC energy heatmap; numeric table follows. '
           'Tilt increases downward, azimuth increases rightward.</title>' + ''.join(cells) +
           f'<circle cx="{x:.3f}" cy="{y:.3f}" r="5" fill="none" stroke="white" stroke-width="2"/>'
           '<text x="8" y="34">0°</text><text x="8" y="264">90°</text>'
           '<text x="60" y="288">N 0°</text><text x="240" y="288">E 90°</text>'
           '<text x="420" y="288">S 180°</text><text x="600" y="288">W 270°</text>'
           '<text x="250" y="312">Azimuth clockwise from true north</text></svg>')
    table = ('<details><summary>Accessible heatmap data (annual AC kWh)</summary><div class="scroll" tabindex="0">'
             '<table><caption>Tilt rows × azimuth columns (degrees)</caption><thead><tr><th scope="col">Tilt</th>' +
             ''.join(f'<th scope="col">{a}°</th>' for a in azimuths) + '</tr></thead><tbody>' +
             ''.join(table_rows) + '</tbody></table></div></details>')
    return (svg + '<p>Blue = lower energy; yellow = higher. White ring = best sampled orientation. '
            'Coarse grid only; refinement is not interpolated. Tilt is from horizontal.</p>' + table)


def render_site(report, index):
    validate_report(report)
    sid = f'site-{index}'
    site, best = report['site'], report['best']
    baseline = report['baselines']['30_degrees_south']
    gain = baseline['gain_of_best_percent']
    gain_text = f'{gain:.3f}%' if gain is not None else 'undefined (zero baseline)'
    monthly = ''.join(f'<tr><th scope="row">{calendar.month_name[m]}</th>'
                      f'<td>{best["monthly_ac_kwh"][str(m)]:.1f}</td></tr>' for m in range(1, 13))
    timing = report.get('timing_sensitivity')
    comparison = '<p>Timing sensitivity was not requested for this report.</p>'
    if timing:
        old = timing['zero_offset_best']
        for key in ('tilt_deg', 'azimuth_deg', 'annual_ac_kwh'):
            number(old[key])
        delta = number(timing['best_energy_change_kwh'], -float('inf'))
        comparison = (f'<p>Same-weather zero-offset optimum: {old["tilt_deg"]:g}° tilt, '
                      f'{old["azimuth_deg"]:g}° azimuth; {old["annual_ac_kwh"]:.1f} kWh. '
                      f'Corrected minus zero-offset best energy: {delta:+.2f} kWh.</p>'
                      f'<p>{escape(str(timing["note"]))}</p>')
    limitations = ''.join(f'<li>{escape(str(item))}</li>' for item in report['assumptions_and_limitations'])
    provenance = escape(json.dumps({'weather': report['weather_source'], 'system': report['system'],
                                    'software': report['software'], 'timing': report['timing']}, indent=2))
    return (f'<section id="{sid}"><h2>{escape(site["name"])}</h2>'
            f'<p>{site["latitude"]:.4f}° N, {site["longitude"]:.4f}° E · '
            f'{report["system"]["dc_capacity_kw"]:g} kWp DC · '
            f'Generated {escape(str(report["generated_at_utc"]))}</p>'
            '<div class="cards">'
            f'<div><h3>Best sampled tilt</h3><strong>{best["tilt_deg"]:g}°</strong><p>From horizontal</p></div>'
            f'<div><h3>Best sampled azimuth</h3><strong>{best["azimuth_deg"]:g}°</strong><p>South = 180°</p></div>'
            f'<div><h3>Modeled annual AC</h3><strong>{best["annual_ac_kwh"]:.1f} kWh</strong>'
            f'<p>{best["specific_yield_kwh_per_kwp"]:.1f} kWh/kWp</p></div></div>'
            f'<p>30° south baseline: {baseline["annual_ac_kwh"]:.1f} kWh. Gain of best: <b>{gain_text}</b>. '
            'Small gains may be outweighed by model/weather uncertainty and installation constraints.</p>'
            '<h3>Orientation energy heatmap</h3>' + heatmap(report, sid) +
            '<p>Sampled alternatives within 1% of the maximum are in the JSON report; '
            'they are not confidence bounds or continuous angle ranges.</p>'
            '<details><summary>Monthly AC energy</summary><table><caption>Nominal UTC calendar months</caption>'
            '<thead><tr><th scope="col">Month</th><th scope="col">kWh</th></tr></thead>'
            f'<tbody>{monthly}</tbody></table></details><h3>Irradiance timing</h3>'
            f'<p>Solar geometry offset: {report["timing"]["irradiance_time_offset_hours"]:g} hours. '
            'Weather rows and hourly/monthly accounting are unchanged.</p>' + comparison +
            f'<details><summary>Assumptions and limitations</summary><ul>{limitations}</ul></details>'
            f'<details><summary>Weather provenance and model configuration</summary><pre>{provenance}</pre></details>'
            '</section>')


def icon_png(size):
    if size not in (180, 192, 512):
        raise ValueError('Unsupported icon size')
    return resources.files('solarna').joinpath(
        'web', f'icon-{size}.png').read_bytes()


def build_artifacts(reports):
    if not reports:
        raise ValueError('No JSON reports found')
    sections = ''.join(render_site(report, i) for i, report in enumerate(reports))
    navigation = ' · '.join(f'<a href="#site-{i}">{escape(r["site"]["name"])}</a>'
                            for i, r in enumerate(reports))
    html = ('''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0e2331"><meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="Solarna"><link rel="manifest" href="manifest.webmanifest">
<link rel="apple-touch-icon" sizes="180x180" href="icon-180.png"><title>Solarna · fixed PV reports</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#edf3f6;color:#102737;font:16px/1.55 system-ui,sans-serif}
main{max-width:1080px;margin:auto;padding:16px}header,section{background:white;padding:clamp(16px,4vw,32px);border-radius:16px;margin:16px 0}
h1,h2,h3{line-height:1.2}a{color:#005a83}a:focus-visible,summary:focus-visible{outline:3px solid #ac6600}
nav a{display:inline-block;padding:10px 6px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.cards>div{padding:16px;background:#edf3f6;border-radius:12px}.cards strong{font-size:1.7rem}
svg{width:100%;height:auto;background:#f4f7fa}svg text{font:13px sans-serif;fill:#102737}
summary{cursor:pointer;padding:14px 0;font-weight:600}table{border-collapse:collapse;width:100%}
th,td{padding:8px;border-bottom:1px solid #ccd7df;text-align:right}th:first-child{text-align:left}
.scroll{overflow-x:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:.85rem}
.notice{border-left:4px solid #b47b00;padding-left:12px}section{scroll-margin-top:12px}
</style></head><body><main><header><h1>Solarna</h1><p>Fixed PV orientation · Tunisia research prototype</p>
<p class="notice">Modeled typical-year energy, not a forecast or a field-validated installation recommendation.
These reports do not model your roof, nearby obstacles or structural constraints.</p><nav aria-label="Sites">''' + navigation +
            '''</nav><p><a href="reports.json">Full JSON reports and sampled alternatives</a></p>
<details><summary>Later on your iPhone</summary><p>Host this folder over HTTPS, open it in Safari,
then use Share → Add to Home Screen (enable Open as Web App if offered). This is a read-only report,
not a native iOS app or an on-device optimizer. No offline cache is provided yet; device installation
and Safari rendering still require testing. No location permission is needed.</p></details></header>''' +
            sections + '</main></body></html>')
    manifest = {'name': 'Solarna PV Reports', 'short_name': 'Solarna', 'id': './',
                'start_url': './index.html', 'scope': './', 'display': 'standalone',
                'background_color': '#edf3f6', 'theme_color': '#0e2331',
                'icons': [{'src': f'icon-{size}.png', 'sizes': f'{size}x{size}',
                           'type': 'image/png', 'purpose': 'any'} for size in (192, 512)]}
    artifacts = {'index.html': html.encode('utf-8'),
                 'manifest.webmanifest': json.dumps(manifest, indent=2).encode('utf-8'),
                 'reports.json': json.dumps(reports, indent=2, allow_nan=False).encode('utf-8')}
    artifacts.update({f'icon-{size}.png': icon_png(size) for size in (180, 192, 512)})
    return artifacts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, default=Path('outputs'))
    parser.add_argument('--output', type=Path, default=Path('outputs/web'))
    parser.add_argument('--check', action='store_true', help='Read-only: verify artifacts exactly match source reports')
    args = parser.parse_args(argv)
    try:
        if args.reports.resolve() == args.output.resolve():
            raise ValueError('Reports and dashboard output must be different directories')
        reports = [json.loads(path.read_text(encoding='utf-8')) for path in sorted(args.reports.glob('*.json'))]
        artifacts = build_artifacts(reports)
        if args.check:
            for name, contents in artifacts.items():
                if (args.output / name).read_bytes() != contents:
                    raise ValueError(f'Artifact is stale or modified: {name}')
            print(f'Verified {len(reports)} report(s) and all {len(artifacts)} dashboard artifacts.')
        else:
            args.output.mkdir(parents=True, exist_ok=True)
            for name, contents in artifacts.items():
                (args.output / name).write_bytes(contents)
            print(f'Built {args.output / "index.html"} from {len(reports)} report(s). No deployment performed.')
        for report in reports:
            best = report['best']
            print(f'{report["site"]["name"]}: {best["tilt_deg"]:g}° tilt / {best["azimuth_deg"]:g}° azimuth; '
                  f'{best["annual_ac_kwh"]:.2f} kWh; offset {report["timing"]["irradiance_time_offset_hours"]:g} h')
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f'Dashboard failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
