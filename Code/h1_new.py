import time
from datetime import datetime
import random
from threading import Thread

from pymodbus.server import StartTcpServer
from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.datastore import ModbusSequentialDataBlock

# Konfigurasi Modbus
MODBUS_LISTEN_IP = "0.0.0.0"
MODBUS_PORT = 5020

NUM_BUS = 5

# Mapping register Modbus
V_BASE_ADDR = 0         # HR 0-4
I_BASE_ADDR = 10        # HR 10-14
BREAKER_BASE_ADDR = 0   # Coil 0-4

# Datastore modbus
store = ModbusSlaveContext(
    di=ModbusSequentialDataBlock(0, [0] * 100),     # Discrete Inputs
    co=ModbusSequentialDataBlock(0, [0] * 100),     # Coils
    hr=ModbusSequentialDataBlock(0, [0] * 100),     # Holding Registers
    ir=ModbusSequentialDataBlock(0, [0] * 100),     # Input Registers
)
context = ModbusServerContext(slaves=store, single=True)

# Breaker status (kondisi awal: tertutup, selanjutnya menyesuaikan dengan nilai dari Digital Twin)
breaker_status = {bus: 1 for bus in range(1, NUM_BUS+1)}

# Sinkronisasi awal 
for bus in range (1, NUM_BUS+1):
    addr_breaker = BREAKER_BASE_ADDR + (bus-1)
    context[0x00].setValues(1, addr_breaker, [breaker_status[bus]])

# Fungsi update status breaker (manual)
def update_breaker(bus, status):
    breaker_status[bus] = status
    context[0x00].setValues(1, BREAKER_BASE_ADDR + (bus-1), [status])

# Modbus Server
def start_modbus_server():
    print(f"Starting Modbus TCP server on {MODBUS_LISTEN_IP}:{MODBUS_PORT}")
    StartTcpServer(context=context, identity=None, address=(MODBUS_LISTEN_IP, MODBUS_PORT))

# Fungsi update Data
def main_loop():
    slave_id = 0x00   # karena single=True
    fx_hr = 3         # 3 = Holding Register
    fx_co = 1         # 1 = Coils

    try:
        while True:
            print("\n", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            for bus in range(1, NUM_BUS + 1):
                addr_v = V_BASE_ADDR + (bus - 1)
                addr_i = I_BASE_ADDR + (bus - 1)
                addr_breaker = BREAKER_BASE_ADDR + (bus - 1)
        
                # 1) Baca status breaker terbaru dari coil Modbus (update dari H2)
                current_breaker = context[slave_id].getValues(fx_co, addr_breaker, count=1)[0]
                breaker_status[bus] = current_breaker
        
                # 2) Generate data dummy
                v = 1.0 + random.uniform(-0.05, 0.05)
                i = random.uniform(0.1, 2.0)
                v_scaled = int(v * 1000)
                i_scaled = int(i * 1000)
        
                # 3) Tulis V/I ke Holding Register
                try:
                    context[slave_id].setValues(fx_hr, addr_v, [v_scaled])
                    context[slave_id].setValues(fx_hr, addr_i, [i_scaled])
                    print(f"Bus {bus} | V={v_scaled} | I={i_scaled} | Breaker={'OPEN' if breaker_status[bus]==0 else 'CLOSE'}")
                except Exception as e:
                    print("Error update Modbus datastore:", e)
        
            time.sleep(5)


    except KeyboardInterrupt:
        print("Stopped by User")


# Entry point
if __name__ == "__main__":
    # Mulai Modbus server
    t = Thread(target=start_modbus_server, daemon=True)
    t.start()

    # Update data loop
    main_loop()
