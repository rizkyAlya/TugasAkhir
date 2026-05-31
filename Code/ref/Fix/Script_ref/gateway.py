"""
Gateway (h3): Modbus server untuk RTU + OPC UA ke DT.
Meneruskan V/I/PF/status switch field ke DT; meneruskan CMD DT ke RTU.
"""
import math
import os
import sys
import time
from datetime import datetime
from threading import Thread

from opcua import Server
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusSlaveContext
from pymodbus.server import StartTcpServer

MODBUS_LISTEN_IP = os.environ.get("MODBUS_LISTEN_IP", "0.0.0.0")
MODBUS_PORT = int(os.environ.get("MODBUS_PORT", "5020"))
OPC_ENDPOINT = os.environ.get("OPC_ENDPOINT", "opc.tcp://0.0.0.0:4840/mininet/")
LOOP_INTERVAL_S = float(os.environ.get("GATEWAY_LOOP_INTERVAL_S", "4"))

V_BASE_ADDR = 0
I_BASE_ADDR = 10
BREAKER_FB_BASE_ADDR = 20
PF_FB_BASE_ADDR = 30
BREAKER_CMD_BASE_ADDR = 0
DT_PATH_PROBE_ADDR = 95
V_SCALE = 1000
I_SCALE = 30
PF_SCALE = 10000
NUM_BUS = 5
V_BASE = 345e3

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
MITM_LOG_DIR = os.path.join(BASE_DIR, "logs", "mitm")
TRACE_CSV = os.path.join(MITM_LOG_DIR, "trace.csv")

try:
    sys.path.insert(0, BASE_DIR)
    from logger.mitm_trace_logger import (
        ATTACK_FLAG,
        append_trace_row,
        ensure_trace_csv,
        get_run_id,
        read_mitm_proxy_snapshot,
    )

    ensure_trace_csv(TRACE_CSV)
    _HAS_TRACE = True
except ImportError:
    _HAS_TRACE = False

server = Server()
server.set_endpoint(OPC_ENDPOINT)
idx = server.register_namespace("mininet-opcua")
objects = server.get_objects_node()
sensor_folder = objects.add_folder(idx, "SENSORS")
command_folder = objects.add_folder(idx, "COMMANDS")

p_nodes = {}
q_nodes = {}
v_dt_nodes = {}
brk_fb_nodes = {}
command_nodes = {}
last_breaker = {}

store = ModbusSlaveContext(
    di=ModbusSequentialDataBlock(0, [0] * 100),
    co=ModbusSequentialDataBlock(0, [1] * 100),
    hr=ModbusSequentialDataBlock(0, [0] * 100),
    ir=ModbusSequentialDataBlock(0, [0] * 100),
)
context = ModbusServerContext(slaves=store, single=True)


def start_modbus_server():
    print(f"Modbus gateway {MODBUS_LISTEN_IP}:{MODBUS_PORT}")
    StartTcpServer(context=context, identity=None, address=(MODBUS_LISTEN_IP, MODBUS_PORT))


def log_measurement(ts, waktu, bus, v_in, i_in, v_out, i_out, v_dt, breaker_cmd, breaker_fb):
    if not _HAS_TRACE:
        return
    if os.path.exists(ATTACK_FLAG):
        snap = read_mitm_proxy_snapshot(bus) or {}
        v_before = snap.get("v_before", f"{v_in:.6f}")
        v_after = snap.get("v_after", f"{v_out:.6f}")
        i_before = snap.get("i_before", f"{i_in:.6f}")
        i_after = snap.get("i_after", f"{i_out:.6f}")
    else:
        v_before, v_after = f"{v_in:.6f}", f"{v_out:.6f}"
        i_before, i_after = f"{i_in:.6f}", f"{i_out:.6f}"
    append_trace_row(
        TRACE_CSV,
        [ts, waktu, get_run_id(), bus, v_before, v_after, i_before, i_after,
         f"{v_dt:.6f}", breaker_cmd, breaker_fb],
    )


