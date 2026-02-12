from mininet.net import Mininet 
from mininet.node import Controller, OVSSwitch, Node
from mininet.cli import CLI 
from mininet.link import TCLink
from mininet.log import setLogLevel

def L3_Core_Switch(net, switch_name, subnets):
    core = net.get(switch_name)
    
    # Create L3 interfaces for each subnet (simulate VLAN routing)
    for idx, (zone, (ip, mask)) in enumerate(subnets.items()):
        iface = f'{core.name}-eth{idx}'
        core.cmd(f'ifconfig {iface} {ip}/{mask} up')
    core.cmd('sysctl -w net.ipv4.ip_forward=1')
    return core
    
def addRouter(net, name):
    """Add a router host with IP forwarding enabled"""
    r = net.addHost(name, cls=Node)
    r.cmd('sysctl -w net.ipv4.ip_forward=1')
    return r

def CPS_topology():
    net = Mininet(controller=Controller, link=TCLink, switch=OVSSwitch)

    print("Adding controller")
    net.addController('c0')

    print("Adding hosts with static IPs")
    h1 = net.addHost('h1', ip='10.0.1.1/24')  # Field Device
    h2 = net.addHost('h2', ip='10.0.1.2/24')  # RTU
    h3 = net.addHost('h3', ip='10.0.2.1/24')  # SCADA Gateway
    h4 = net.addHost('h4', ip='10.0.3.1/24')  # Digital Twin
    h5 = net.addHost('h5', ip='10.0.3.2/24')  # Attacker in IT Zone

    print("Adding switches")
    switch_field = net.addSwitch('s1')
    switch_control = net.addSwitch('s2')
    switch_it = net.addSwitch('s3')
    core_switch = net.addSwitch('s4')
    
    print("Creating links")
    # Field Zone
    net.addLink(h1, switch_field)
    net.addLink(h2, switch_field)
    net.addLink(switch_field, core_switch)

    # Control/Gateway Zone
    net.addLink(h3, switch_control)
    net.addLink(switch_control, core_switch)

    # IT Zone
    net.addLink(h4, switch_it)
    net.addLink(h5, switch_it)  
    net.addLink(switch_it, core_switch)

    print("Starting network")
    net.start()
    
    print("Configuring L3 Core Switch")
    subnets = {
        'field': ('10.0.1.1', 24),
        'control': ('10.0.2.1', 24),
        'IT': ('10.0.3.1', 24)
    }
    L3_Core_Switch(net, 's4', subnets)
    
    print("Running CLI")
    CLI(net)

    print("Stopping network")
    net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    CPS_topology()
