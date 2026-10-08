"""Stdlib-only pcap/pcapng reader, TCP reassembly, HTTP request parser, and pcap writer.

Shared by triage_pcaps.py and build_and_check.py. Python 3.9+ (the Suricata 7
container ships python3.9), no third-party packages.
"""
from __future__ import annotations

import os
import struct
from collections import OrderedDict

# --------------------------------------------------------------------------- read


def _iter_classic(data: bytes):
    magic = data[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        end = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        end = ">"
    else:
        raise ValueError("not a classic pcap")
    linktype = struct.unpack(end + "I", data[20:24])[0] & 0x0FFFFFFF
    off = 24
    while off + 16 <= len(data):
        _ts, _tsu, incl, _orig = struct.unpack(end + "IIII", data[off:off + 16])
        off += 16
        yield linktype, data[off:off + incl]
        off += incl


def _iter_pcapng(data: bytes):
    off = 0
    end = "<"
    linktypes = []
    while off + 12 <= len(data):
        btype_raw = data[off:off + 4]
        if btype_raw == b"\x0a\x0d\x0d\x0a":
            bom = data[off + 8:off + 12]
            end = "<" if bom == b"\x4d\x3c\x2b\x1a" else ">"
            linktypes = []
        btype, blen = struct.unpack(end + "II", data[off:off + 8])
        if blen < 12:
            break
        body = data[off + 8:off + blen - 4]
        if btype == 1:  # IDB
            linktypes.append(struct.unpack(end + "H", body[:2])[0])
        elif btype == 6:  # EPB
            iface, _th, _tl, cap, _orig = struct.unpack(end + "IIIII", body[:20])
            lt = linktypes[iface] if iface < len(linktypes) else 1
            yield lt, body[20:20 + cap]
        elif btype == 3:  # SPB
            orig = struct.unpack(end + "I", body[:4])[0]
            yield (linktypes[0] if linktypes else 1), body[4:4 + orig]
        off += blen


def iter_frames(path: str):
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] == b"\x0a\x0d\x0d\x0a":
        return list(_iter_pcapng(data))
    return list(_iter_classic(data))


def _ip_payload(linktype: int, frame: bytes):
    """Return (ip_bytes) or None for Ethernet/raw/null/SLL link types."""
    if linktype == 1:  # Ethernet, skip VLAN tags
        off, etype = 14, struct.unpack("!H", frame[12:14])[0]
        while etype in (0x8100, 0x88A8) and len(frame) >= off + 4:
            etype = struct.unpack("!H", frame[off + 2:off + 4])[0]
            off += 4
        return frame[off:] if etype in (0x0800, 0x86DD) else None
    if linktype in (101, 228, 229, 12, 14):  # raw IP
        return frame
    if linktype == 0:  # BSD loopback
        return frame[4:]
    if linktype == 113:  # Linux SLL
        return frame[16:]
    if linktype == 276:  # Linux SLL2
        return frame[20:]
    return None


def _tcp_segment(ip: bytes):
    if not ip:
        return None
    ver = ip[0] >> 4
    if ver == 4:
        ihl = (ip[0] & 0x0F) * 4
        total = struct.unpack("!H", ip[2:4])[0] or len(ip)
        if ip[9] != 6:
            return None
        src, dst = ".".join(map(str, ip[12:16])), ".".join(map(str, ip[16:20]))
        tcp = ip[ihl:total]
    elif ver == 6:
        if ip[6] != 6:
            return None
        import ipaddress
        src = str(ipaddress.IPv6Address(ip[8:24]))
        dst = str(ipaddress.IPv6Address(ip[24:40]))
        plen = struct.unpack("!H", ip[4:6])[0]
        tcp = ip[40:40 + plen]
    else:
        return None
    if len(tcp) < 20:
        return None
    sport, dport, seq, _ack, offres, flags = struct.unpack("!HHIIBB", tcp[:14])
    doff = (offres >> 4) * 4
    return src, sport, dst, dport, seq, flags, tcp[doff:]


