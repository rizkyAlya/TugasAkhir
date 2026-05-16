"""
tcpdump capture on Mininet hosts for OT protocol traffic.
Output layout: logs/pcap/<timestamp>/*.pcap (+ manifest.json)
"""
from __future__ import annotations

import json
import os
import shutil
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

# iface: antarmuka Mininet (selaras topology.j2 / attacker.j2).
# defer=mitm: capture dimulai setelah escalate_attacker_to_field (h5-eth1 aktif).
CAPTURE_SPECS: List[Dict[str, str]] = [
    {
        "host": "h1",
        "label": "field_modbus_5020",
        "iface": "h1-eth0",
        "filter": "tcp port 5020",
    },
    {
        "host": "h2",
        "label": "rtu_modbus_5020",
        "iface": "h2-eth0",
        "filter": "tcp port 5020",
    },
    {
        "host": "h3",
        "label": "gateway_modbus_opcua",
        "iface": "h3-eth0",
        "filter": "tcp port 5020 or tcp port 4840",
    },
    {
        "host": "h4",
        "label": "dt_opcua_4840",
        "iface": "h4-eth0",
        "filter": "tcp port 4840",
    },
    {
        "host": "h5",
        "label": "attacker_control_eth0",
        "iface": "h5-eth0",
        "filter": "tcp port 5020 or tcp port 50201 or udp port 5001",
    },
    {
        "host": "h5",
        "label": "attacker_field_mitm_eth1",
        "iface": "h5-eth1",
        "filter": "tcp port 5020 or tcp port 50201",
        "defer": "mitm",
    },
    {
        "host": "r0",
        "label": "router_ot_crosszone",
        "iface": "any",
        "filter": "tcp port 5020 or tcp port 4840",
    },
]

_PID_DIR = "/tmp/cyberrange_pcap"
_REMOTE_PCAP_DIR = "/tmp/cyberrange_pcap/out"


def _iface_up(host, iface: str) -> bool:
    if iface == "any":
        return True
    out = (host.cmd(f"cat /sys/class/net/{iface}/operstate 2>/dev/null") or "").strip()
    return out in ("up", "unknown", "dormant")


def _host_has_tcpdump(host) -> bool:
    return bool((host.cmd("command -v tcpdump 2>/dev/null") or "").strip())


def _remote_pcap_path(host_name: str, label: str) -> str:
    safe = label.replace("/", "_")
    return f"{_REMOTE_PCAP_DIR}/{host_name}_{safe}.pcap"


def _pid_file(host_name: str, label: str) -> str:
    safe = label.replace("/", "_")
    return f"{_PID_DIR}/{host_name}_{label.replace('/', '_')}.pid"


def _copy_from_host_namespace(host, remote_path: str, local_path: str) -> bool:
    pid = getattr(host, "pid", None)
    if not pid:
        return False
    src = f"/proc/{pid}/root{remote_path}"
    if not os.path.isfile(src):
        return False
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    shutil.copy2(src, local_path)
    return True


def _write_manifest(output_dir: str, manifest: List[Dict[str, Any]], **extra) -> None:
    payload = {"output_dir": output_dir, "captures": manifest}
    payload.update(extra)
    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def _start_one_capture(
    net,
    spec: Dict[str, str],
    output_dir: str,
    started_at: str,
) -> Dict[str, Any]:
    host_name = spec["host"]
    label = spec["label"]
    bpf = spec["filter"]
    iface = spec["iface"]

    if host_name not in net.nameToNode:
        return {
            "host": host_name,
            "label": label,
            "status": "skipped",
            "reason": "host_not_in_topology",
        }

    host = net.get(host_name)
    if not _host_has_tcpdump(host):
        print(f"[pcap] SKIP {host_name} ({label}): tcpdump not found")
        return {
            "host": host_name,
            "label": label,
            "status": "skipped",
            "reason": "tcpdump_not_installed",
        }

    if not _iface_up(host, iface):
        print(f"[pcap] WARN {host_name} ({label}): {iface} not up yet (starting anyway)")

    remote_pcap = _remote_pcap_path(host_name, label)
    pid_file = _pid_file(host_name, label)
    host.cmd(f"mkdir -p {_REMOTE_PCAP_DIR} {_PID_DIR}")
    host.cmd(f"rm -f {remote_pcap} {pid_file}")

    bpf_q = bpf.replace('"', '\\"')
    host.cmd(
        f"nohup tcpdump -i {iface} -w {remote_pcap} "
        f'"{bpf_q}" -U -s 0 '
        f"</dev/null >/dev/null 2>&1 & echo $! > {pid_file}"
    )
    time.sleep(0.15)
    pid_out = (host.cmd(f"cat {pid_file} 2>/dev/null") or "").strip()
    if not pid_out.isdigit():
        print(f"[pcap] FAIL start on {host_name} ({label}) iface={iface}")
        return {
            "host": host_name,
            "label": label,
            "status": "failed",
            "reason": "tcpdump_start_failed",
            "iface": iface,
            "filter": bpf,
        }

    print(f"[pcap] START {host_name} ({label}) iface={iface} pid={pid_out}")
    return {
        "host": host_name,
        "label": label,
        "status": "running",
        "pid": int(pid_out),
        "iface": iface,
        "filter": bpf,
        "remote_pcap": remote_pcap,
        "pid_file": pid_file,
        "local_file": os.path.join(output_dir, f"{label}.pcap"),
        "started_at": started_at,
        "defer": spec.get("defer"),
    }


