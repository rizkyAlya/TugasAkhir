from pymodbus.client import ModbusTcpClient
import time
import csv
from datetime import datetime

H1_IP = "10.0.0.101"  # IP h1 mininet
MODBUS_PORT = 5020

V_BASE_ADDR = 0
I_BASE_ADDR = 10
NUM_BUS = 5

client = ModbusTcpClient(H1_IP, port=MODBUS_PORT)
client.connect()

with open("log_modbus_h2.csv", "a", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["timestamp", "bus", "V(pu)", "I(pu)"])

    try:
        while True:
            ts = datetime.now().isoformat()

            for bus in range(1, NUM_BUS + 1):
                addr_v = V_BASE_ADDR + (bus - 1)
                addr_i = I_BASE_ADDR + (bus - 1)

                rr_v = client.read_holding_registers(addr_v, 1, unit=1)
                rr_i = client.read_holding_registers(addr_i, 1, unit=1)

                if rr_v.isError() or rr_i.isError():
                    print("Error baca Modbus bus", bus)
                    continue

                v_scaled = rr_v.registers[0]
                i_scaled = rr_i.registers[0]

                v = v_scaled / 1000.0
                i = i_scaled / 1000.0

                print(f"[{ts}] bus {bus}: V={v:.3f} pu, I={i:.3f}")
                writer.writerow([ts, bus, v, i])

            f.flush()
            time.sleep(5)

    except KeyboardInterrupt:
        print("Logger dihentikan.")

    finally:
        client.close()
