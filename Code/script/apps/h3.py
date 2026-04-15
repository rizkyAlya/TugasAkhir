from threading import Thread
from opcua import Server
from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.datastore import ModbusSequentialDataBlock
import time
from datetime import datetime

# Konfigurasi server OPC UA
server = Server()
server.set_endpoint("opc.tcp://10.0.2.2:4840/mininet/")

uri = "mininet-opcua"
idx = server.register_namespace(uri)

objects = server.get_objects_node()

sensor_folder = objects.add_folder(idx, "SENSORS")
command_folder = objects.add_folder(idx, "COMMANDS")

tegangan_nodes = {}
arus_nodes = {}
command_nodes = {}

last_breaker = {}

# Modbus gateway datastore:
# - Holding registers:
#   0-4   : V bus
#   10-14 : I bus
#   20-24 : breaker feedback dari RTU
# - Coils:
#   0-4   : breaker command ke RTU
MODBUS_LISTEN_IP = "0.0.0.0"
MODBUS_PORT = 5020
V_BASE_ADDR = 0
I_BASE_ADDR = 10
BREAKER_FB_BASE_ADDR = 20
BREAKER_CMD_BASE_ADDR = 0
NUM_BUS = 5

store = ModbusSlaveContext(
    di=ModbusSequentialDataBlock(0, [0] * 100),
    co=ModbusSequentialDataBlock(0, [1] * 100),
    hr=ModbusSequentialDataBlock(0, [0] * 100),
    ir=ModbusSequentialDataBlock(0, [0] * 100),
)
context = ModbusServerContext(slaves=store, single=True)


def start_modbus_server():
    print(f"Memulai Modbus Gateway di {MODBUS_LISTEN_IP}:{MODBUS_PORT}")
    StartTcpServer(context=context, identity=None, address=(MODBUS_LISTEN_IP, MODBUS_PORT))


for bus in range(1, 6):
    tegangan_nodes[bus] = sensor_folder.add_variable(idx, f"V_bus_{bus}", 0.0)
    tegangan_nodes[bus].set_writable()

    arus_nodes[bus] = sensor_folder.add_variable(idx, f"I_bus_{bus}", 0.0)
    arus_nodes[bus].set_writable()

    command_nodes[bus] = command_folder.add_variable(idx, f"CMD_bus_{bus}", 1)
    command_nodes[bus].set_writable()

    last_breaker[bus] = 1

print("Memulai Server OPC UA")
server.start()
t = Thread(target=start_modbus_server, daemon=True)
t.start()

try:
    while True:
        print("\n")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for bus in range(1, NUM_BUS + 1):
            cmd_val = last_breaker[bus]
            try:
                # 1) Ambil data dari RTU melalui Modbus
                addr_v = V_BASE_ADDR + (bus - 1)
                addr_i = I_BASE_ADDR + (bus - 1)
                _addr_b = BREAKER_FB_BASE_ADDR + (bus - 1)
                v_raw = context[0x00].getValues(3, addr_v, count=1)[0]
                i_raw = context[0x00].getValues(3, addr_i, count=1)[0]

                v = float(v_raw) / 1000.0
                i = float(i_raw) / 1000.0

                # 2) Publish ke OPC UA untuk pandapower (V/I)
                tegangan_nodes[bus].set_value(v)
                arus_nodes[bus].set_value(i)

                # 3) Ambil command (status breaker) dari OPC UA lalu tulis ke Modbus coil untuk RTU
                cmd = command_nodes[bus].get_value()
                cmd_val = 1 if int(cmd) == 1 else 0
                context[0x00].setValues(1, BREAKER_CMD_BASE_ADDR + (bus - 1), [cmd_val])

                print(f"[{ts}] [Bus {bus}] Data V/I/CMD berhasil update")
            except Exception as e:
                print(f"[{ts}] [Bus {bus}] Gagal update: {e}")

            if cmd_val != last_breaker[bus]:
                print(f"[{ts}] [Bus {bus}] Command breaker ke RTU: {'CLOSE' if cmd_val==1 else 'OPEN'}")
                last_breaker[bus] = cmd_val

        time.sleep(4)

except KeyboardInterrupt:
    print("Server dihentikan oleh user")
    server.stop()