def start_pcap_captures(net, output_dir: str) -> List[Dict[str, Any]]:
    """Start tcpdump for all hosts except defer=mitm (h5-eth1 after lateral movement)."""
    os.makedirs(output_dir, exist_ok=True)
    started_at = datetime.now().isoformat(timespec="seconds")
    manifest: List[Dict[str, Any]] = []

    for spec in CAPTURE_SPECS:
        if spec.get("defer") == "mitm":
            continue
        manifest.append(_start_one_capture(net, spec, output_dir, started_at))

    _write_manifest(output_dir, manifest, started_at=started_at)
    return manifest


def start_mitm_pcap_captures(
    net,
    output_dir: str,
    manifest: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Setelah escalate_attacker_to_field: capture di h5-eth1 (DNAT Modbus MITM, selaras attacker.j2).
    """
    started_at = datetime.now().isoformat(timespec="seconds")
    added: List[Dict[str, Any]] = []

    for spec in CAPTURE_SPECS:
        if spec.get("defer") != "mitm":
            continue
        entry = _start_one_capture(net, spec, output_dir, started_at)
        manifest.append(entry)
        added.append(entry)

    _write_manifest(output_dir, manifest, mitm_captures_started_at=started_at)
    return added


def stop_pcap_captures(
    net,
    output_dir: str,
    manifest: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Stop tcpdump processes and pull .pcap files into output_dir."""
    stopped_at = datetime.now().isoformat(timespec="seconds")
    summary: Dict[str, Any] = {
        "stopped_at": stopped_at,
        "output_dir": output_dir,
        "files": [],
    }

    for entry in manifest:
        if entry.get("status") != "running":
            continue

        host_name = entry["host"]
        host = net.get(host_name)
        pid_file = entry["pid_file"]
        remote_pcap = entry["remote_pcap"]
        local_file = entry["local_file"]

        host.cmd(
            f"if [ -f {pid_file} ]; then "
            f"kill -TERM $(cat {pid_file}) 2>/dev/null; "
            f"sleep 0.4; "
            f"kill -KILL $(cat {pid_file}) 2>/dev/null; "
            f"rm -f {pid_file}; fi"
        )
        time.sleep(0.2)

        ok = _copy_from_host_namespace(host, remote_pcap, local_file)
        size = os.path.getsize(local_file) if ok and os.path.isfile(local_file) else 0
        entry["status"] = "saved" if ok and size > 0 else "empty_or_missing"
        entry["stopped_at"] = stopped_at
        entry["bytes"] = size
        host.cmd(f"rm -f {remote_pcap}")

        summary["files"].append(
            {
                "host": host_name,
                "label": entry["label"],
                "iface": entry.get("iface"),
                "path": local_file,
                "bytes": size,
                "status": entry["status"],
            }
        )
        tag = "OK" if size > 0 else "WARN"
        print(f"[pcap] {tag} {host_name} ({entry.get('iface')}) -> {local_file} ({size} bytes)")

    _write_manifest(
        output_dir,
        manifest,
        stopped_at=stopped_at,
        summary=summary,
    )
    return summary


def pcap_session_dir(base_dir: str, run_id: str) -> str:
    """logs/pcap/<timestamp>/"""
    return os.path.join(base_dir, "logs", "pcap", run_id)