def client_streams(path: str):
    """Reassemble client->server TCP payload per connection.

    Returns a list of dicts {src, sport, dst, dport, data} in first-seen order.
    The client is the SYN sender; without a SYN, the side sending first.
    """
    conns: "OrderedDict[tuple, dict]" = OrderedDict()
    for lt, frame in iter_frames(path):
        ip = _ip_payload(lt, frame)
        seg = _tcp_segment(ip) if ip is not None else None
        if seg is None:
            continue
        src, sport, dst, dport, seq, flags, payload = seg
        key = tuple(sorted([(src, sport), (dst, dport)]))
        c = conns.get(key)
        if c is None:
            c = {"client": None, "segs": {}, "isn": None}
            conns[key] = c
        syn, ack = flags & 0x02, flags & 0x10
        if syn and not ack:
            c["client"] = (src, sport)
            c["isn"] = seq
        if c["client"] is None and payload:
            c["client"] = (src, sport)
        if payload and c["client"] == (src, sport):
            c["segs"].setdefault(seq, payload)
    out = []
    for key, c in conns.items():
        if c["client"] is None or not c["segs"]:
            continue
        seqs = sorted(c["segs"])
        nxt = (c["isn"] + 1) if c["isn"] is not None else seqs[0]
        buf = bytearray()
        for s in seqs:
            p = c["segs"][s]
            if s + len(p) <= nxt:
                continue
            if s > nxt:  # gap: append anyway (best effort)
                nxt = s
            buf += p[nxt - s:]
            nxt = s + len(p)
        server = key[0] if key[1] == c["client"] else key[1]
        out.append({"src": c["client"][0], "sport": c["client"][1],
                    "dst": server[0], "dport": server[1], "data": bytes(buf)})
    return out


# --------------------------------------------------------------------------- HTTP

METHODS = (b"GET", b"POST", b"PUT", b"DELETE", b"HEAD", b"OPTIONS", b"PATCH",
           b"CONNECT", b"TRACE")


def parse_requests(data: bytes):
    """Parse pipelined HTTP/1.x requests from a client stream."""
    reqs = []
    off = 0
    while off < len(data):
        hdr_end = data.find(b"\r\n\r\n", off)
        sep = 4
        if hdr_end == -1:
            hdr_end = data.find(b"\n\n", off)
            sep = 2
        if hdr_end == -1:
            break
        head = data[off:hdr_end].decode("latin-1")
        lines = head.replace("\r\n", "\n").split("\n")
        parts = lines[0].split(" ")
        if len(parts) < 2 or not parts[0].encode() in METHODS + tuple(m.lower() for m in METHODS):
            # not an HTTP request line; stop
            break
        method, uri = parts[0], parts[1]
        version = parts[2] if len(parts) > 2 else ""
        headers = []
        for ln in lines[1:]:
            if ":" in ln:
                n, v = ln.split(":", 1)
                headers.append([n, v.strip(" \t")])
        hmap = {n.lower(): v for n, v in headers}
        body_start = hdr_end + sep
        body = b""
        if "chunked" in hmap.get("transfer-encoding", "").lower():
            p = body_start
            chunks = []
            while True:
                le = data.find(b"\r\n", p)
                if le == -1:
                    break
                try:
                    size = int(data[p:le].split(b";")[0].strip() or b"0", 16)
                except ValueError:
                    break
                p = le + 2
                if size == 0:
                    te = data.find(b"\r\n\r\n", p - 2)
                    p = (te + 4) if te != -1 else len(data)
                    break
                chunks.append(data[p:p + size])
                p += size + 2
            body = b"".join(chunks)
            off = p
        else:
            try:
                clen = int(hmap.get("content-length", "0").strip() or 0)
            except ValueError:
                clen = 0
            body = data[body_start:body_start + clen]
            off = body_start + clen
        reqs.append({"method": method, "uri": uri, "version": version,
                     "headers": headers, "body": body.decode("latin-1")})
    return reqs


def body_params(body: str):
    """Split an x-www-form-urlencoded body into [name, value] pairs (raw, not decoded)."""
    out = []
    for part in body.split("&"):
        if part == "":
            continue
        if "=" in part:
            n, v = part.split("=", 1)
        else:
            n, v = part, None
        out.append([n, v])
    return out


