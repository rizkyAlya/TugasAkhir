# Tugas Akhir

---

## Authors

- [@rizkyAlya](https://github.com/rizkyAlya/)

---

## Features

- **CPS topology**: Mininet-based 3-zone network (Field, Control, IT) for smart grid / industrial simulation.
- **Scalable Field zone**: Number of hosts in the Field zone is configurable; Control zone has 1 host, IT zone has 2 hosts.
- **Config from file**: Topology can be defined via YAML or JSON (e.g. `field`, `bandwidth`) for repeatable runs.
- **Timestamped runs**: Each topology creation is logged with a timestamp under `Code/logs/topology/`.
- **Host applications**: Field device, RTU, SCADA gateway, Digital Twin, and optional DoS attacker for experiments.
- **Data collection**: Baseline and DoS (light/heavy) metrics: RTT, packet loss, throughput, with CSV output.

---

## Project structure

```
TugasAkhir/
├── Code/               # Implementation and experiments
│   ├── topology/            # Mininet topology definitions
│   │   ├── topology_new.py       # Fixed CPS topology (2 field, 1 control, 2 IT)
│   │   ├── topology_auto.py      # Scalable topology from config or CLI (field scalable only)
│   │   └── topology_example.yaml # Example YAML config for topology_auto.py
│   ├── apps/                # Host applications (run inside Mininet hosts)
│   │   ├── h1_field.py           # Field device
│   │   ├── h2_rtu.py             # RTU
│   │   ├── h3_gateway.py         # SCADA gateway
│   │   ├── h4_twin.py            # Digital Twin
│   │   └── h5_attacker.py        # DoS attacker (light/heavy)
│   ├── logger/              # Data collection and baseline tools
│   │   ├── collector.py          # RTT, packet loss, throughput collection
│   │   └── baseline.py           # Baseline measurement helpers
│   └── logs/                # Generated logs (created at runtime)
│       ├── topology/             # Topology creation timestamps and config
│       ├── host/                 # Per-host application logs
│       ├── baseline/             # Baseline experiment CSVs
│       └── dos/                  # DoS experiment CSVs (light, heavy)
│
└── Skripsi/            # Thesis (LaTeX)
```

- **Code**: All runnable code, topologies, apps, and experiment logs.
- **Skripsi**: LaTeX source for the thesis; build with the provided Makefile or your LaTeX setup.

---

## Installation

- Install Mininet (and run topology scripts in an environment where Mininet is available).
- Python 3 with dependencies used by `Code/` (e.g. for collector, apps); optional: `pip install pyyaml` for YAML config in `topology_auto.py`.

---

## Tech stack

- **Network simulation**: Mininet (SDN/mini-networks).
- **Digital twin simulation**: PandaPower.
- **Language**: Python 3 (topology, apps, logger).
- **Config**: YAML / JSON for topology (e.g. `topology_example.yaml`).
- **Thesis**: LaTeX (Skripsi template).

---

## Documentation

- Topology usage: run `topology_auto.py` with `--config topology_example.yaml` or `--field N --bandwidth B`; see `topology/topology_auto.py` for full options.
- Experiment data: CSV outputs in `Code/logs/baseline/` and `Code/logs/dos/{light,heavy}/`.

---

## License

[UI]()

