from opcua import Client as OPCUAClient
import time
import random
import logging
from threading import Thread

from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.datastore import ModbusSequentialDataBlock

# =========================
# LOGGING
# =========================
logging.basicConfig()
log = logging.getLogger()
log.setLevel(logging.INFO)

# =========================
# KONFIGURASI
# =========================
OPCUA_ENDPOINT = "opc.tcp://10.0.0.103:4840/mininet/"

MODBUS_LISTEN_IP = "0.0.0.0"
MODBUS_PORT = 5020

# Mapping register Modbus
#   - V_bus_1..5 di Holding Register 0..4
#   - I_bus_1..5 di Holding Register 10..14
V_BASE_ADDR = 0
I_BASE_ADDR = 10
NUM_BUS = 5

# =========================
# MODBUS SERVER CONTEXT
# =========================
store = ModbusSlaveContext(
    di=ModbusSequentialDataBlock(0, [0] * 100),     # Discrete Inputs
    co=ModbusSequentialDataBlock(0, [0] * 100),     # Coils
    hr=ModbusSequentialDataBlock(0, [0] * 100),     # Holding Registers
    ir=ModbusSequentialDataBlock(0, [0] * 100),     # Input Registers
)

context = ModbusServerContext(slaves=store, single=True)


def start_modbus_server():
    """Jalankan Modbus TCP server (blocking) di thread sendiri."""
    print(f"Starting Modbus TCP server on {MODBUS_LISTEN_IP}:{MODBUS_PORT}")
    StartTcpServer(context=context, identity=None,
                   address=(MODBUS_LISTEN_IP, MODBUS_PORT))


# =========================
# FUNGSI UTAMA: OPC UA + UPDATE DATASTORE MODBUS
# =========================
def main_loop():
    # --- OPC UA SETUP ---
    client_ua = OPCUAClient(OPCUA_ENDPOINT)
    client_ua.connect()

    idx = client_ua.get_namespace_index("mininet-opcua")
    print("Namespace index:", idx)

    root = client_ua.get_root_node()

    tegangan_nodes = {}
    arus_nodes = {}
    command_nodes = {}

    for bus in range(1, NUM_BUS + 1):
        tegangan_nodes[bus] = root.get_child([
            "0:Objects", f"{idx}:SENSORS", f"{idx}:V_bus_{bus}"
        ])
        arus_nodes[bus] = root.get_child([
            "0:Objects", f"{idx}:SENSORS", f"{idx}:I_bus_{bus}"
        ])
        command_nodes[bus] = root.get_child([
            "0:Objects", f"{idx}:COMMANDS", f"{idx}:CMD_bus_{bus}"
        ])

    slave_id = 0x00          # karena single=True
    fx_hr = 3                # 3 = Holding Register

    try:
        while True:
            for bus in range(1, NUM_BUS + 1):

                # ----- 1) Generate data dummy -----
                v = 1.0 + random.uniform(-0.05, 0.05)    # per unit
                i = random.uniform(0.1, 2.0)             # misal arus

                # ----- 2) Kirim ke OPC UA -----
                try:
                    tegangan_nodes[bus].set_value(v)
                    arus_nodes[bus].set_value(i)
                except Exception as e:
                    print("Error OPC UA:", e)

                # ----- 3) Simpan ke Modbus datastore (Holding Registers) -----
                # Scaling ke integer (Modbus 16-bit)
                v_scaled = int(v * 1000)
                i_scaled = int(i * 1000)

                addr_v = V_BASE_ADDR + (bus - 1)
                addr_i = I_BASE_ADDR + (bus - 1)

                try:
                    context[slave_id].setValues(fx_hr, addr_v, [v_scaled])
                    context[slave_id].setValues(fx_hr, addr_i, [i_scaled])
                    print(f"Update HR[{addr_v}]={v_scaled}, HR[{addr_i}]={i_scaled}")
                except Exception as e:
                    print("Error update Modbus datastore:", e)

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

            time.sleep(5)

    except KeyboardInterrupt:
        print("Dihentikan oleh user.")

    finally:
        client_ua.disconnect()


# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    # 1) Start Modbus server di thread daemon
    t = Thread(target=start_modbus_server, daemon=True)
    t.start()

    # 2) Jalankan loop OPC UA + update datastore Modbus di thread utama
    main_loop()
