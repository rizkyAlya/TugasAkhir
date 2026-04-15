import os
import yaml
import argparse
import json
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
    links = config.get("topology", {}).get("links", [])

    all_hosts = []
    zone_map = {}
    hosts_by_name = {}
    hosts_by_role = {}

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
            hosts_by_name[host_data["name"]] = host_data
            hosts_by_role.setdefault(host_data["role"], []).append(host_data)

        zone_map[zone_name] = zone_hosts

    return all_hosts, zone_map, links, bandwidth, hosts_by_name, hosts_by_role

# GENERATE APPS
def generate_apps(hosts, app_name_mode="host"):
    app_dir = os.path.join(OUTPUT_DIR, "apps")
    os.makedirs(app_dir, exist_ok=True)
    app_map = {}
    role_counts = {}

    for host in hosts:
        role = host["role"]
        template_name = ROLE_TEMPLATE[role]
        template = env.get_template(template_name)

        # Keep templates simple: pass host plus computed role/name maps.
        # Templates may use these to reference other hosts' IPs/endpoints.
        output = template.render(
            host=host,
            all_hosts=hosts,
            hosts_by_name=generate_apps.hosts_by_name,
            hosts_by_role=generate_apps.hosts_by_role,
        )

        if app_name_mode == "role":
            role_counts[role] = role_counts.get(role, 0) + 1
            idx = role_counts[role]
            script_name = f"{role}.py" if idx == 1 else f"{role}_{idx}.py"
        else:
            script_name = f"{host['name']}.py"

        app_map[host["name"]] = script_name
        with open(os.path.join(app_dir, script_name), "w") as f:
            f.write(output)

    # Save host -> script mapping so run.py can resolve generated filenames.
    with open(os.path.join(app_dir, "app_map.json"), "w", encoding="utf-8") as f:
        json.dump(app_map, f, indent=2)
    return app_map

# GENERATE TOPOLOGY FILE
def generate_topology(hosts, zone_map, links, bandwidth, hosts_by_role):
    template = env.get_template("topology.j2")
    attacker_hosts = hosts_by_role.get("attacker", [])
    if not attacker_hosts:
        raise ValueError("Topology requires at least one host with role 'attacker' for dual-homed setup.")
    attacker_name = attacker_hosts[0]["name"]

    output = template.render(
        hosts=hosts,
        zones=zone_map,
        links=links,
        bandwidth=bandwidth,
        attacker_name=attacker_name,
    )

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with open(os.path.join(OUTPUT_DIR, "topology.py"), "w") as f:
        f.write(output)

# MAIN
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-C", "--config", required=True)
    parser.add_argument(
        "--app-mode",
        choices=["host", "role"],
        default="host",
        help="Generated app filename mode: host (h1.py) or role (field.py, field_2.py, ...)",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    hosts, zone_map, links, bandwidth, hosts_by_name, hosts_by_role = parse_topology(config)
    generate_apps.hosts_by_name = hosts_by_name
    generate_apps.hosts_by_role = hosts_by_role

    app_map = generate_apps(hosts, app_mode=args.app_mode)
    generate_topology(hosts, zone_map, links, bandwidth, hosts_by_role)

    print("Generation complete!")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"App filename mode: {args.app_mode}")
    print(f"App mapping file: {os.path.join(OUTPUT_DIR, 'apps', 'app_map.json')}")


if __name__ == "__main__":
    main()
