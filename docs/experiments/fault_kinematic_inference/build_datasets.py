"""Build small fault-inference datasets without using the inference forward model."""

import argparse
import hashlib
import importlib.metadata
import json
import shutil
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import rasterio
from pyogrio.raw import read as read_vector
from rasterio.merge import merge
from rasterio.transform import from_bounds
from rasterio.warp import reproject, Resampling
from shapely import STRtree, from_wkb, make_valid
from shapely.geometry import LineString, Point, box, mapping, shape
from shapely.ops import linemerge, unary_union
from skimage.measure import find_contours

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
CACHE = ROOT / '.cache' / 'fault_kinematic_downloads'
OUT = BASE / 'datasets'
SEED = 20261112


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(clean(obj), indent=2, allow_nan=False) + '\n', encoding='utf-8')


def collection(path, features, epsg=None):
    obj = {'type': 'FeatureCollection', 'features': features}
    obj['crs'] = {'type': 'name', 'properties': {
        'name': f'EPSG:{epsg}' if epsg else 'LOCAL_CARTESIAN_METRES'}}
    write_json(path, obj)


def feature(geom, props):
    return {'type': 'Feature', 'geometry': mapping(geom), 'properties': clean(props)}


def parts(geom, kind):
    if geom.is_empty:
        return []
    if geom.geom_type == kind:
        return [geom]
    if hasattr(geom, 'geoms'):
        return [g for child in geom.geoms for g in parts(child, kind)]
    return []


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_raster(path, values, bounds, epsg=None):
    with rasterio.open(path, 'w', driver='GTiff', height=values.shape[0],
                       width=values.shape[1], count=1, dtype='float32',
                       transform=from_bounds(*bounds, values.shape[1], values.shape[0]),
                       crs=f'EPSG:{epsg}' if epsg else None, nodata=-9999,
                       compress='deflate') as dst:
        dst.write(np.where(np.isfinite(values), values, -9999).astype('float32'), 1)
        dst.update_tags(vertical_units='metres', sample_location='pixel centre')


def pixel_grid(bounds, n=201):
    left, bottom, right, top = bounds
    dx, dy = (right-left)/n, (top-bottom)/n
    return np.meshgrid(left+(np.arange(n)+0.5)*dx, top-(np.arange(n)+0.5)*dy)


def terrain(x, y):
    return 200 + 0.015*x + 0.02*y + 35*np.sin(x/850)*np.cos(y/1100)


PROFILE_Y = np.linspace(-1800, 1800, 10001)
PROFILE_SCALE = np.max((1-(PROFILE_Y/1800)**2)**2*(1+0.4*PROFILE_Y/1800))


def profile(y):
    u = y/1800
    return np.where(np.abs(u) < 1, (1-u*u)**2*(1+0.4*u)/PROFILE_SCALE, 0.0)


def restored(case, x, y, z):
    positive = x > 0
    if case == 1:
        return x, y-positive*150, z+positive*100
    if case == 2:
        y0 = np.array(y, dtype=float, copy=True)
        for _ in range(45):
            y0 = y-positive*120*profile(y0)
        return x, y0, z+positive*180*profile(y0)
    return x, y, z-positive*100


def field(case, x, y, z):
    x0, y0, z0 = restored(case, x, y, z)
    if case == 1:
        return z0 + 0.35*x0 + 0.2*y0
    return z0 + 0.35*x0 + 0.2*y0 + 300*np.sin(y0/700) + 90*np.sin(x0/800)


def normals(case, x, y, z):
    h = 0.05
    args = [x, y, z]
    grad = []
    for j in range(3):
        plus, minus = list(args), list(args)
        plus[j], minus[j] = args[j]+h, args[j]-h
        grad.append((field(case, *plus)-field(case, *minus))/(2*h))
    v = np.column_stack(grad)
    return v / np.linalg.norm(v, axis=1)[:, None]