def build_request(method: str, uri: str, version: str, headers, body: str) -> bytes:
    """Rebuild request bytes; Content-Length is rewritten to match the body."""
    out_headers = []
    have_cl = False
    for n, v in headers:
        if n.lower() == "content-length":
            v = str(len(body.encode("latin-1")))
            have_cl = True
        if n.lower() == "transfer-encoding":
            continue
        out_headers.append((n, v))
    if not have_cl and body:
        out_headers.append(("Content-Length", str(len(body.encode("latin-1")))))
    lines = ["%s %s %s" % (method, uri, version or "HTTP/1.1")]
    lines += ["%s: %s" % (n, v) for n, v in out_headers]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body.encode("latin-1")


# --------------------------------------------------------------------------- write


def _csum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    s = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    while s >> 16:
        s = (s & 0xFFFF) + (s >> 16)
    return (~s) & 0xFFFF


def _ip4(a: str) -> bytes:
    return bytes(int(x) for x in a.split("."))


def _packet(src, dst, sport, dport, seq, ack, flags, payload=b""):
    tcp_hdr = struct.pack("!HHIIBBHHH", sport, dport, seq & 0xFFFFFFFF, ack & 0xFFFFFFFF,
                          5 << 4, flags, 65535, 0, 0)
    pseudo = _ip4(src) + _ip4(dst) + struct.pack("!BBH", 0, 6, len(tcp_hdr) + len(payload))
    c = _csum(pseudo + tcp_hdr + payload)
    tcp_hdr = tcp_hdr[:16] + struct.pack("!H", c) + tcp_hdr[18:]
    total = 20 + len(tcp_hdr) + len(payload)
    ip_hdr = struct.pack("!BBHHHBBH4s4s", 0x45, 0, total, 1, 0, 64, 6, 0, _ip4(src), _ip4(dst))
    ip_hdr = ip_hdr[:10] + struct.pack("!H", _csum(ip_hdr)) + ip_hdr[12:]
    eth = b"\x02\x00\x00\x00\x00\x02" + b"\x02\x00\x00\x00\x00\x01" + b"\x08\x00"
    return eth + ip_hdr + tcp_hdr + payload


def write_session_pcap(path: str, request: bytes, *, client="10.0.0.1", server="10.0.0.2",
                       sport=40000, dport=8080, segments=3):
    """Write a complete TCP session (handshake, request split into segments, 200 reply, FIN)."""
    c_isn, s_isn = 10000, 20000
    pk = [
        _packet(client, server, sport, dport, c_isn, 0, 0x02),
        _packet(server, client, dport, sport, s_isn, c_isn + 1, 0x12),
        _packet(client, server, sport, dport, c_isn + 1, s_isn + 1, 0x10),
    ]
    n = max(1, segments)
    step = max(1, -(-len(request) // n))
    seq = c_isn + 1
    for i in range(0, len(request), step):
        chunk = request[i:i + step]
        pk.append(_packet(client, server, sport, dport, seq, s_isn + 1, 0x18, chunk))
        seq += len(chunk)
    resp = b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
    pk.append(_packet(server, client, dport, sport, s_isn + 1, seq, 0x10))
    pk.append(_packet(server, client, dport, sport, s_isn + 1, seq, 0x18, resp))
    pk.append(_packet(client, server, sport, dport, seq, s_isn + 1 + len(resp), 0x10))
    pk.append(_packet(client, server, sport, dport, seq, s_isn + 1 + len(resp), 0x11))
    pk.append(_packet(server, client, dport, sport, s_isn + 1 + len(resp), seq + 1, 0x11))
    pk.append(_packet(client, server, sport, dport, seq + 1, s_isn + 2 + len(resp), 0x10))
    with open(path, "wb") as fh:
        fh.write(struct.pack("<IHHiIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
        for i, p in enumerate(pk):
            fh.write(struct.pack("<IIII", 1700000000 + i, 0, len(p), len(p)))
            fh.write(p)


def expand_pcap_paths(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for name in sorted(os.listdir(p)):
                if name.endswith((".pcap", ".pcapng", ".cap")):
                    out.append(os.path.join(p, name))
        else:
            out.append(p)
    return out
