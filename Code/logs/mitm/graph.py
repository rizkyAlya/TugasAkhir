import pandas as pd
import matplotlib.pyplot as plt

# =========================
# 1. LOAD DATA
# =========================
file_path = "data.csv"  # ganti sesuai file kamu
df = pd.read_csv(file_path, delimiter=';')

# Jika timestamp berupa string, ubah ke datetime (opsional tapi disarankan)
# df["timestamp"] = pd.to_datetime(df["timestamp"])

# Urutkan berdasarkan waktu
df = df.sort_values(by="timestamp")

# =========================
# 2. HITUNG DRIFT
# =========================
# Drift = selisih absolut antara nilai real dan digital twin
df["drift_V"] = abs(df["v_raw"] - df["v_final"])
df["drift_I"] = abs(df["i_raw"] - df["i_final"])

# =========================
# 3. MAE (RINGKASAN ERROR)
# =========================
# Esensi:
# MAE menunjukkan rata-rata kesalahan → seberapa besar DT menyimpang dari kondisi nyata
mae_per_bus = df.groupby("bus")[["drift_V", "drift_I"]].mean()
print("\nMAE per Bus:")
print(mae_per_bus)

# Bandingkan sebelum vs sesudah serangan
# Esensi:
# untuk membuktikan apakah serangan benar-benar meningkatkan error
mae_phase = df.groupby(["bus", "phase"])[["drift_V", "drift_I"]].mean()
print("\nMAE per Bus (Pre vs Post Attack):")
print(mae_phase)

# =========================
# 4. VISUALISASI PER BUS
# =========================
for b in df["bus"].unique():
    subset = df[df["bus"] == b]

    pre = subset[subset["phase"] == "pre_attack"]
    post = subset[subset["phase"] == "post_attack"]

    # -------------------------
    # (A) Voltage: Real vs DT
    # -------------------------
    # Esensi:
    # Menunjukkan apakah digital twin mengikuti kondisi nyata atau menyimpang
    plt.figure()
    plt.plot(subset["timestamp"], subset["v_raw"], label="Real")
    plt.plot(subset["timestamp"], subset["v_final"], label="Digital Twin")
    plt.title(f"Voltage Comparison - Bus {b}")
    plt.xlabel("Time")
    plt.ylabel("Voltage")
    plt.legend()
    plt.grid()
    plt.savefig(f"voltage_bus_{b}.png")
    plt.close()

    # -------------------------
    # (B) Voltage Drift
    # -------------------------
    # Esensi:
    # Fokus langsung ke error → memudahkan melihat kapan drift terjadi dan seberapa besar
    plt.figure()
    plt.plot(subset["timestamp"], subset["drift_V"], label="Drift Voltage")
    plt.title(f"Voltage Drift - Bus {b}")
    plt.xlabel("Time")
    plt.ylabel("Error")
    plt.legend()
    plt.grid()
    plt.savefig(f"drift_voltage_bus_{b}.png")
    plt.close()

    # -------------------------
    # (C) Voltage Pre vs Post
    # -------------------------
    # Esensi:
    # Membuktikan dampak serangan dengan membandingkan kondisi sebelum dan sesudah
    plt.figure()
    plt.plot(pre["timestamp"], pre["drift_V"], label="Pre Attack")
    plt.plot(post["timestamp"], post["drift_V"], label="Post Attack")
    plt.title(f"Voltage Drift Comparison - Bus {b}")
    plt.xlabel("Time")
    plt.ylabel("Error")
    plt.legend()
    plt.grid()
    plt.savefig(f"drift_voltage_compare_bus_{b}.png")
    plt.close()

    # -------------------------
    # (D) Current: Real vs DT
    # -------------------------
    # Esensi:
    # Menunjukkan apakah perubahan beban (arus) juga mempengaruhi DT
    plt.figure()
    plt.plot(subset["timestamp"], subset["i_raw"], label="Real")
    plt.plot(subset["timestamp"], subset["i_final"], label="Digital Twin")
    plt.title(f"Current Comparison - Bus {b}")
    plt.xlabel("Time")
    plt.ylabel("Current")
    plt.legend()
    plt.grid()
    plt.savefig(f"current_bus_{b}.png")
    plt.close()

    # -------------------------
    # (E) Current Drift
    # -------------------------
    # Esensi:
    # Mengungkap error pada parameter beban → sering lebih sensitif dari tegangan
    plt.figure()
    plt.plot(subset["timestamp"], subset["drift_I"], label="Drift Current")
    plt.title(f"Current Drift - Bus {b}")
    plt.xlabel("Time")
    plt.ylabel("Error")
    plt.legend()
    plt.grid()
    plt.savefig(f"drift_current_bus_{b}.png")
    plt.close()

    # -------------------------
    # (F) Current Pre vs Post
    # -------------------------
    # Esensi:
    # Membandingkan dampak serangan terhadap arus (beban sistem)
    plt.figure()
    plt.plot(pre["timestamp"], pre["drift_I"], label="Pre Attack")
    plt.plot(post["timestamp"], post["drift_I"], label="Post Attack")
    plt.title(f"Current Drift Comparison - Bus {b}")
    plt.xlabel("Time")
    plt.ylabel("Error")
    plt.legend()
    plt.grid()
    plt.savefig(f"drift_current_compare_bus_{b}.png")
    plt.close()

# =========================
# 5. OVERVIEW SEMUA BUS
# =========================
# Esensi:
# Melihat apakah dampak serangan lokal atau menyebar ke seluruh sistem

# Voltage drift semua bus
plt.figure()
for b in df["bus"].unique():
    subset = df[df["bus"] == b]
    plt.plot(subset["timestamp"], subset["drift_V"], label=f"Bus {b}")

plt.title("Voltage Drift - All Bus")
plt.xlabel("Time")
plt.ylabel("Error")
plt.legend()
plt.grid()
plt.savefig("drift_voltage_all_bus.png")
plt.close()

# Current drift semua bus
plt.figure()
for b in df["bus"].unique():
    subset = df[df["bus"] == b]
    plt.plot(subset["timestamp"], subset["drift_I"], label=f"Bus {b}")

plt.title("Current Drift - All Bus")
plt.xlabel("Time")
plt.ylabel("Error")
plt.legend()
plt.grid()
plt.savefig("drift_current_all_bus.png")
plt.close()

# =========================
# 6. SIMPAN DATA HASIL
# =========================
df.to_csv("hasil_drift.csv", sep=';', index=False)

print("\nSemua proses selesai. Grafik dan hasil sudah disimpan.")