def add_splits(path, contacts, bedding, bounds, buffer):
    """Spatial bands, with a gap around each held-out region in every point layer."""
    edges = np.linspace(bounds[1], bounds[3], 6)
    records = []
    for k, (lo, hi) in enumerate(zip(edges[:-1], edges[1:])):
        target = path / 'splits' / f'fold_{k}'
        target.mkdir(parents=True, exist_ok=True)
        for name, table in [('contacts', contacts), ('bedding', bedding)]:
            test = (table.Y >= lo) & ((table.Y < hi) if k < 4 else (table.Y <= hi))
            train = (table.Y < lo-buffer) | (table.Y > hi+buffer)
            table.loc[train].to_csv(target/f'{name}_train.csv', index=False)
            table.loc[test].to_csv(target/f'{name}_test.csv', index=False)
            records.append({'fold': k, 'layer': name, 'train': int(train.sum()),
                            'test': int(test.sum()), 'buffer_excluded': int((~train & ~test).sum())})
        write_json(target/'mask.json', {'test_y_interval_m': [lo, hi], 'buffer_m': buffer,
                   'apply_to': ['all contact, map polygon and bedding evidence',
                                'all derived matches and thickness estimates'],
                   'known_fault_geometry_may_remain_conditioning': True,
                   'source_and_truth_files_are_not_blind_training_inputs': True})
    pd.DataFrame(records).to_csv(path/'splits'/'counts.csv', index=False)


def preview(path, title, bounds, polygons, traces, faults, bedding, xx, yy, zz):
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.pcolormesh(xx/1000, yy/1000, zz, cmap='Greys', alpha=0.3, shading='auto', rasterized=True)
    colours = plt.get_cmap('tab20')
    polygon_keys=sorted({str(f['properties'].get('code',f['properties'].get('Symbol','unknown')))
                         for f in polygons})
    for k, f in enumerate(polygons):
        unit=str(f['properties'].get('code',f['properties'].get('Symbol','unknown')))
        for polygon in parts(shape(f['geometry']), 'Polygon'):
            xy = np.array(polygon.exterior.coords)/1000
            ax.fill(xy[:, 0], xy[:, 1], color=colours(polygon_keys.index(unit) % 20), alpha=0.3)
    trace_keys=sorted({str(f['properties'].get('contact_id','unknown')) for f in traces})
    for k, f in enumerate(traces):
        contact=str(f['properties'].get('contact_id','unknown'))
        for line in parts(shape(f['geometry']), 'LineString'):
            xy = np.array(line.coords)/1000
            ax.plot(xy[:, 0], xy[:, 1], color=colours(trace_keys.index(contact) % 20), lw=1.1)
    for f in faults:
        for line in parts(shape(f['geometry']), 'LineString'):
            xy = np.array(line.coords)/1000
            ax.plot(xy[:, 0], xy[:, 1], 'k-', lw=2)
    if len(bedding):
        ax.scatter(bedding.X/1000, bedding.Y/1000, s=12, marker='+', c='darkblue', label='Bedding')
    for y in np.linspace(bounds[1], bounds[3], 6)[1:-1]:
        ax.axhline(y/1000, color='grey', lw=0.7, ls='--')
    ax.set(xlim=(bounds[0]/1000, bounds[2]/1000), ylim=(bounds[1]/1000, bounds[3]/1000),
           xlabel='Easting / local x (km)', ylabel='Northing / local y (km)', title=title)
    ax.set_aspect('equal')
    ax.text(0, -0.14, 'Black: faults   Blue +: bedding   Dashed: validation block boundaries',
            transform=ax.transAxes, fontsize=8)
    fig.tight_layout()
    fig.savefig(path/'preview.png', dpi=150)
    plt.close(fig)


