from opcua import Server
import time
from datetime import datetime

# Konfigurasi server
server = Server()
server.set_endpoint("opc.tcp://10.0.2.2:4840/mininet/")

uri = "mininet-opcua"
idx = server.register_namespace(uri)

objects = server.get_objects_node()

sensor_folder = objects.add_folder(idx, "SENSORS")
command_folder = objects.add_folder(idx, "COMMANDS")

# nodes untuk OPC UA
tegangan_nodes = {}
arus_nodes = {}
command_nodes = {}

last_breaker = {}     # Simpan nilai terkahir breaker untuk track update

for bus in range(1, 6):  
    tegangan_nodes[bus] = sensor_folder.add_variable(idx, f"V_bus_{bus}", 0.0)
    tegangan_nodes[bus].set_writable()

    arus_nodes[bus] = sensor_folder.add_variable(idx, f"I_bus_{bus}", 0.0)
    arus_nodes[bus].set_writable()

    command_nodes[bus] = command_folder.add_variable(idx, f"CMD_bus_{bus}", 0)
    command_nodes[bus].set_writable()

    last_breaker[bus] = 0  # default: breaker terbuka

print("Memulai Server OPC UA")
server.start()

try:
    while True:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for bus in range(1, 6):
            # Periksa V/I
            try:
                v = tegangan_nodes[bus].get_value()
                i = arus_nodes[bus].get_value()
                cmd = command_nodes[bus].get_value()
                print(f"[{ts}] [Bus {bus}] Data V/I/breaker berhasil update")
            except Exception as e:
                print(f"[{ts}] [Bus {bus}] Gagal update: {e}")

            # Periksa status breaker
            if cmd != last_breaker[bus]:
                print(f"[{ts}] [Bus {bus}] Status breaker diperbarui ke: {'CLOSE' if cmd==1 else 'OPEN'}")
                last_breaker[bus] = cmd

        time.sleep(1)

except KeyboardInterrupt:
    print("Server dihentikan oleh user")
    server.stop()
