from pymodbus.client import ModbusTcpClient
from opcua import Client as OPCUAClient
import time
from datetime import datetime
import csv

H1_IP = "10.0.1.2"
MODBUS_PORT = 5020
OPCUA_ENDPOINT = "opc.tcp://10.0.2.2:4840/mininet/"

V_BASE_ADDR = 0
I_BASE_ADDR = 10
BREAKER_BASE_ADDR = 0
NUM_BUS = 5

# Modbus (h1)
modbus_client = ModbusTcpClient(H1_IP, port=MODBUS_PORT)
modbus_client.connect()

# OPC UA (h3)
opc_client = OPCUAClient(OPCUA_ENDPOINT)
opc_client.connect()
idx = opc_client.get_namespace_index("mininet-opcua")
root = opc_client.get_root_node()

tegangan_nodes = {bus: root.get_child(["0:Objects", f"{idx}:SENSORS", f"{idx}:V_bus_{bus}"]) for bus in range(1, NUM_BUS+1)}
arus_nodes = {bus: root.get_child(["0:Objects", f"{idx}:SENSORS", f"{idx}:I_bus_{bus}"]) for bus in range(1, NUM_BUS+1)}
command_nodes = {bus: root.get_child(["0:Objects", f"{idx}:COMMANDS", f"{idx}:CMD_bus_{bus}"]) for bus in range(1, NUM_BUS+1)}

# Status breaker (lokal)
breaker_status = {bus: 0 for bus in range(1, NUM_BUS+1)}  # 0=OPEN, 1=CLOSE

# Main function
def read_modbus_bus(bus):
    # Membaca V/I dari h1
    addr_v = V_BASE_ADDR + (bus - 1)
    addr_i = I_BASE_ADDR + (bus - 1)
    rr_v = modbus_client.read_holding_registers(addr_v, 1, unit=1)
    rr_i = modbus_client.read_holding_registers(addr_i, 1, unit=1)
    if rr_v.isError() or rr_i.isError():
        return None, None
    v = rr_v.registers[0] / 1000.0
    i = rr_i.registers[0] / 1000.0
    return v, i

# Update coils ke h1
def update_breaker_h1(bus, status):
    addr_brk = BREAKER_BASE_ADDR + (bus - 1)
    try:
        modbus_client.write_coil(addr_brk, status, unit=1)
    except Exception as e:
        print(f"Error update breaker H1 bus {bus}: {e}")

# Kirim data ke h3
def send_opcua_bus(bus, v, i, breaker):
    try:
        tegangan_nodes[bus].set_value(v)
        arus_nodes[bus].set_value(i)
        command_nodes[bus].set_value(breaker)
    except Exception as e:
        print(f"Error kirim ke OPC UA bus {bus}: {e}")

# Main loop
csv_file = "log_modbus.csv"    # File untuk menyimpan log data
with open(csv_file, "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "bus", "V(pu)", "I(pu)", "breaker_status"])
    
    try:
        while True:
            print("\n")
            ts = datetime.now().isoformat()

            for bus in range(1, NUM_BUS+1):
                v, i = read_modbus_bus(bus)
                if v is None or i is None:
                    print(f"Error baca Modbus bus {bus}")
                    continue

                # 1) Terima perintah breaker dari h3
                try:
                    cmd = command_nodes[bus].get_value()
                    if cmd in [0, 1]:
                        breaker_status[bus] = cmd
                except Exception as e:
                    print(f"Error baca command OPC UA bus {bus}: {e}")

                # 2) Update coil di h1
                update_breaker_h1(bus, breaker_status[bus])

                # 3) Kirim data dan status breaker ke h3
                send_opcua_bus(bus, v, i, breaker_status[bus])

                # 4) Perbarui log
                print(f"[{ts}] Bus {bus}: V={v:.3f} pu, I={i:.3f}, Breaker={'CLOSE' if breaker_status[bus]==1 else 'OPEN'}")
                writer.writerow([ts, bus, v, i, breaker_status[bus]])

            f.flush()
            time.sleep(5)

    except KeyboardInterrupt:
        print("RTU/IED dihentikan")

    finally:
        modbus_client.close()
        opc_client.disconnect()

