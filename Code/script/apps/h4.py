from opcua import Client
import pandapower.networks as pn
import pandapower as pp
import time
from datetime import datetime

# Menggunakan Panda Power IEEE 39 Bus
net = pn.case39()

client = Client("opc.tcp://10.0.2.2:4840/mininet/")
client.connect()

idx = client.get_namespace_index("mininet-opcua")
print("Namespace index:", idx)

root = client.get_root_node()

p_nodes = {}
q_nodes = {}
v_dt_nodes = {}
command_nodes = {}

for bus in range(1, 6):
    p_nodes[bus] = root.get_child(["0:Objects", f"{idx}:SENSORS", f"{idx}:P_bus_{bus}"])
    q_nodes[bus] = root.get_child(["0:Objects", f"{idx}:SENSORS", f"{idx}:Q_bus_{bus}"])
    v_dt_nodes[bus] = root.get_child(["0:Objects", f"{idx}:SENSORS", f"{idx}:V_DT_bus_{bus}"])
    command_nodes[bus] = root.get_child(["0:Objects", f"{idx}:COMMANDS", f"{idx}:CMD_bus_{bus}"])

dt_path_probe_node = root.get_child(["0:Objects", f"{idx}:SENSORS", f"{idx}:DT_path_probe"])
_last_dt_probe = -1

# Map field bus -> pandapower bus yang memiliki elemen load
# (dipilih dari set load_buses case39 agar update p_mw/q_mvar selalu masuk)
bus_map = {
    1: 0,
    2: 2,
    3: 3,
    4: 6,
    5: 7,
}
print("Field bus -> Pandapower bus mapping:", bus_map)

# Mapping breaker per bus berdasarkan line yang benar-benar terhubung
bus_line = {}
used_lines = set()
for bus, idx_pp in bus_map.items():
    connected_lines = net.line[(net.line.from_bus == idx_pp) | (net.line.to_bus == idx_pp)].index.tolist()
    selected_line = None
    for line_idx in connected_lines:
        if line_idx not in used_lines:
            selected_line = line_idx
            used_lines.add(line_idx)
            break
    bus_line[bus] = selected_line

print("Unique bus->line mapping:", bus_line)

line_status = {idx: True for idx in range(len(net.line))}
open_factor = 0.6   # Open jika I_line > max_i_ka * open_factor
close_factor = 0.55  # Close jika I_line < max_i_ka * close_factor
ema_alpha = 0.35     # smoothing input P/Q agar tegangan tidak terlalu berosilasi
p_ema = {}
q_ema = {}

while True:
    try:
        probe = int(dt_path_probe_node.get_value())
        if probe != _last_dt_probe:
            print(f"DT_PATH_LAT,h4,{time.time():.6f},{probe}", flush=True)
            _last_dt_probe = probe
    except Exception as e:
        print(f"DT_path_probe read: {e}")

    for bus in range(1, 6):
        p_in = float(p_nodes[bus].get_value())
        q_in = float(q_nodes[bus].get_value())

        if bus not in p_ema:
            p_ema[bus] = p_in
            q_ema[bus] = q_in
        else:
            p_ema[bus] = (ema_alpha * p_in) + ((1 - ema_alpha) * p_ema[bus])
            q_ema[bus] = (ema_alpha * q_in) + ((1 - ema_alpha) * q_ema[bus])

        idx_pp = bus_map[bus]

        load_idx = net.load[net.load.bus == idx_pp].index.tolist()
        if len(load_idx):
            net.load.loc[load_idx, "p_mw"] = p_ema[bus] # MW
            net.load.loc[load_idx, "q_mvar"] = q_ema[bus] # MVar

    try:
        pp.runpp(net)
        for bus in range(1, 6):
            idx_pp = bus_map[bus]
            v_dt_nodes[bus].set_value(float(net.res_bus.vm_pu.loc[idx_pp]))
        print("\n", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("Load flow sukses. Voltage snapshot (pu):", net.res_bus.vm_pu.values[:5])
    except Exception:
        print("Load flow gagal")

    for bus in range(1, 6):
        idx_pp = bus_map[bus]
        line_idx = bus_line.get(bus, None)

        if line_idx is None:
            print(f"Bus {bus}: tidak ada line terhubung untuk kontrol breaker")
            continue

        i_from_ka = abs(float(net.res_line.i_from_ka.loc[line_idx]))
        i_to_ka = abs(float(net.res_line.i_to_ka.loc[line_idx]))
        i_line_ka = max(i_from_ka, i_to_ka)
        i_open_ka = float(net.line.max_i_ka.loc[line_idx]) * open_factor
        i_close_ka = float(net.line.max_i_ka.loc[line_idx]) * close_factor
        line_is_closed = bool(line_status.get(line_idx, True))

        # Hysteresis:
        # - Jika line sedang CLOSE, hanya OPEN saat melebihi batas open
        # - Jika line sedang OPEN, hanya CLOSE saat turun di bawah batas close
        if line_is_closed:
            cmd = 0 if i_line_ka > i_open_ka else 1
        else:
            cmd = 1 if i_line_ka < i_close_ka else 0
        command_nodes[bus].set_value(cmd)

        if cmd == 0:
            net.line.loc[line_idx, "in_service"] = False
            line_status[line_idx] = False
        elif cmd == 1:
            net.line.loc[line_idx, "in_service"] = True
            line_status[line_idx] = True

        vm_pu = float(net.res_bus.vm_pu.loc[idx_pp])
        max_i = float(net.line.max_i_ka.loc[line_idx])
        in_svc_after = bool(net.line.loc[line_idx, "in_service"])
        ts_row = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"[h4] {ts_row} bus={bus} line={line_idx} pp_bus={idx_pp} | "
            f"i_from={i_from_ka:.4f} i_to={i_to_ka:.4f} i_line={i_line_ka:.4f} kA | "
            f"max_i={max_i:.4f} thr_open={i_open_ka:.4f} thr_close={i_close_ka:.4f} | "
            f"was_closed={line_is_closed} cmd={cmd} in_svc={in_svc_after} | "
            f"vm_pu={vm_pu:.4f} P_ema={p_ema[bus]:.4f} Q_ema={q_ema[bus]:.4f}",
            flush=True,
        )

    time.sleep(4)