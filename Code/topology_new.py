#!/usr/bin/python

from mininet.net import Mininet
from mininet.node import Controller, OVSSwitch, Node
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel

def addRouter(net, name):
    """Add a router host with IP forwarding enabled"""
    r = net.addHost(name, cls=Node)
    r.cmd('sysctl -w net.ipv4.ip_forward=1')
    return r

def CPS_topology_reachable():
    net = Mininet(controller=Controller, link=TCLink, switch=OVSSwitch)

    print("*** Adding controller")
    net.addController('c0')

    print("*** Adding hosts with static IPs")
    # Field Zone
    h1 = net.addHost('h1', ip='10.0.1.2/24')  # Field Device
    h2 = net.addHost('h2', ip='10.0.1.3/24')  # RTU
    # Control Zone
    h3 = net.addHost('h3', ip='10.0.2.2/24')  # SCADA Gateway
    # IT Zone
    h4 = net.addHost('h4', ip='10.0.3.2/24')  # Digital Twin
    h5 = net.addHost('h5', ip='10.0.3.3/24')  # Attacker

    print("*** Adding switches")
    switch_field = net.addSwitch('s1')
    switch_control = net.addSwitch('s2')
    switch_it = net.addSwitch('s3')
    core_switch = net.addSwitch('s4')

    print("*** Adding router")
    r0 = addRouter(net, 'r0')

    print("*** Creating links")
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

    print("*** Starting network")
    net.start()

    print("*** Configuring router interfaces")
    # Assign router IPs per subnet
    r0.cmd('ifconfig r0-eth0 10.0.1.1/24 up')  # Field Zone
    r0.cmd('ifconfig r0-eth1 10.0.2.1/24 up')  # Control Zone
    r0.cmd('ifconfig r0-eth2 10.0.3.1/24 up')  # IT Zone

    print("*** Setting default routes on hosts")
    # Field Zone
    h1.cmd('ip route add default via 10.0.1.1')
    h2.cmd('ip route add default via 10.0.1.1')
    # Control Zone
    h3.cmd('ip route add default via 10.0.2.1')
    # IT Zone
    h4.cmd('ip route add default via 10.0.3.1')
    h5.cmd('ip route add default via 10.0.3.1')

    print("*** Network ready. You can test ping between hosts.")
    CLI(net)

    print("*** Stopping network")
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    CPS_topology_reachable()
