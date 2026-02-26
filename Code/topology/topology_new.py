from mininet.net import Mininet
from mininet.node import Controller, OVSSwitch, Node
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel

import time
import os

def addRouter(net, name):
    r = net.addHost(name, cls=Node)
    r.cmd('sysctl -w net.ipv4.ip_forward=1')
    return r

def CPS_topology():
    net = Mininet(controller=Controller, link=TCLink, switch=OVSSwitch)

    print("Adding controller")
    net.addController('c0')

    print("Adding hosts")
    # Field Zone
    h1 = net.addHost('h1', ip='10.0.1.2/24')  # Field Device
    h2 = net.addHost('h2', ip='10.0.1.3/24')  # RTU
    # Control Zone
    h3 = net.addHost('h3', ip='10.0.2.2/24')  # SCADA Gateway
    # IT Zone
    h4 = net.addHost('h4', ip='10.0.3.2/24')  # Digital Twin
    h5 = net.addHost('h5', ip='10.0.3.3/24')  # Attacker

    print("Adding switches")
    switch_field = net.addSwitch('s1')
    switch_control = net.addSwitch('s2')
    switch_it = net.addSwitch('s3')
    core_switch = net.addSwitch('s4')

    print("Adding router")
    r0 = addRouter(net, 'r0')

    print("Creating links")
    # Field Zone
    net.addLink(h1, switch_field)
    net.addLink(h2, switch_field)
    net.addLink(switch_field, core_switch)
    net.addLink(r0, switch_field)  # connect router to Field Zone

    # Control Zone
    net.addLink(h3, switch_control)
    net.addLink(switch_control, core_switch)
    net.addLink(r0, switch_control)  # connect router to Control Zone

    # IT Zone
    net.addLink(h4, switch_it)
    net.addLink(h5, switch_it)
    net.addLink(switch_it, core_switch)
    net.addLink(r0, switch_it)  # connect router to IT Zone

    print("Starting network")
    net.start()

    print("\nConfiguring router interfaces")
    # Assign router IPs per subnet
    r0.cmd('ifconfig r0-eth0 10.0.1.1/24 up')  # Field Zone
    r0.cmd('ifconfig r0-eth1 10.0.2.1/24 up')  # Control Zone
    r0.cmd('ifconfig r0-eth2 10.0.3.1/24 up')  # IT Zone

    print("Setting default routes on hosts")
    # Field Zone
    h1.cmd('ip route add default via 10.0.1.1')
    h2.cmd('ip route add default via 10.0.1.1')
    # Control Zone
    h3.cmd('ip route add default via 10.0.2.1')
    # IT Zone
    h4.cmd('ip route add default via 10.0.3.1')
    h5.cmd('ip route add default via 10.0.3.1')

    print("\nWaiting for network stabilization...")
    time.sleep(5)
    print("Network ready")

    # Running host application
    print("\nStarting host applications...")
    
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

    h1.cmd(f'python3 -u {base_dir}/apps/h1_field.py > {base_dir}/logs/h1.log 2>&1 &')
    h3.cmd(f'python3 -u {base_dir}/apps/h3_gateway.py > {base_dir}/logs/h3.log 2>&1 &')
    time.sleep(2)
    h2.cmd(f'python3 -u {base_dir}/apps/h2_rtu.py > {base_dir}/logs/h2.log 2>&1 &')
    h4.cmd(f'python3 -u {base_dir}/apps/h4_twin.py > {base_dir}/logs/h4.log 2>&1 &')

    print("All applications started.")
    
    CLI(net)

    print("Stopping network")
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    CPS_topology()
