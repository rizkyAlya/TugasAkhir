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
bus_line = {i+1: i for i in range(len(net.line))}
line_status = {idx: True for idx in range(len(net.line))}

while True:
    for bus in range(1, 6):
        p_mw = p_nodes[bus].get_value()
        q_mvar = q_nodes[bus].get_value()

        idx_pp = bus_map[bus]

        if bus in net.load.bus.values:
            load_idx = net.load[net.load.bus == idx_pp].index
            if len(load_idx):
                net.load.loc[load_idx, "p_mw"] = float(p_mw)
                net.load.loc[load_idx, "q_mvar"] = float(q_mvar)

    try:
        pp.runpp(net)
        print("\n", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        print("Load flow sukses. Voltage snapshot:", net.res_bus.vm_pu.values[:5])
    except Exception:
        print("Load flow gagal")

    for bus in range(1, 6):
        idx_pp = bus_map[bus]
        v = net.res_bus.vm_pu.loc[idx_pp]
        line_idx = bus_line.get(bus, None)

        if line_idx is None:
            continue

        cmd = 0 if v > 1.02 else 1
        command_nodes[bus].set_value(cmd)

        if cmd == 0:
            net.line.loc[line_idx, "in_service"] = False
            line_status[line_idx] = False
            print(f"Bus {bus}: breaker OPEN (line {line_idx})")
        elif cmd == 1:
            net.line.loc[line_idx, "in_service"] = True
            line_status[line_idx] = True
            print(f"Bus {bus}: breaker CLOSE (line {line_idx})")

    time.sleep(4)