def synthetic(case):
    labels = {1: ('synthetic_01_parallel_markers', 'Parallel markers: unresolved slip direction'),
              2: ('synthetic_02_variable_slip', 'Folded markers and asymmetric variable slip'),
              3: ('synthetic_03_reactivation', 'Reactivation: two histories, one net offset')}
    name, title = labels[case]
    path = OUT/name
    path.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED+case)
    bounds = [-2000, -2000, 2000, 2000]
    xx, yy = pixel_grid(bounds, 401)
    zz = terrain(xx, yy)
    save_raster(path/'dem.tif', zz, bounds)
    surface_field = field(case, xx, yy, zz)
    levels = [-400, -150, 100, 350, 600, 850]
    traces, contacts = [], []
    for wall in [-1, 1]:
        image = surface_field.copy()
        image[wall*xx < 5] = np.nan
        for level in levels:
            for j, rc in enumerate(find_contours(image, level)):
                x = bounds[0]+(rc[:, 1]+0.5)*(bounds[2]-bounds[0])/401
                y = bounds[3]-(rc[:, 0]+0.5)*(bounds[3]-bounds[1])/401
                line = LineString(np.c_[x, y])
                if line.length < 150:
                    continue
                group = f'contact_{level}_wall_{wall}_trace_{j}'
                traces.append(feature(line, {'contact_id': f'C{level}', 'val': level,
                                              'source_group': group, 'wall': wall}))
                for distance in np.arange(40, line.length, 80):
                    p = line.interpolate(distance)
                    if abs(p.x) < 40:
                        continue
                    xobs, yobs = np.array([p.x, p.y])+rng.normal(0, 10, 2)
                    contacts.append({'observation_id': f'C{len(contacts):05d}',
                        'X': xobs, 'Y': yobs, 'Z': terrain(xobs, yobs),
                        'contact_id': f'C{level}', 'feature_name': 'stratigraphy',
                        'val': level, 'source_group': group, 'wall': wall,
                        'position_sigma_m': 10, 'evidence_kind': 'synthetic_contact'})
    contacts = pd.DataFrame(contacts)
    # Original analytic contact geometry is truth, not additional conditioning data.
    collection(path/'truth'/'contact_traces.geojson', traces)
    observed_traces = []
    for group, rows in contacts.groupby('source_group', sort=False):
        if len(rows) >= 2:
            observed_traces.append(feature(LineString(rows[['X','Y']].to_numpy()),
                {'source_group': group, 'contact_id': rows.contact_id.iloc[0]}))
    collection(path/'contact_traces.geojson', observed_traces)
    contacts.to_csv(path/'contacts.csv', index=False)
    x = rng.uniform(-1850, 1850, 100)
    x[np.abs(x) < 60] += 100
    y = rng.uniform(-1900, 1900, 100)
    z = terrain(x, y)
    true_normal = normals(case, x, y, z)
    noisy = true_normal+rng.normal(0, np.deg2rad(3), true_normal.shape)
    noisy /= np.linalg.norm(noisy, axis=1)[:, None]
    bedding = pd.DataFrame({'observation_id': [f'B{i:04d}' for i in range(len(x))],
        'X': x, 'Y': y, 'Z': z, 'nx': noisy[:,0], 'ny': noisy[:,1], 'nz': noisy[:,2],
        'orientation_sigma_degrees': 3, 'source_group': [f'bedding_{i}' for i in range(len(x))],
        'evidence_kind': 'synthetic_bedding'})
    bedding.to_csv(path/'bedding.csv', index=False)
    np.savez_compressed(path/'truth'/'fields.npz', x=xx, y=yy, z=zz, scalar=surface_field,
                        bedding_normals=true_normal)
    fault_end = 1800 if case == 2 else 2000
    faults = [feature(LineString([(0,-fault_end),(0,fault_end)]),
        {'fault_id': 'F1', 'geometry': 'vertical plane x=0',
         'endpoint_meaning': 'true slip tips' if case == 2 else 'window boundary; not a tip'})]
    collection(path/'faults.geojson', faults)
    truth = {'case': case, 'seed': SEED+case, 'fault_plane': 'x=0',
             'positive_wall': 'x>0; hanging wall is not unique for the vertical limiting geometry',
             'forward_slip_convention': 'positive wall relative to negative wall',
             'base_field': 'z0 + 0.35*x0 + 0.2*y0' +
                 ('' if case == 1 else ' + 300*sin(y0/700) + 90*sin(x0/800)'),
             'terrain': '200 + .015*x + .02*y + 35*sin(x/850)*cos(y/1100)',
             'contact_levels': levels, 'generator': 'independent analytic coordinate transformation; no LoopStructural interpolation'}
    if case == 1:
        truth.update(forward_slip_m=[0,150,-100], magnitude_m=float(np.hypot(150,100)),
                     pitch_degrees=float(np.degrees(np.arctan2(100,150))),
                     expected_identifiability='parallel marker normals constrain only 0.2*a-b; repeated contacts do not add an independent direction')
    elif case == 2:
        truth.update(forward_slip_m='[0,120*g(y0),-180*g(y0)]',
            profile='g(y0)=max(0,1-(y0/1800)^2)^2*(1+0.4*y0/1800)/normalisation within |y0|<1800; zero outside',
            profile_normalisation=PROFILE_SCALE, maximum_magnitude_m=float(np.hypot(120,180)),
            pitch_degrees=float(np.degrees(np.arctan2(180,120))),
            expected_identifiability='varying marker orientations can constrain shared direction/profile; confidence remains conditional on stratigraphic model')
    else:
        truth.update(events_oldest_first=[{'forward_slip_m':[0,0,300]}, {'forward_slip_m':[0,0,-200]}],
            net_forward_slip_m=[0,0,100], equivalent_single_event_m=[0,0,100],
            expected_identifiability='base observations all predate both events; history cannot be separated from net slip')
        # An optional intermediate-age horizon: currently z + 200 + .15*x + .1*y = 200.
        xd = np.linspace(-1200,1200,121)
        yd = np.zeros_like(xd)
        zd = 200-.15*xd-(xd>0)*200
        pd.DataFrame({'X':xd,'Y':yd,'Z':zd,'horizon_id':'intermediate_age_marker',
                      'observation_kind':'optional subsurface/section diagnostic; NOT surface-map input',
                      'position_sigma_m':10}).to_csv(path/'truth'/'optional_intermediate_marker.csv',index=False)
        truth['optional_diagnostic'] = 'truth/optional_intermediate_marker.csv is deliberately not part of the surface dataset'
    write_json(path/'truth'/'parameters.json', truth)
    write_json(path/'constraints.json', {
        'E0': {'status':'ready', 'fault_geometry':'known vertical plane',
               'pitch':'unconstrained', 'amplitude_prior_m':[0,600],
               'note':'all constraints refer to the net event unless explicitly scoped'},
        'E1': {'status':'hypothetical expert input for a controlled experiment',
               'slip_direction': ([0,150,-100] if case == 1 else
                                  'pitch 50-65 degrees' if case == 2 else 'net upward motion of the x>0 wall'),
               'source':'synthetic independent expert knowledge, not inferred from contacts',
               'fault_endpoints':'true tips' if case == 2 else 'window edges, continuation unknown'},
        'agent_access': 'Use observations, constraints and training split only; truth directory is evaluator-only.'})
    add_splits(path, contacts, bedding, bounds, 150)
    preview(path, title, bounds, [], observed_traces, faults, bedding, xx, yy, zz)
    manifest = {'dataset_id':name, 'title':title, 'kind':'synthetic', 'seed':SEED+case,
        'horizontal_crs':'local Cartesian metres; not a geographic location', 'bounds_xy_m':bounds,
        'vertical_datum':'synthetic local height, metres', 'noise':{'contact_xy_sigma_m':10,
        'bedding_noise':'isotropic Gaussian perturbation of unit normals, 3 degrees component scale; approximate angular error'},
        'contact_count':len(contacts), 'bedding_count':len(bedding), 'fault_count':1,
        'validation':'five y-strips with 150 m training exclusion buffer; no inference has been run',
        'licence':'synthetic data and generator follow the repository MIT licence',
        'truth_access':'Evaluator only; never include truth files in agent/inference context.'}
    write_json(path/'manifest.json', manifest)
    return manifest


