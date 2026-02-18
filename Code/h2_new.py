from pymodbus.client import ModbusTcpClient
from opcua import Client as OPCUAClient
import time
from datetime import datetime
import csv
import random

# ----------------------------
# KONFIGURASI
# ----------------------------
H1_IP = "10.0.1.2"
MODBUS_PORT = 5020
OPCUA_ENDPOINT = "opc.tcp://10.0.2.2:4840/mininet/"  # H3 OPC UA server

V_BASE_ADDR = 0
I_BASE_ADDR = 10
BREAKER_BASE_ADDR = 0
NUM_BUS = 5

# ----------------------------
# MODBUS CLIENT (H1)
# ----------------------------
modbus_client = ModbusTcpClient(H1_IP, port=MODBUS_PORT)
modbus_client.connect()

# ----------------------------
# OPC UA CLIENT (H3)
# ----------------------------
opc_client = OPCUAClient(OPCUA_ENDPOINT)
opc_client.connect()
idx = opc_client.get_namespace_index("mininet-opcua")
root = opc_client.get_root_node()

# Buat node dictionary untuk data dan command
tegangan_nodes = {bus: root.get_child(["0:Objects", f"{idx}:SENSORS", f"{idx}:V_bus_{bus}"]) for bus in range(1, NUM_BUS+1)}
arus_nodes = {bus: root.get_child(["0:Objects", f"{idx}:SENSORS", f"{idx}:I_bus_{bus}"]) for bus in range(1, NUM_BUS+1)}
command_nodes = {bus: root.get_child(["0:Objects", f"{idx}:COMMANDS", f"{idx}:CMD_bus_{bus}"]) for bus in range(1, NUM_BUS+1)}

# ----------------------------
# LOG FILE
# ----------------------------
csv_file = "log_modbus_h2.csv"
with open(csv_file, "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "bus", "V(pu)", "I(pu)", "breaker_status"])

# ----------------------------
# STATUS BREAKER LOKAL
# ----------------------------
breaker_status = {bus: 0 for bus in range(1, NUM_BUS+1)}  # 0=OPEN, 1=CLOSE

# ----------------------------
# LOOP UTAMA
# ----------------------------
try:
    while True:
        ts = datetime.now().isoformat()

        for bus in range(1, NUM_BUS+1):
            addr_v = V_BASE_ADDR + (bus - 1)
            addr_i = I_BASE_ADDR + (bus - 1)
            addr_brk = BREAKER_BASE_ADDR + (bus - 1)

            # 1) Baca tegangan/arus dari H1 (Modbus HR)
            rr_v = modbus_client.read_holding_registers(addr_v, 1, unit=1)
            rr_i = modbus_client.read_holding_registers(addr_i, 1, unit=1)
            if rr_v.isError() or rr_i.isError():
                print(f"Error baca Modbus bus {bus}")
                continue

            v_scaled = rr_v.registers[0]
            i_scaled = rr_i.registers[0]

            v = v_scaled / 1000.0
            i = i_scaled / 1000.0

            # 2) Kirim ke H3 (OPC UA)
            try:
                tegangan_nodes[bus].set_value(v)
                arus_nodes[bus].set_value(i)
            except Exception as e:
                print(f"Error kirim ke OPC UA bus {bus}: {e}")

            # 3) Terima status breaker dari H3
            try:
                cmd = command_nodes[bus].get_value()
                if cmd in [0,1]:
                    breaker_status[bus] = cmd
            except Exception as e:
                print(f"Error baca command OPC UA bus {bus}: {e}")

            # 4) Kirim status breaker ke H1 (Modbus coil)
            try:
                modbus_client.write_coil(addr_brk, breaker_status[bus], unit=1)
            except Exception as e:
                print(f"Error update breaker H1 bus {bus}: {e}")

            # 5) Log
            print(f"[{ts}] Bus {bus}: V={v:.3f} pu, I={i:.3f}, Breaker={'CLOSE' if breaker_status[bus]==1 else 'OPEN'}")
            writer.writerow([ts, bus, v, i, breaker_status[bus]])

        f.flush()
        time.sleep(5)

except KeyboardInterrupt:
    print("RTU/IED dihentikan")

finally:
    modbus_client.close()
    opc_client.disconnect()
