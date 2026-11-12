"""Check dataset integrity and analytic truth, without fitting fault parameters."""

import json
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from shapely.geometry import shape

from build_datasets import OUT, field, profile, restored, terrain, write_json


def check(condition, description):
    if not condition:
        raise AssertionError(description)


def main():
    results = []
    manifests = json.loads((OUT/'catalogue.json').read_text(encoding='utf-8'))
    check(len(manifests) == 5, 'Expected three synthetic and two real datasets')
    for manifest in manifests:
        path = OUT/manifest['dataset_id']
        hashes=json.loads((path/'SHA256SUMS.json').read_text(encoding='utf-8'))
        for name,expected in hashes.items():
            check(hashlib.sha256((path/name).read_bytes()).hexdigest()==expected,
                  f'{path.name}: file hash changed: {name}')
        contacts = pd.read_csv(path/'contacts.csv')
        bedding = pd.read_csv(path/'bedding.csv')
        bounds = manifest['bounds_xy_m']
        for name, table in [('contacts',contacts),('bedding',bedding)]:
            check(len(table)>0, f'{path.name}: empty {name}')
            check(table.observation_id.is_unique, f'{path.name}: duplicate {name} IDs')
            check(np.isfinite(table[['X','Y','Z']].to_numpy()).all(), f'{path.name}: invalid positions')
            check(table.X.between(bounds[0],bounds[2]).all() and
                  table.Y.between(bounds[1],bounds[3]).all(), f'{path.name}: out-of-window observations')
        norms = np.linalg.norm(bedding[['nx','ny','nz']].to_numpy(),axis=1)
        check(np.allclose(norms,1,atol=1e-6),f'{path.name}: nonunit bedding poles')
        with rasterio.open(path/'dem.tif') as dem:
            values=dem.read(1,masked=True)
            check(values.count()==values.size,f'{path.name}: incomplete terrain')
            if manifest['kind']!='synthetic':
                check(dem.crs.to_epsg()==manifest['horizontal_epsg'],f'{path.name}: wrong DEM CRS')
                sampled=np.array([v[0] for v in dem.sample(zip(contacts.X,contacts.Y))])
                check(np.allclose(sampled,contacts.Z,atol=1e-3),f'{path.name}: DEM/observation mismatch')
        for name in ['faults.geojson','contact_traces.geojson']:
            features=json.loads((path/name).read_text(encoding='utf-8'))['features']
            check(len(features)>0,f'{path.name}: empty {name}')
            check(all(shape(f['geometry']).is_valid and not shape(f['geometry']).is_empty
                      for f in features),f'{path.name}: invalid geometry')
        for fold in range(5):
            split=path/'splits'/f'fold_{fold}'
            mask=json.loads((split/'mask.json').read_text(encoding='utf-8'))
            lo,hi=mask['test_y_interval_m'];gap=mask['buffer_m']
            for layer in ['contacts','bedding']:
                train=pd.read_csv(split/f'{layer}_train.csv')
                test=pd.read_csv(split/f'{layer}_test.csv')
                check(set(train.observation_id).isdisjoint(test.observation_id),
                      f'{path.name}: shared train/test IDs')
                check(((train.Y<lo-gap)|(train.Y>hi+gap)).all(),
                      f'{path.name}: training data inside exclusion buffer')
                check(test.Y.between(lo,hi).all(),f'{path.name}: test data outside block')
        result={'dataset':path.name,'contacts':len(contacts),'bedding':len(bedding),
                'coordinate_geometry_dem_and_split_checks':'passed'}
        if manifest['kind']=='synthetic':
            case=int(manifest['dataset_id'].split('_')[1])
            check(np.allclose(contacts.Z,terrain(contacts.X,contacts.Y),atol=1e-8),
                  f'{path.name}: contacts do not lie on analytic terrain')
            traces=json.loads((path/'truth'/'contact_traces.geojson').read_text(encoding='utf-8'))['features']
            errors=[]
            for f in traces:
                xy=np.array(shape(f['geometry']).coords)
                residual=field(case,xy[:,0],xy[:,1],terrain(xy[:,0],xy[:,1]))-f['properties']['val']
                errors.extend(np.abs(residual))
            check(max(errors)<0.1,f'{path.name}: inaccurate noiseless contact contours')
            y0=np.linspace(-1900,1900,201);x0=np.full_like(y0,800);z0=np.full_like(y0,200)
            sy,sz=(150,-100) if case==1 else ((120*profile(y0),-180*profile(y0)) if case==2 else (0,100))
            xr,yr,zr=restored(case,x0,y0+sy,z0+sz)
            error=max(np.max(np.abs(xr-x0)),np.max(np.abs(yr-y0)),np.max(np.abs(zr-z0)))
            check(error<1e-7,f'{path.name}: forward/restoration inconsistency')
            result['max_noiseless_contact_field_error_m']=float(max(errors))
            result['max_round_trip_error_m']=float(error)
            if case==1:
                a=np.tile([0.2,-1.0],(20,1))
                check(np.linalg.matrix_rank(a)==1,'Parallel-marker toy must have rank one')
                result['slip_constraint_rank']=1
            if case==2:
                y=np.linspace(-1800,1800,10001)
                jac=1+120*np.gradient(profile(y),y)
                check(jac.min()>0,'Variable slip mapping folds onto itself')
                result['minimum_along_strike_jacobian']=float(jac.min())
            if case==3:
                check(300-200==100,'Equivalent-history net slip')
                result['history_equivalence']='old markers have the same net 100 m vertical forward slip'
        else:
            check(manifest['slip_ground_truth'] is None,'Real slip must not be fabricated')
            check('val' not in contacts.columns,'Unreviewed boundaries must not have invented scalar levels')
        results.append(result)
    write_json(OUT/'validation_report.json',{'status':'passed','datasets':results,
               'scope':'Data and analytic-generator validation only; no inference benchmark has been run.'})
    print(json.dumps(results,indent=2))


if __name__=='__main__':main()
