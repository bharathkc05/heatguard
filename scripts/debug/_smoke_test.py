"""Smoke test for pythermalcomfort v2.9.0 PHS API."""
import pythermalcomfort
print(f"Version: {pythermalcomfort.__version__}")

from pythermalcomfort.models import phs

# Test 1: Hot conditions
print("\n=== Test 1: Hot (tdb=40, tr=52, rh=30) ===")
r1 = phs(tdb=40, tr=52, rh=30, v=1.5, met=150, clo=0.5,
         posture=2, wme=0, duration=480, limit_inputs=False)
print(f"  Type: {type(r1)}")
print(f"  Keys: {list(r1.keys()) if isinstance(r1, dict) else dir(r1)}")
for k, v in r1.items():
    print(f"  {k}: {v}")

# Test 2: Mild conditions
print("\n=== Test 2: Mild (tdb=25, tr=30, rh=50) ===")
r2 = phs(tdb=25, tr=30, rh=50, v=1.5, met=65, clo=0.3,
         posture=2, wme=0, duration=480, limit_inputs=False)
for k, v in r2.items():
    print(f"  {k}: {v}")

# Test 3: Extreme hot-dry
print("\n=== Test 3: Extreme (tdb=44, tr=58, rh=15) ===")
r3 = phs(tdb=44, tr=58, rh=15, v=2.0, met=200, clo=0.5,
         posture=2, wme=0, duration=480, limit_inputs=False)
for k, v in r3.items():
    print(f"  {k}: {v}")

# Test 4: Hot-humid
print("\n=== Test 4: Hot-humid (tdb=36, tr=44, rh=85) ===")
r4 = phs(tdb=36, tr=44, rh=85, v=0.5, met=200, clo=0.5,
         posture=2, wme=0, duration=480, limit_inputs=False)
for k, v in r4.items():
    print(f"  {k}: {v}")
