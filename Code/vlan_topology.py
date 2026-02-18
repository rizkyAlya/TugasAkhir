from mininet.net import Mininet
from mininet.node import Controller, OVSSwitch, Node
from mininet.cli import CLI
from mininet.link import TCLink
from mininet.log import setLogLevel

def addRouter(net, name):
    r = net.addHost(name, cls=Node)
    r.cmd('sysctl -w net.ipv4.ip_forward=1')  # enable IP forwarding
    return r

def CPS_topology_vlan():
    net = Mininet(controller=Controller, link=TCLink, switch=OVSSwitch)

    print("Adding controller")
    net.addController('c0')

    print("Adding hosts")
    # Field Zone VLAN 10
    h1 = net.addHost('h1', ip='10.0.1.2/24')
    h2 = net.addHost('h2', ip='10.0.1.3/24')
    # Control Zone VLAN 20
    h3 = net.addHost('h3', ip='10.0.2.2/24')
    # IT Zone VLAN 30
    h4 = net.addHost('h4', ip='10.0.3.2/24')
    h5 = net.addHost('h5', ip='10.0.3.3/24')

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
    net.addLink(switch_field, core_switch)  # link to core

    # Control Zone
    net.addLink(h3, switch_control)
    net.addLink(switch_control, core_switch)  # link to core

    # IT Zone
    net.addLink(h4, switch_it)
    net.addLink(h5, switch_it)
    net.addLink(switch_it, core_switch)  # link to core

    # Router to core switch
    net.addLink(r0, core_switch)  # r0-eth0

    print("Starting network")
    net.start()

    print("Configuring router VLAN subinterfaces")
    # Subinterface VLAN
    r0.cmd('ip link add link r0-eth0 name r0-eth0.10 type vlan id 10')
    r0.cmd('ip link add link r0-eth0 name r0-eth0.20 type vlan id 20')
    r0.cmd('ip link add link r0-eth0 name r0-eth0.30 type vlan id 30')

    r0.cmd('ifconfig r0-eth0.10 10.0.1.1/24 up')
    r0.cmd('ifconfig r0-eth0.20 10.0.2.1/24 up')
    r0.cmd('ifconfig r0-eth0.30 10.0.3.1/24 up')

    print("Configuring core switch trunk VLAN")
    # Assign VLAN tags ke port yang terhubung ke switch zona
    core_switch.cmd('ovs-vsctl set port s4-eth1 tag=10')  # Field
    core_switch.cmd('ovs-vsctl set port s4-eth2 tag=20')  # Control
    core_switch.cmd('ovs-vsctl set port s4-eth3 tag=30')  # IT
    core_switch.cmd('ovs-vsctl set port s4-eth4 tag=10,20,30')  # Router link trunk

    print("Setting default routes on hosts")
    # Field Zone
    h1.cmd('ip route add default via 10.0.1.1')
    h2.cmd('ip route add default via 10.0.1.1')
    # Control Zone
    h3.cmd('ip route add default via 10.0.2.1')
    # IT Zone
    h4.cmd('ip route add default via 10.0.3.1')
    h5.cmd('ip route add default via 10.0.3.1')

    print("Network ready - VLAN OT/IT compliant")
    CLI(net)

    print("Stopping network")
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    CPS_topology_vlan()
