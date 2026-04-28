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
command_nodes = {}

for bus in range(1, 6):
    p_nodes[bus] = root.get_child(["0:Objects", f"{idx}:SENSORS", f"{idx}:P_bus_{bus}"])
    q_nodes[bus] = root.get_child(["0:Objects", f"{idx}:SENSORS", f"{idx}:Q_bus_{bus}"])
    command_nodes[bus] = root.get_child(["0:Objects", f"{idx}:COMMANDS", f"{idx}:CMD_bus_{bus}"])

bus_map = {i+1: i for i in range(5)}
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
open_factor = 1.00   # Open jika I_line > max_i_ka * open_factor
close_factor = 0.95  # Close jika I_line < max_i_ka * close_factor

while True:
    for bus in range(1, 6):
        p_mw = p_nodes[bus].get_value()
        q_mvar = q_nodes[bus].get_value()

        idx_pp = bus_map[bus]

        # Gunakan idx_pp agar mapping bus ekuivalen konsisten.
        if idx_pp in net.load.bus.values:
            load_idx = net.load[net.load.bus == idx_pp].index
            if len(load_idx):
                net.load.loc[load_idx, "p_mw"] = float(p_mw)
                net.load.loc[load_idx, "q_mvar"] = float(q_mvar)

    try:
        pp.runpp(net)
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
            print(f"Bus {bus}: breaker OPEN (line {line_idx}) | I_line={i_line_ka:.4f} kA, I_open={i_open_ka:.4f} kA")
        elif cmd == 1:
            net.line.loc[line_idx, "in_service"] = True
            line_status[line_idx] = True
            print(f"Bus {bus}: breaker CLOSE (line {line_idx}) | I_line={i_line_ka:.4f} kA, I_close={i_close_ka:.4f} kA")

    time.sleep(4)