def read_json_features(path, bounds):
    obj = json.loads(path.read_text(encoding='utf-8'))
    clip = box(*bounds)
    result = []
    for f in obj['features']:
        g = make_valid(shape(f['geometry'])).intersection(clip)
        if not g.is_empty:
            result.append(feature(g, f['properties']))
    return result


def read_tab(path, bounds):
    meta, ids, wkbs, columns = read_vector(path, bbox=tuple(bounds), return_fids=True)
    result = []
    for j, wkb in enumerate(wkbs):
        g = make_valid(from_wkb(wkb)).intersection(box(*bounds))
        if not g.is_empty:
            props = {k: v[j] for k,v in zip(meta['fields'],columns)}
            props['source_fid'] = int(ids[j])
            result.append(feature(g,props))
    return result


def real_dem(path, bounds, epsg):
    records = json.loads((CACHE/'terrain_records.json').read_text(encoding='utf-8'))
    sources = [r for r in records if r['target_epsg']==epsg]
    datasets = [rasterio.open(CACHE/r['cache_file']) for r in sources]
    try:
        mosaic, transform = merge(datasets, nodata=-9999)
        n = 401
        dem = np.full((n,n), -9999, dtype='float32')
        reproject(mosaic[0], dem, src_transform=transform, src_crs=datasets[0].crs,
                  dst_transform=from_bounds(*bounds,n,n),dst_crs=f'EPSG:{epsg}',
                  src_nodata=-9999,dst_nodata=-9999,resampling=Resampling.bilinear)
    finally:
        for d in datasets:d.close()
    if np.any(dem == -9999):
        raise ValueError('Incomplete DEM coverage')
    save_raster(path/'dem.tif', dem, bounds,epsg)
    return dem,sources


