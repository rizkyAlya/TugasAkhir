from opcua import Client
import pandapower.networks as pn
import pandapower as pp
import time
from datetime import datetime

# Menggunakan Panda Power IEEE 39 Bus
net = pn.case39()

client = Client("opc.tcp://10.0.2.2:4840/mininet/")
client.connect()

# Namespace index server
idx = client.get_namespace_index("mininet-opcua")
print("Namespace index:", idx)

root = client.get_root_node()

# OPC UA nodes
tegangan_nodes = {}
arus_nodes = {}
command_nodes = {}

# Pointer buat tiap variabel yang ada di OPC UA server
for bus in range(1, 6):
    tegangan_nodes[bus] = root.get_child(["0:Objects",f"{idx}:SENSORS",f"{idx}:V_bus_{bus}"])
    arus_nodes[bus] = root.get_child(["0:Objects",f"{idx}:SENSORS",f"{idx}:I_bus_{bus}"])
    command_nodes[bus] = root.get_child(["0:Objects",f"{idx}:COMMANDS",f"{idx}:CMD_bus_{bus}"])

# Mapping untuk index tiap bus, karena beda index antara OPC UA (1-39) dan PandaPower(0-38)
bus_map = {i+1: i for i in range(5)}   

# Mapping dan status untuk bus line (untuk simulasi breaker nanti)
bus_line = {i+1: i for i in range(len(net.line))}
line_status = {idx: True for idx in range(len(net.line))} # True: tutup; False: buka

while True:
    # Baca semua sensor dari mininet yang disimpan di OPC UA server
    for bus in range(1, 6):
        v = tegangan_nodes[bus].get_value()
        i = arus_nodes[bus].get_value()

        # Update nilai di tiap bus
        idx = bus_map[bus]
        net.bus.loc[idx, "vm_pu"] = v

        # Update load, agar realistis, karena load berubah sesuai kondisi lapangan
        if bus in net.load.bus.values:
            load_idx = net.load[net.load.bus == idx].index
            if len(load_idx):
                net.load.loc[load_idx, "p_mw"] = float(i) * 0.1
                net.load.loc[load_idx, "q_mvar"] = float(i) * 0.05

    # Run load flow (perhitungan ulang distribusi di 39 bus)
    try:
        pp.runpp(net)
        print("\n", datetime.now().isoformat())
        print("Load flow sukses. Voltage snapshot:", net.res_bus.vm_pu.values[:5])
    except:
        print("Load flow gagal")

    # Mengirim perintah ke mininet melalui OPC UA server
    for bus in range(1, 6):
        idx = bus_map[bus]
        v = net.res_bus.vm_pu.loc[idx]
        line_idx = bus_line.get(bus, None)

        if line_idx is None:
            continue

        if v > 1.02:
            cmd = 0 # Buka breaker
        else:
            cmd = 1 # Tutup breaker
        
        command_nodes[bus].set_value(cmd) # Kirim perintah

        # Terapkan perubahan di PandaPower
        if cmd == 0:
            net.line.loc[line_idx, "in_service"] = False
            line_status[line_idx] = False
            print(f"Bus {bus}: breaker OPEN (line {line_idx})")
        elif cmd == 1:
            net.line.loc[line_idx, "in_service"] = True
            line_status[line_idx] = True
            print(f"Bus {bus}: breaker CLOSE (line {line_idx})")

    time.sleep(4)