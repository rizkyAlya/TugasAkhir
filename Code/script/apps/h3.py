import json
import os
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Lock, Thread

from opcua import Server
from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.datastore import ModbusSequentialDataBlock

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
INJECT_ENABLE_FLAG = "/tmp/h3_http_inject_enabled"
INJECT_API_IP = "0.0.0.0"
INJECT_API_PORT = 8088
INJECT_API_TOKEN = "lab-sim-token"
MAX_TTL_SECONDS = 30

store = ModbusSlaveContext(
    di=ModbusSequentialDataBlock(0, [0] * 100),
    co=ModbusSequentialDataBlock(0, [1] * 100),
    hr=ModbusSequentialDataBlock(0, [0] * 100),
    ir=ModbusSequentialDataBlock(0, [0] * 100),
)
context = ModbusServerContext(slaves=store, single=True)
override_lock = Lock()
overrides = {}
inject_api_started = False

def start_modbus_server():
    print(f"Memulai Modbus Gateway di {MODBUS_LISTEN_IP}:{MODBUS_PORT}")
    StartTcpServer(context=context, identity=None, address=(MODBUS_LISTEN_IP, MODBUS_PORT))


def _json_response(handler, code, payload):
    data = json.dumps(payload).encode("utf-8")
    handler.send_response(code)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(data)))
    handler.end_headers()
    handler.wfile.write(data)


def _get_active_override(bus):
    now = time.time()
    with override_lock:
        item = overrides.get(bus)
        if not item:
            return None
        if item["expires_at"] <= now:
            overrides.pop(bus, None)
            return None
        return item


def _clear_override(bus=None):
    with override_lock:
        if bus is None:
            overrides.clear()
        else:
            overrides.pop(bus, None)


class InjectHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        return

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception:
            _json_response(self, 400, {"ok": False, "error": "invalid json"})
            return

        token = str(payload.get("token", ""))
        if token != INJECT_API_TOKEN:
            _json_response(self, 403, {"ok": False, "error": "unauthorized"})
            return

        if self.path == "/inject":
            try:
                bus = int(payload["bus"])
                v = float(payload["v"])
                i = float(payload["i"])
                ttl = int(payload.get("ttl", 8))
            except Exception:
                _json_response(self, 400, {"ok": False, "error": "invalid payload"})
                return

            if bus < 1 or bus > NUM_BUS:
                _json_response(self, 400, {"ok": False, "error": "bus out of range"})
                return

            ttl = max(1, min(ttl, MAX_TTL_SECONDS))
            with override_lock:
                overrides[bus] = {
                    "v": v,
                    "i": i,
                    "expires_at": time.time() + ttl,
                }
            _json_response(self, 200, {"ok": True, "bus": bus, "ttl": ttl})
            return

        if self.path == "/clear":
            bus = payload.get("bus")
            if bus is None:
                _clear_override()
            else:
                try:
                    _clear_override(int(bus))
                except Exception:
                    _json_response(self, 400, {"ok": False, "error": "invalid bus"})
                    return
            _json_response(self, 200, {"ok": True})
            return

        _json_response(self, 404, {"ok": False, "error": "not found"})


def start_inject_api():
    print(f"HTTP inject API aktif di {INJECT_API_IP}:{INJECT_API_PORT}")
    httpd = ThreadingHTTPServer((INJECT_API_IP, INJECT_API_PORT), InjectHandler)
    httpd.serve_forever()


def maybe_start_inject_api():
    global inject_api_started
    if inject_api_started:
        return
    if os.path.exists(INJECT_ENABLE_FLAG):
        t_http = Thread(target=start_inject_api, daemon=True)
        t_http.start()
        inject_api_started = True

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
        maybe_start_inject_api()
        print("\n")
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for bus in range(1, NUM_BUS + 1):
            cmd_val = last_breaker[bus]
            try:
                # 1) Ambil data dari RTU melalui Modbus
                addr_v = V_BASE_ADDR + (bus - 1)
                addr_i = I_BASE_ADDR + (bus - 1)
                addr_b = BREAKER_FB_BASE_ADDR + (bus - 1)
                v_raw = context[0x00].getValues(3, addr_v, count=1)[0]
                i_raw = context[0x00].getValues(3, addr_i, count=1)[0]
                b_raw = context[0x00].getValues(3, addr_b, count=1)[0]

                v = float(v_raw) / 1000.0
                i = float(i_raw) / 1000.0
                breaker_fb = 1 if int(b_raw) == 1 else 0
                source = "RTU"

                override = _get_active_override(bus)
                if override is not None:
                    v = float(override["v"])
                    i = float(override["i"])
                    source = "SIMULATED"

                # 2) Publish ke OPC UA untuk pandapower (V/I)
                tegangan_nodes[bus].set_value(v)
                arus_nodes[bus].set_value(i)

                # 3) Ambil command dari OPC UA lalu tulis ke Modbus coil untuk RTU
                cmd = command_nodes[bus].get_value()
                cmd_val = 1 if int(cmd) == 1 else 0
                context[0x00].setValues(1, BREAKER_CMD_BASE_ADDR + (bus - 1), [cmd_val])

                print(f"[{ts}] [Bus {bus}] Data V/I/CMD update ({source})")
            except Exception as e:
                print(f"[{ts}] [Bus {bus}] Gagal update: {e}")

            if cmd_val != last_breaker[bus]:
                print(f"[{ts}] [Bus {bus}] Command breaker ke RTU: {'CLOSE' if cmd_val==1 else 'OPEN'}")
                last_breaker[bus] = cmd_val

        time.sleep(4)

except KeyboardInterrupt:
    print("Server dihentikan oleh user")
    server.stop()
