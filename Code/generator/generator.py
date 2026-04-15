import os
import yaml
import argparse
from jinja2 import Environment, FileSystemLoader

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TEMPLATE_DIR = os.path.join(BASE_DIR, "generator", "templates")
OUTPUT_DIR = os.path.join(BASE_DIR, "script")

env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

ROLE_TEMPLATE = {
    "field": "field.j2",
    "rtu": "rtu.j2",
    "gateway": "gateway.j2",
    "pandapower": "pandapower.j2",
    "attacker": "attacker.j2"
}

# LOAD CONFIG
def load_config(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

# PARSE HOSTS + IP ASSIGN
def parse_topology(config):
    zones = config["topology"]["zones"]
    bandwidth = config.get("network", {}).get("bandwidth", 5)

    all_hosts = []
    zone_map = {}

    for zone_name, zone in zones.items():
        subnet_base = zone["subnet"].split("/")[0].rsplit(".", 1)[0]

        zone_hosts = []

        for i, host in enumerate(zone["hosts"]):
            host_data = {
                "name": host["name"],
                "role": host["role"],
                "ip": f"{subnet_base}.{i+2}",
                "zone": zone_name
            }
            all_hosts.append(host_data)
            zone_hosts.append(host_data)

        zone_map[zone_name] = zone_hosts

    return all_hosts, zone_map, bandwidth

# GENERATE APPS
def generate_apps(hosts):
    app_dir = os.path.join(OUTPUT_DIR, "apps")
    os.makedirs(app_dir, exist_ok=True)

    for host in hosts:
        role = host["role"]
        template_name = ROLE_TEMPLATE[role]
        template = env.get_template(template_name)

        output = template.render(host=host)

        with open(os.path.join(app_dir, f"{host['name']}.py"), "w") as f:
            f.write(output)

# GENERATE TOPOLOGY FILE
def generate_topology(hosts, links, bandwidth):
    template = env.get_template("topology.j2")

    output = template.render(
        hosts=hosts,
        links=links,
        bandwidth=bandwidth
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(os.path.join(OUTPUT_DIR, "topology.py"), "w") as f:
        f.write(output)

# MAIN
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-C", "--config", required=True)
    args = parser.parse_args()

    config = load_config(args.config)

    hosts, links, bandwidth = parse_topology(config)

    generate_apps(hosts)
    generate_topology(hosts, links, bandwidth)

    print("Generation complete!")
    print(f"Output directory: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
