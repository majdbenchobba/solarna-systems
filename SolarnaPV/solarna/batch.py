"""Sequential, explicitly requested CSV site batches; no nationwide auto-download."""

import argparse
import csv
import math
from pathlib import Path
import re
import sys
import time

from .engine import Site, System
from .reporting import build_report, write_report
from .weather import load_tmy


def read_sites(path):
    with Path(path).open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        fields = ['id', 'name', 'latitude', 'longitude', 'altitude_m']
        if reader.fieldnames != fields:
            raise ValueError('CSV header must be: ' + ','.join(fields))
        rows = list(reader)
    if not 1 <= len(rows) <= 200:
        raise ValueError('Provide between 1 and 200 sites per batch')
    sites, seen = [], set()
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError('Malformed CSV row')
        key = row['id']
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', key) or key in seen:
            raise ValueError('Site IDs must be unique safe lowercase slugs')
        # Prefix filenames so Windows reserved names such as con are also safe.
        seen.add(key)
        if not row['name'].strip():
            raise ValueError('Site name cannot be blank')
        site = Site(float(row['latitude']), float(row['longitude']),
                    float(row['altitude_m']), row['name'].strip())
        # Broad regional bounds, not a political-border or roof-location check.
        if not (30 <= site.latitude <= 38 and 7 <= site.longitude <= 12):
            raise ValueError('Site outside the supported Tunisia regional bounding box')
        sites.append((key, site))
    return sites


def run_batch(sites, output, cache_dir, pause_seconds=1.0, coarse_step=5,
              timing_sensitivity=False):
    if not math.isfinite(pause_seconds) or pause_seconds < 1:
        raise ValueError('Pause must be at least one second')
    failures = []
    for index, (key, site) in enumerate(sites):
        if index:
            time.sleep(pause_seconds)
        try:
            print(f'[{index + 1}/{len(sites)}] {site.name}', flush=True)
            weather, provenance = load_tmy(site, cache_dir)
            report = build_report(weather, provenance, site, System(), coarse_step,
                                  timing_sensitivity=timing_sensitivity)
            write_report(report, Path(output) / f'site-{key}.json')
        except (OSError, ValueError, KeyError, TypeError) as exc:
            failures.append(key)
            print(f'FAILED {key}: {exc}. Any older report is unchanged and may be stale.', file=sys.stderr)
    return failures


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sites', required=True, type=Path)
    parser.add_argument('--output', type=Path, default=Path('outputs/tunisia'))
    parser.add_argument('--cache-dir', type=Path, default=Path('.cache/pvgis'))
    parser.add_argument('--pause-seconds', type=float, default=1.0)
    parser.add_argument('--coarse-step', type=int, choices=[5, 10, 15, 30], default=5)
    parser.add_argument('--timing-sensitivity', action='store_true')
    args = parser.parse_args(argv)
    try:
        sites = read_sites(args.sites)  # Validate every row before any network access.
        failed = run_batch(sites, args.output, args.cache_dir, args.pause_seconds,
                           args.coarse_step, args.timing_sensitivity)
    except (OSError, ValueError, TypeError) as exc:
        print(f'Batch rejected: {exc}', file=sys.stderr)
        return 1
    print(f'Batch finished: {len(sites) - len(failed)} succeeded, {len(failed)} failed.')
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
