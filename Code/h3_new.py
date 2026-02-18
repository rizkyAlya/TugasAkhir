from opcua import Server
import time

server = Server()
server.set_endpoint("opc.tcp://10.0.2.2:4840/mininet/")

uri = "mininet-opcua"
idx = server.register_namespace(uri)

objects = server.get_objects_node()

sensor_folder = objects.add_folder(idx, "SENSORS")
command_folder = objects.add_folder(idx, "COMMANDS")

# Membuat node untuk 39 bus -> sekarang 5 bus dulu
tegangan_nodes = {}
arus_nodes = {}
command_nodes = {}

for bus in range(1, 6):  
    tegangan_nodes[bus] = sensor_folder.add_variable(idx, f"V_bus_{bus}", 0.0)
    tegangan_nodes[bus].set_writable()

    arus_nodes[bus] = sensor_folder.add_variable(idx, f"I_bus_{bus}", 0.0)
    arus_nodes[bus].set_writable()

    command_nodes[bus] = command_folder.add_variable(idx, f"CMD_bus_{bus}", 0)
    command_nodes[bus].set_writable()

print("Memulai Server OPC UA")
server.start()

try:
    while True:
        time.sleep(1)
except:
    server.stop()