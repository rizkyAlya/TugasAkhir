from opcua import Server
import time

server = Server()
server.set_endpoint("opc.tcp://0.0.0.0:4840/")

uri = "mininet-opcua"
idx = server.register_namespace(uri)

objects = server.get_objects_node()

sensor_folder = objects.add_folder(idx, "SENSORS")

tegangan_nodes = sensor_folder.add_variable(idx, "V", 0.0)
tegangan_nodes.set_writable()

print("Memulai Server OPC UA")
server.start()

try:
    while True:
        time.sleep(1)
except:
    server.stop()