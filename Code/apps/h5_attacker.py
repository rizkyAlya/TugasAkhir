def run_dos_attack(net, mode="light"):

    h5 = net.get('h5')
    target_ip = "10.0.2.2" # h2 (gateway)

    # Hentikan serangan sebelumnya
    h5.cmd("pkill -f iperf")

    if mode == "light":
        print("Running LIGHT DoS (10 Mbps UDP flood)")
        h5.cmd(f"iperf -c {target_ip} -u -b 10M -t 30 &")

    elif mode == "heavy":
        print("Running HEAVY DoS (100 Mbps UDP flood)")
        h5.cmd(f"iperf -c {target_ip} -u -b 100M -t 30 &")