def sample_dem(path, x, y):
    with rasterio.open(path/'dem.tif') as d:
        return np.array([v[0] for v in d.sample(zip(x,y))])


def real_dataset(region):
    wa = region=='hamersley'
    name = 'real_01_hamersley' if wa else 'real_02_mcarthur_river'
    title = 'GSWA Hamersley / Rocklea window' if wa else 'NTGS McArthur River / Batten window'
    path=OUT/name;path.mkdir(parents=True,exist_ok=True)
    bounds=[535000,7485000,555000,7505000] if wa else [595000,8185000,615000,8205000]
    epsg=28350 if wa else 28353
    if wa:
        source=ROOT/'packages/map2loop/src/map2loop/_datasets/geodata_files/hamersley'
        polygons=read_json_features(source/'geology.geojson',bounds)
        faults=read_json_features(source/'faults.geojson',bounds)
        structures=read_json_features(source/'structures.geojson',bounds)
        source_records=[{'repository_path':str((source/f).relative_to(ROOT)).replace('\\','/'),
                         'sha256':digest(source/f),'bytes':(source/f).stat().st_size}
                        for f in ['geology.geojson','faults.geojson','structures.geojson']]
    else:
        source=CACHE/'nt_extracted'
        polygons=read_tab(source/'MCRR_LithOutcrop_100K.TAB',bounds)
        faults=read_tab(source/'MCRR_Fault_100K.TAB',bounds)
        structures=read_tab(source/'MCRR_StructData_100K.TAB',bounds)
        source_records=json.loads((CACHE/'download_records.json').read_text(encoding='utf-8'))[:2]
        write_json(path/'source_catalogue_metadata.json',json.loads((CACHE/'nt_item.json').read_text(encoding='utf-8')))
    for j,f in enumerate(faults):
        f['properties']['fault_id']=f'F{j:03d}'
    collection(path/'geology.geojson',polygons,epsg)
    collection(path/'faults.geojson',faults,epsg)
    collection(path/'source_structures.geojson',structures,epsg)
    dem,terrain_sources=real_dem(path,bounds,epsg)
    rows=[]
    for j,f in enumerate(structures):
        p=f['properties'];g=shape(f['geometry'])
        try:
            dip=float(p['dip'] if wa else p['Dip'])
            az_raw=float(p['azimuth2'] if wa else p['DipDirection'])
        except (KeyError,ValueError,TypeError):continue
        if not 0<=dip<=90:continue
        if not 0<=az_raw<=(720 if wa else 360):continue
        az=az_raw%360
        description=str(p.get('feature','') if wa else p.get('ObsType',''))
        if 'bed' not in description.lower():continue
        rad,dd=np.deg2rad([dip,az])
        rows.append({'observation_id':f'B{j:04d}','X':g.x,'Y':g.y,
                     'dip_degrees':dip,'dip_direction_degrees':az,
                     'nx':np.sin(rad)*np.sin(dd),'ny':np.sin(rad)*np.cos(dd),'nz':np.cos(rad),
                     'source_group':str(p.get('gml_id',p.get('ID',j))),
                     'orientation_sigma_degrees':10,'uncertainty_status':'assumed benchmark value; not survey-certified',
                     'evidence_kind':'survey_bedding','polarity':'not established from these attributes'})
    bedding=pd.DataFrame(rows)
    bedding['Z']=sample_dem(path,bedding.X,bedding.Y)
    bedding.to_csv(path/'bedding.csv',index=False)
    # Shared polygon edges identify unit pairs, not automatically correlatable basal contacts.
    faults_geom=unary_union([shape(f['geometry']) for f in faults])
    fault_exclusion=faults_geom.buffer(50)
    margin=box(*bounds).boundary.buffer(5)
    traces=[]
    geometries=[shape(f['geometry']) for f in polygons]
    geometry_tree=STRtree(geometries)
    unit_key='code' if wa else 'Symbol'
    for i,a in enumerate(geometries):
        for j in sorted(geometry_tree.query(a, predicate='intersects')):
            if j<=i:continue
            ua=polygons[i]['properties'].get(unit_key,'unknown')
            ub=polygons[j]['properties'].get(unit_key,'unknown')
            if ua==ub:continue
            shared=a.boundary.intersection(geometries[j].boundary)
            shared=shared.difference(fault_exclusion).difference(margin)
            line_parts=parts(shared,'LineString')
            if line_parts:
                shared=linemerge(line_parts)
            for k,line in enumerate(parts(shared,'LineString')):
                if line.length<120:continue
                cid='__'.join(sorted([str(ua),str(ub)]))
                traces.append(feature(line,{'contact_id':cid,'unit_a':ua,'unit_b':ub,
                    'source_group':f'polygon_pair_{i}_{j}_part_{k}',
                    'evidence_kind':'derived shared mapped boundary; contact type and correlation need review',
                    'fault_exclusion_buffer_m':50}))
    collection(path/'contact_traces.geojson',traces,epsg)
    cr=[]
    for f in traces:
        line=shape(f['geometry']);p=f['properties']
        for d in np.arange(50,line.length,150):
            v=line.interpolate(d)
            cr.append({'observation_id':f'C{len(cr):05d}','X':v.x,'Y':v.y,
                       'contact_id':p['contact_id'],'unit_a':p['unit_a'],'unit_b':p['unit_b'],
                       'source_group':p['source_group'],'position_sigma_m':150 if wa else 50,
                       'uncertainty_status':'assumed benchmark value; not survey-certified',
                       'evidence_kind':'derived contact candidate; review before assigning a scalar value'})
    contacts=pd.DataFrame(cr)
    if contacts.empty:raise ValueError(f'No shared contacts in {name}')
    contacts['Z']=sample_dem(path,contacts.X,contacts.Y)
    contacts.to_csv(path/'contacts.csv',index=False)
    # Preserve original boundaries separately: they may include unconformities and intrusive contacts.
    if not wa:
        collection(path/'source_lithological_boundaries.geojson',
                   read_tab(source/'MCRR_LithBoundary_100K.TAB',bounds),epsg)
    write_json(path/'constraints.json',{
        'status':'awaiting geologist review; no unmeasured slip or magnitude is asserted',
        'known':{'surface_fault_traces':'faults.geojson','bedding':'bedding.csv'},
        'to_elicit':['fault slip sense and pitch bounds','fault dip and event order',
                     'trusted unit-pair/contact correlations','true tips versus concealed continuation',
                     'plausible displacement ranges and profile complexity'],
        'warning':'Do not treat missing or sentinel-valued displacement as zero; preserve source fields.',
        'agent_access':'Use the selected training split and apply its map mask; raw sources reveal withheld geology.'})
    add_splits(path,contacts,bedding,bounds,500)
    xx,yy=pixel_grid(bounds,401)
    preview(path,title,bounds,polygons,traces,faults,bedding,xx,yy,dem)
    licence=('GSWA bedrock compilation DMIRS-016: CC BY-NC 4.0 per data.wa.gov.au catalogue; '
             'retain State of Western Australia attribution. Local snapshot extraction dates are in source attributes.'
             if wa else 'CC BY 4.0; Northern Territory of Australia (Northern Territory Geological Survey).')
    manifest={'dataset_id':name,'title':title,'kind':'real survey extract','horizontal_epsg':epsg,
        'bounds_xy_m':bounds,'map_scale_denominator':500000 if wa else 100000,
        'source_publication_year':2016 if wa else 1991,'source_gis_version':None if wa else '2018-03-09',
        'fault_feature_count':len(faults),'geology_feature_count':len(polygons),
        'contact_trace_count':len(traces),'contact_count':len(contacts),'bedding_count':len(bedding),
        'licence':licence,'slip_ground_truth':None,'validation_status':'predictive benchmark; not verified slip truth',
        'contact_status':'unit-pair boundary candidates, not asserted basal contacts; no invented scalar levels or unit thicknesses',
        'orientation_convention':'dip direction clockwise from north; upward geometric poles; polarity unresolved',
        'dem':{'source':'Mapzen/Terrain Tiles on AWS; Australia terrain data copyright Commonwealth of Australia (Geoscience Australia) 2017',
               'source_zoom':11,'output_spacing_m':20000/401,'resampling':'bilinear',
               'vertical_datum':'source terrain product; absolute vertical datum not independently reconciled with survey data',
               'observation_Z':'sampled from packaged DEM; not surveyed contact elevations'},
        'uncertainty_assumptions':{'position_sigma_m':150 if wa else 50,'orientation_sigma_degrees':10,
               'status':'provisional sensitivity settings, not accuracy claims'},
        'sources':source_records,'terrain_sources':terrain_sources,
        'source_links':(['https://doi.org/10.5194/gmd-14-5063-2021',
                         'https://catalogue.data.wa.gov.au/en/dataset/1-500-000-state-interpreted-bedrock-geology-dmirs-016']
                       if wa else ['https://geoscience.nt.gov.au/gemis/ntgsjspui/handle/1/81583'])}
    write_json(path/'manifest.json',manifest)
    shutil.copyfile(CACHE/'terrain_attribution.md',path/'TERRAIN_ATTRIBUTION.md')
    return manifest


