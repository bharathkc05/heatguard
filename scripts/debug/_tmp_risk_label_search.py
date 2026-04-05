import json
import urllib.request
from itertools import product

lat, lon = 24.5, 78.0
hydr = ['well', 'mild', 'dehydrated', 'severe']
acts = ['light', 'moderate', 'heavy', 'very_heavy']
hours = [2.0, 3.0, 4.0, 5.0, 5.5, 6.0, 6.5, 7.0]
hr = [100, 110, 120, 130, 140, 150, 160]
accl = [True, False]

found = {}
for h, a, ho, bpm, ac in product(hydr, acts, hours, hr, accl):
    payload = {
        'worker_id': 1,
        'lat': lat,
        'lon': lon,
        'hours_worked': ho,
        'hydration_status': h,
        'activity_level': a,
        'acclimatized': ac,
        'hr_bpm': bpm,
    }
    req = urllib.request.Request(
        'http://localhost:8000/predict',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            out = json.loads(r.read().decode('utf-8'))
        lab = out['risk_label']
        if lab not in found:
            found[lab] = (payload, out['risk_score'])
        if {'LOW', 'MODERATE', 'HIGH', 'CRITICAL'}.issubset(found.keys()):
            break
    except Exception:
        pass

print('FOUND_LABELS', sorted(found.keys()))
for k in ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']:
    if k in found:
        payload, score = found[k]
        print(k, 'score=', score, 'payload=', payload)
