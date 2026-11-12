"""Download public source material only; never execute downloaded content."""

import hashlib
import json
import math
import sys
import zipfile
from pathlib import Path

import requests
from pyproj import Transformer

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / '.cache' / 'fault_kinematic_downloads'


def fetch(url, name, expected=None):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / name
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    if expected == 'zip' and not response.content.startswith(b'PK'):
        raise ValueError(f'Expected ZIP, received {response.headers.get("Content-Type")}')
    path.write_bytes(response.content)
    record = {
        'url': url, 'resolved_url': response.url, 'cache_file': name,
        'bytes': len(response.content),
        'sha256': hashlib.sha256(response.content).hexdigest(),
        'accessed_date': '2026-11-12',
    }
    print(name, record['bytes'], flush=True)
    return path, record


def main():
    if '--terrain' in sys.argv:
        records = []
        for crs, bounds in [
            (28350, (535000, 7485000, 555000, 7505000)),
            (28353, (595000, 8185000, 615000, 8205000)),
        ]:
            transform = Transformer.from_crs(crs, 4326, always_xy=True)
            corners = [transform.transform(x, y) for x in bounds[::2] for y in bounds[1::2]]
            def tile(lon, lat):
                return (int((lon + 180) / 360 * 2048),
                        int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * 2048))
            coords = [tile(*c) for c in corners]
            for x in range(min(c[0] for c in coords), max(c[0] for c in coords) + 1):
                for y in range(min(c[1] for c in coords), max(c[1] for c in coords) + 1):
                    name = f'terrain_11_{x}_{y}.tif'
                    _, record = fetch(
                        f'https://elevation-tiles-prod.s3.amazonaws.com/geotiff/11/{x}/{y}.tif', name)
                    record['target_epsg'] = crs
                    records.append(record)
        (CACHE / 'terrain_records.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
        return
    item_url = 'https://geoscience.nt.gov.au/gemis/server/api/pid/find?id=1/81583'
    item_path, item_record = fetch(item_url, 'nt_item.json')
    item = json.loads(item_path.read_text(encoding='utf-8'))
    bundles = requests.get(item['_links']['bundles']['href'], timeout=60).json()
    bundle = next(b for b in bundles['_embedded']['bundles'] if b['name'] == 'ORIGINAL')
    streams = requests.get(bundle['_links']['bitstreams']['href'], timeout=60).json()
    stream = next(b for b in streams['_embedded']['bitstreams']
                  if b['name'] == 'McArthurRvrGeol100kM.zip')
    _, zip_record = fetch(stream['_links']['content']['href'], stream['name'], 'zip')
    extracted = CACHE / 'nt_extracted'
    extracted.mkdir(exist_ok=True)
    with zipfile.ZipFile(CACHE / stream['name']) as archive:
        for member in archive.infolist():
            target = (extracted / member.filename).resolve()
            if not target.is_relative_to(extracted.resolve()):
                raise ValueError('Unsafe archive member')
            if not member.is_dir():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(member))
    _, attribution = fetch(
        'https://raw.githubusercontent.com/tilezen/joerd/master/docs/attribution.md',
        'terrain_attribution.md',
    )
    (CACHE / 'download_records.json').write_text(
        json.dumps([item_record, zip_record, attribution], indent=2), encoding='utf-8')


if __name__ == '__main__':
    main()