def finalize():
    """Package review aids and physically masked map layers for existing datasets."""
    from shapely.ops import nearest_points
    manifests=[]
    for path in sorted(OUT.glob('*')):
        if not path.is_dir() or not (path/'manifest.json').exists():continue
        manifest=json.loads((path/'manifest.json').read_text(encoding='utf-8'))
        bounds=manifest['bounds_xy_m'];epsg=manifest.get('horizontal_epsg')
        traces=json.loads((path/'contact_traces.geojson').read_text(encoding='utf-8'))['features']
        faults=json.loads((path/'faults.geojson').read_text(encoding='utf-8'))['features']
        polygons=(json.loads((path/'geology.geojson').read_text(encoding='utf-8'))['features']
                  if (path/'geology.geojson').exists() else [])
        for k in range(5):
            target=path/'splits'/f'fold_{k}'
            mask=json.loads((target/'mask.json').read_text(encoding='utf-8'))
            lo,hi=mask['test_y_interval_m'];gap=mask['buffer_m']
            training=box(*bounds).difference(box(bounds[0]-1,lo-gap,bounds[2]+1,hi+gap))
            for name,features in [('contact_traces',traces),('geology',polygons)]:
                if not features:continue
                masked=[]
                for f in features:
                    geom=shape(f['geometry']).intersection(training)
                    if not geom.is_empty:masked.append(feature(geom,f['properties']))
                collection(target/f'{name}_train.geojson',masked,epsg)
            mask['masked_training_map_files']='*_train.geojson; do not provide complete source maps as training evidence'
            write_json(target/'mask.json',mask)
        if polygons:
            key='code' if epsg==28350 else 'Symbol'
            units={str(f['properties'].get(key)):f['properties'] for f in polygons}
            pd.DataFrame([{'unit_code':k,**v} for k,v in sorted(units.items())]).to_csv(path/'unit_catalogue.csv',index=False)
            candidates=[]
            fault_geometries=[shape(f['geometry']) for f in faults]
            fault_tree=STRtree(fault_geometries)
            for f in traces:
                for line in parts(shape(f['geometry']),'LineString'):
                    for endpoint in [Point(line.coords[0]),Point(line.coords[-1])]:
                        if not fault_geometries:continue
                        j=int(fault_tree.nearest(endpoint))
                        distance=endpoint.distance(fault_geometries[j])
                        if distance>150:continue
                        projected=nearest_points(endpoint,fault_geometries[j])[1]
                        candidates.append({'candidate_id':f'K{len(candidates):04d}',
                            'fault_id':faults[j]['properties']['fault_id'],
                            'contact_id':f['properties']['contact_id'],
                            'source_group':f['properties']['source_group'],
                            'endpoint_X':endpoint.x,'endpoint_Y':endpoint.y,
                            'projected_X':projected.x,'projected_Y':projected.y,
                            'projection_distance_m':distance,
                            'status':'geometric candidate only; correlation and extrapolation require geologist review'})
            cols=['candidate_id','fault_id','contact_id','source_group','endpoint_X','endpoint_Y',
                  'projected_X','projected_Y','projection_distance_m','status']
            pd.DataFrame(candidates,columns=cols).to_csv(path/'cutoff_candidates.csv',index=False)
            ranking=[]
            for f in faults:
                fid=f['properties']['fault_id']
                ranking.append({'fault_id':fid,'mapped_length_in_window_m':shape(f['geometry']).length,
                                'nearby_cutoff_candidates':sum(c['fault_id']==fid for c in candidates),
                                'slip_magnitude_m':None,'review_status':'unreviewed'})
            pd.DataFrame(ranking).sort_values(['nearby_cutoff_candidates','mapped_length_in_window_m'],
                ascending=False).to_csv(path/'fault_review_priority.csv',index=False)
            manifest['cutoff_candidate_count']=len(candidates)
            write_json(path/'manifest.json',manifest)
        checksums={str(p.relative_to(path)).replace('\\','/'):digest(p)
                   for p in sorted(path.rglob('*')) if p.is_file() and p.name!='SHA256SUMS.json'}
        write_json(path/'SHA256SUMS.json',checksums)
        manifests.append(manifest)
    write_json(OUT/'catalogue.json',manifests)
    versions={name:importlib.metadata.version(name) for name in
              ['numpy','pandas','scipy','scikit-image','matplotlib','requests','shapely','pyproj','rasterio','pyogrio']}
    write_json(OUT/'environment.json',versions)
    (BASE/'requirements-datasets.txt').write_text(''.join(f'{k}=={v}\n' for k,v in versions.items()),encoding='utf-8')
    fig,axes=plt.subplots(2,3,figsize=(18,11))
    for ax,manifest in zip(axes.flat,manifests):
        ax.imshow(plt.imread(OUT/manifest['dataset_id']/'preview.png'));ax.axis('off')
    for ax in list(axes.flat)[len(manifests):]:ax.axis('off')
    fig.tight_layout();fig.savefig(OUT/'overview.png',dpi=140);plt.close(fig)
    print(json.dumps([{'dataset':m['dataset_id'],'contacts':m['contact_count'],
                      'bedding':m['bedding_count']} for m in manifests],indent=2),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--synthetic-only',action='store_true')
    parser.add_argument('--only',choices=['hamersley','mcarthur'])
    parser.add_argument('--finalize',action='store_true')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if args.finalize:
        finalize()
        return
    if args.only:
        real_dataset(args.only)
        manifests=[json.loads(p.read_text(encoding='utf-8')) for p in sorted(OUT.glob('*/manifest.json'))]
        write_json(OUT/'catalogue.json',manifests)
        print(json.dumps([{'dataset':m['dataset_id'],'contacts':m['contact_count'],
                          'bedding':m['bedding_count']} for m in manifests],indent=2),flush=True)
        return
    manifests=[synthetic(i) for i in [1,2,3]]
    if not args.synthetic_only:
        manifests += [real_dataset(r) for r in ['hamersley','mcarthur']]
    write_json(OUT/'catalogue.json',manifests)
    print(json.dumps([{'dataset':m['dataset_id'],'contacts':m['contact_count'],
                      'bedding':m['bedding_count']} for m in manifests],indent=2))


if __name__=='__main__':main()