for bus in range(1, NUM_BUS + 1):
    p_nodes[bus] = sensor_folder.add_variable(idx, f"P_bus_{bus}", 0.0)
    p_nodes[bus].set_writable()
    q_nodes[bus] = sensor_folder.add_variable(idx, f"Q_bus_{bus}", 0.0)
    q_nodes[bus].set_writable()
    v_dt_nodes[bus] = sensor_folder.add_variable(idx, f"V_DT_bus_{bus}", 1.0)
    v_dt_nodes[bus].set_writable()
    brk_fb_nodes[bus] = sensor_folder.add_variable(idx, f"BRK_FB_bus_{bus}", 1)
    brk_fb_nodes[bus].set_writable()
    command_nodes[bus] = command_folder.add_variable(idx, f"CMD_bus_{bus}", 1)
    command_nodes[bus].set_writable()
    last_breaker[bus] = 1

dt_path_probe_node = sensor_folder.add_variable(idx, "DT_path_probe", 0)
dt_path_probe_node.set_writable()

print(f"OPC UA server {OPC_ENDPOINT}")
server.start()
Thread(target=start_modbus_server, daemon=True).start()

_gateway_iter = 0

try:
    while True:
        print("\n")
        _gateway_iter += 1
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for bus in range(1, NUM_BUS + 1):
            cmd_val = last_breaker[bus]
            try:
                v_raw = float(context[0x00].getValues(3, V_BASE_ADDR + bus - 1, count=1)[0]) / V_SCALE
                i_raw = float(context[0x00].getValues(3, I_BASE_ADDR + bus - 1, count=1)[0]) / I_SCALE
                pf_raw = float(context[0x00].getValues(3, PF_FB_BASE_ADDR + bus - 1, count=1)[0]) / PF_SCALE
                b_raw = int(context[0x00].getValues(3, BREAKER_FB_BASE_ADDR + bus - 1, count=1)[0])
                breaker_fb = 1 if b_raw == 1 else 0

                pf = min(1.0, max(1e-6, pf_raw))
                v_real = v_raw * V_BASE
                s_va = v_real * i_raw
                p_mw = (s_va * pf) / 1e6
                q_mvar = (s_va * math.sqrt(max(0.0, 1 - pf**2))) / 1e6

                p_nodes[bus].set_value(float(p_mw))
                q_nodes[bus].set_value(float(q_mvar))
                brk_fb_nodes[bus].set_value(int(breaker_fb))

                cmd = command_nodes[bus].get_value()
                cmd_val = 1 if int(cmd) == 1 else 0
                context[0x00].setValues(1, BREAKER_CMD_BASE_ADDR + bus - 1, [cmd_val])

                v_dt = float(v_dt_nodes[bus].get_value())
                log_measurement(
                    ts, _gateway_iter, bus, v_raw, i_raw, v_raw, i_raw,
                    v_dt, cmd_val, breaker_fb,
                )
                print(
                    f"[{ts}] iter={_gateway_iter} bus={bus} "
                    f"V={v_raw:.4f} I={i_raw:.4f} PF={pf:.4f} BRK_FB={breaker_fb} "
                    f"P={p_mw:.4f} Q={q_mvar:.4f} CMD={cmd_val} V_DT={v_dt:.4f}"
                )
            except Exception as exc:
                print(f"[{ts}] bus {bus} error: {exc}")

            if cmd_val != last_breaker[bus]:
                print(f"[{ts}] bus {bus} CMD ke RTU: {'CLOSE' if cmd_val else 'OPEN'}")
                last_breaker[bus] = cmd_val

        try:
            dt_path_probe_node.set_value(int(context[0x00].getValues(3, DT_PATH_PROBE_ADDR, count=1)[0]))
        except Exception as exc:
            print(f"[{ts}] DT_path_probe sync: {exc}")

        time.sleep(LOOP_INTERVAL_S)

except KeyboardInterrupt:
    print("Gateway dihentikan")
    server.stop()
