from pythermalcomfort.models import phs

cases = [
    ("Very mild",  dict(tdb=22, tr=26, v=1.5, rh=40, met=65,  clo=0.3, posture="standing", duration=480, limit_inputs=False)),
    ("Moderate",   dict(tdb=38, tr=48, v=1.0, rh=30, met=130, clo=0.5, posture="standing", duration=480, limit_inputs=False)),
    ("Hot-dry",    dict(tdb=44, tr=58, v=2.0, rh=15, met=200, clo=0.5, posture="standing", duration=480, limit_inputs=False)),
    ("Hot-humid",  dict(tdb=36, tr=44, v=0.5, rh=85, met=200, clo=0.5, posture="standing", duration=480, limit_inputs=False)),
]

for label, kw in cases:
    r = phs(**kw)
    v = vars(r)
    print(f"{label}: d_lim_t_re={v['d_lim_t_re']:.1f}  sweat_loss_g={v['sweat_loss_g']:.0f}  t_re={v['t_re']:.1f}  t_sk={v['t_sk']:.1f}")

# Also check with shorter durations to understand if t_re is cumulative
print("\n--- Duration comparison for same conditions ---")
for dur in [1, 10, 60, 120, 240, 480]:
    r = phs(tdb=38, tr=48, v=1.0, rh=30, met=130, clo=0.5, posture="standing", duration=dur, limit_inputs=False)
    v = vars(r)
    avg_t_re = v['t_re'] / dur
    print(f"  duration={dur:3d}: t_re={v['t_re']:7.2f}  avg_per_min={avg_t_re:.3f}  d_lim_t_re={v['d_lim_t_re']:.1f}  sweat_loss_g={v['sweat_loss_g']:.1f}")

# Check what the source code says about t_re
print("\n--- All field names ---")
r = phs(tdb=38, tr=48, v=1.0, rh=30, met=130, clo=0.5, posture="standing", duration=480, limit_inputs=False)
for k, v2 in vars(r).items():
    print(f"  {k}: {v2}")
