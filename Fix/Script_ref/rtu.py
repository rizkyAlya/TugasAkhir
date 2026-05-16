"""
RTU/IED: relay Modbus antara field (h1) dan gateway (h3).
"""
import os
import random
import time
from datetime import datetime

from pymodbus.client import ModbusTcpClient
from pymodbus.exceptions import ConnectionException

FIELD_IP = os.environ.get("FIELD_IP", "10.0.1.2")
GATEWAY_IP = os.environ.get("GATEWAY_IP", "10.0.2.2")
MODBUS_PORT = int(os.environ.get("MODBUS_PORT", "5020"))
LOOP_INTERVAL_S = float(os.environ.get("RTU_LOOP_INTERVAL_S", "4"))

V_BASE_ADDR = 0
I_BASE_ADDR = 10
PF_BASE_ADDR = 30
BREAKER_BASE_ADDR = 0
BREAKER_FB_BASE_ADDR = 20
PF_FB_BASE_ADDR = 30
V_SCALE = 1000
I_SCALE = 30
PF_SCALE = 10000
NUM_BUS = 5
DT_PATH_PROBE_ADDR = 95

RTU_NOISE_SEED = int(os.environ.get("RTU_NOISE_SEED", "7"))
V_NOISE_SIGMA = float(os.environ.get("RTU_V_NOISE_SIGMA", "0.003"))
I_NOISE_SIGMA = float(os.environ.get("RTU_I_NOISE_SIGMA", "1.5"))
_noise_rng = random.Random(RTU_NOISE_SEED)

field_client = ModbusTcpClient(FIELD_IP, port=MODBUS_PORT)
gateway_client = ModbusTcpClient(GATEWAY_IP, port=MODBUS_PORT)
_dt_path_cycle = 0
breaker_cmd = {bus: 1 for bus in range(1, NUM_BUS + 1)}


def _connect_with_retry(client: ModbusTcpClient, label: str, retry_delay_s: float = 1.0) -> None:
    while True:
        try:
            if client.connect():
                return
            print(f"Connection to {label} failed (connect() returned False). Retrying...")
        except Exception as exc:
            print(f"Connection to {label} failed: {exc}. Retrying...")
        time.sleep(retry_delay_s)


def _is_connected(client: ModbusTcpClient) -> bool:
    val = getattr(client, "connected", None)
    if val is None:
        return False
    try:
        return bool(val)
    except Exception:
        return False


def ensure_connections() -> None:
    if not _is_connected(field_client):
        _connect_with_retry(field_client, f"FIELD ({FIELD_IP}:{MODBUS_PORT})")
    if not _is_connected(gateway_client):
        _connect_with_retry(gateway_client, f"GATEWAY ({GATEWAY_IP}:{MODBUS_PORT})")


def apply_measurement_noise(v_pu, i_amp):
    v_noisy = v_pu + _noise_rng.gauss(0.0, V_NOISE_SIGMA)
    i_noisy = max(0.0, i_amp + _noise_rng.gauss(0.0, I_NOISE_SIGMA))
    return v_noisy, i_noisy


def read_modbus_bus(bus):
    addr_v = V_BASE_ADDR + (bus - 1)
    addr_i = I_BASE_ADDR + (bus - 1)
    addr_pf = PF_BASE_ADDR + (bus - 1)
    rr_v = field_client.read_holding_registers(addr_v, 1, unit=1)
    rr_i = field_client.read_holding_registers(addr_i, 1, unit=1)
    rr_pf = field_client.read_holding_registers(addr_pf, 1, unit=1)
    if rr_v.isError() or rr_i.isError() or rr_pf.isError():
        return None, None, None
    return (
        rr_v.registers[0] / V_SCALE,
        rr_i.registers[0] / I_SCALE,
        rr_pf.registers[0] / PF_SCALE,
    )


def read_breaker_field(bus):
    """Status switch aktual di field (coil) sebelum perintah siklus ini diterapkan."""
    addr = BREAKER_BASE_ADDR + (bus - 1)
    rr = field_client.read_coils(addr, 1, unit=0)
    if rr.isError() or not rr.bits:
        return None
    return 1 if rr.bits[0] else 0


def read_breaker_command(bus):
    addr_cmd = BREAKER_BASE_ADDR + (bus - 1)
    rr_cmd = gateway_client.read_coils(addr_cmd, 1, unit=1)
    if rr_cmd.isError() or not rr_cmd.bits:
        return None
    return 1 if rr_cmd.bits[0] else 0


def update_breaker_field(bus, status):
    addr_brk = BREAKER_BASE_ADDR + (bus - 1)
    try:
        field_client.write_coil(addr_brk, bool(status), unit=0)
    except Exception as exc:
        print(f"Error update breaker FIELD bus {bus}: {exc}")


def send_to_gateway_modbus(bus, v, i, pf, breaker_fb):
    try:
        gateway_client.write_register(V_BASE_ADDR + (bus - 1), int(v * V_SCALE), unit=1)
        gateway_client.write_register(I_BASE_ADDR + (bus - 1), int(i * I_SCALE), unit=1)
        gateway_client.write_register(PF_FB_BASE_ADDR + (bus - 1), int(pf * PF_SCALE), unit=1)
        gateway_client.write_register(BREAKER_FB_BASE_ADDR + (bus - 1), int(breaker_fb), unit=1)
    except Exception as exc:
        print(f"Error kirim ke gateway Modbus bus {bus}: {exc}")


try:
    ensure_connections()
    print(f"RTU measurement noise: seed={RTU_NOISE_SEED} V_sigma={V_NOISE_SIGMA} I_sigma={I_NOISE_SIGMA}")
    while True:
        print("\n")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            ensure_connections()
            for bus in range(1, NUM_BUS + 1):
                v, i, pf = read_modbus_bus(bus)
                if v is None or i is None or pf is None:
                    print(f"Error baca V/I/PF field bus {bus}")
                    continue

                v_raw, i_raw = v, i
                v, i = apply_measurement_noise(v, i)

                brk_fb = read_breaker_field(bus)
                if brk_fb is None:
                    brk_fb = breaker_cmd[bus]

                cmd = read_breaker_command(bus)
                if cmd in (0, 1):
                    breaker_cmd[bus] = cmd

                update_breaker_field(bus, breaker_cmd[bus])
                send_to_gateway_modbus(bus, v, i, pf, brk_fb)

                print(
                    f"[{ts}] Bus {bus}: V={v:.3f} pu (raw {v_raw:.3f}) "
                    f"I={i:.1f} A (raw {i_raw:.1f}) PF={pf:.4f} | "
                    f"FB={'CLOSE' if brk_fb else 'OPEN'} "
                    f"CMD={'CLOSE' if breaker_cmd[bus] else 'OPEN'}"
                )

            _dt_path_cycle = ((_dt_path_cycle + 1) & 0xFFFF) or 1
            gateway_client.write_register(DT_PATH_PROBE_ADDR, _dt_path_cycle, unit=1)
            print(f"DT_PATH_LAT,h2,{time.time():.6f},{_dt_path_cycle}", flush=True)

        except ConnectionException as exc:
            print(f"[{ts}] Koneksi Modbus terputus: {exc}. Reconnecting...")
            try:
                field_client.close()
            except Exception:
                pass
            try:
                gateway_client.close()
            except Exception:
                pass
            time.sleep(1)

        time.sleep(LOOP_INTERVAL_S)

except KeyboardInterrupt:
    print("RTU/IED dihentikan")
finally:
    field_client.close()
    gateway_client.close()
