from opcua import Client as OPCUAClient
import time
import random

# --- Modbus client ---
from pymodbus.client.sync import ModbusTcpClient

# =========================
# KONFIGURASI
# =========================
OPCUA_ENDPOINT = "opc.tcp://10.0.0.103:4840/mininet/"
MODBUS_HOST = "0.0.0.0"      # Modbus server ada di h1 sendiri
MODBUS_PORT = 5020

# Mapping register Modbus
# Misal:
#   - V_bus_1..5 disimpan di Holding Register 0..4
#   - I_bus_1..5 disimpan di Holding Register 10..14
V_BASE_ADDR = 0
I_BASE_ADDR = 10

# =========================
# OPC UA SETUP
# =========================
client_ua = OPCUAClient(OPCUA_ENDPOINT)
client_ua.connect()

idx = client_ua.get_namespace_index("mininet-opcua")
print("Namespace index:", idx)

root = client_ua.get_root_node()

tegangan_nodes = {}
arus_nodes = {}
command_nodes = {}

for bus in range(1, 6):
    tegangan_nodes[bus] = root.get_child([
        "0:Objects", f"{idx}:SENSORS", f"{idx}:V_bus_{bus}"
    ])
    arus_nodes[bus] = root.get_child([
        "0:Objects", f"{idx}:SENSORS", f"{idx}:I_bus_{bus}"
    ])
    command_nodes[bus] = root.get_child([
        "0:Objects", f"{idx}:COMMANDS", f"{idx}:CMD_bus_{bus}"
    ])

# =========================
# MODBUS CLIENT SETUP
# =========================
client_mb = ModbusTcpClient(MODBUS_HOST, port=MODBUS_PORT)
if not client_mb.connect():
    print("Gagal koneksi ke Modbus server, cek IP/port!")
    exit(1)

print("Terhubung ke Modbus server di", MODBUS_HOST, MODBUS_PORT)

# =========================
# LOOP UTAMA
# =========================
try:
    while True:
        for bus in range(1, 6):

            # ----- 1) Generate data dummy -----
            v = 1.0 + random.uniform(-0.05, 0.05)    # per unit
            i = random.uniform(0.1, 2.0)             # misal arus dalam pu atau kA

            # ----- 2) Kirim ke OPC UA -----
            try:
                tegangan_nodes[bus].set_value(v)
                arus_nodes[bus].set_value(i)
            except Exception as e:
                print("Error OPC UA:", e)

            # ----- 3) Simpan ke Modbus Holding Register -----
            # Karena Modbus cuma dukung 16-bit register,
            v_scaled = int(v * 1000)
            i_scaled = int(i * 1000)

            addr_v = V_BASE_ADDR + (bus - 1)   # HR untuk V_bus_n
            addr_i = I_BASE_ADDR + (bus - 1)   # HR untuk I_bus_n

            try:
                # function code 0x06: write single holding register
                rr_v = client_mb.write_register(addr_v, v_scaled, unit=1)
                rr_i = client_mb.write_register(addr_i, i_scaled, unit=1)

                if rr_v.isError() or rr_i.isError():
                    print(f"Error write Modbus bus {bus}")
            except Exception as e:
                print("Error Modbus:", e)

            # ----- 4) Ambil command dari PandaPower via OPC UA -----
            try:
                cmd = command_nodes[bus].get_value()
                if cmd == 1:
                    print(f"Bus {bus}: command = breaker OPEN")
                elif cmd == 2:
                    print(f"Bus {bus}: command = breaker CLOSE")
                else:
                    print(f"Bus {bus}: command = NORMAL")
            except Exception as e:
                print("Error baca command:", e)

        # jeda antar siklus
        time.sleep(5)

except KeyboardInterrupt:
    print("Dihentikan oleh user.")

finally:
    client_ua.disconnect()
    client_mb.close()
