from opcua import Client
import time
import random

client = Client("opc.tcp://localhost:4840/mininet/")
client.connect()

# Namespace index server
idx = client.get_namespace_index("mininet-opcua")
print("Namespace index:", idx)

root = client.get_root_node()

# Get node maps
tegangan_nodes = {}
arus_nodes = {}
command_nodes = {}

for bus in range(1, 6):
    tegangan_nodes[bus] = root.get_child(["0:Objects",f"{idx}:SENSORS",f"{idx}:V_bus_{bus}"])
    arus_nodes[bus] = root.get_child(["0:Objects",f"{idx}:SENSORS",f"{idx}:I_bus_{bus}"])
    command_nodes[bus] = root.get_child(["0:Objects",f"{idx}:COMMANDS",f"{idx}:CMD_bus_{bus}"])

while True:
    for bus in range(1, 6):
        # Data dummy untuk dikirimkan
        v = 1.0 + random.uniform(-0.05, 0.05)    
        i = random.uniform(0.1, 2.0)

        try:
            tegangan_nodes[bus].set_value(v)
            arus_nodes[bus].set_value(i)
        except Exception as e:
            print("Error:", e)

        # Mengambil perintah dari PandaPower
        cmd = command_nodes[bus].get_value()
        if cmd == 1:
            print(f"Bus {bus} menerima command: breaker OPEN")
        elif cmd == 2:
            print(f"Bus {bus} menerima command: breaker CLOSE")
        else:
            print(f"Bus {bus} menerima command: NORMAL")

    time.sleep(5)