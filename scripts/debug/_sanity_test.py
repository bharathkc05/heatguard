"""Quick test — 5000 records to verify class balance after biased sampling."""
import sys
sys.path.insert(0, ".")
import generate_dataset as gd

df = gd.generate_dataset(n_records=5000, seed=42)

print("\nt_re_final stats:")
print(df["t_re_final"].describe())

print("\nrisk_label distribution:")
dist = df["risk_label"].value_counts()
pct = df["risk_label"].value_counts(normalize=True) * 100
for label in dist.index:
    print(f"  {label:<10}: {dist[label]:>5}  ({pct[label]:.1f}%)")

print("\nd_lim_t_re_raw stats:")
print(df["d_lim_t_re_raw"].describe())

print("\nwater_loss_g stats:")
print(df["water_loss_g"].describe())
