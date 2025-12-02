from opcua import Client
import time
import random

client = Client("opc.tcp://localhost:4840/")
client.connect()

# Namespace index server
idx = client.get_namespace_index("mininet-opcua")
print("Namespace index:", idx)

root = client.get_root_node()

#tegangan_nodes = client.get_node(f"ns={idx};s=SENSORS/V")
tegangan_nodes = root.get_child(["0:Objects",f"{idx}:SENSORS",f"{idx}:V"])

while True:
    # Data dummy untuk dikirimkan
    v = 1.0 + random.uniform(-0.05, 0.05)    

    tegangan_nodes.set_value(v)

    time.sleep(1)