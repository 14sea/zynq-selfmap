"""An independent reading of 7-series configuration packets, and the read-only policy.

Deliberately structural: every header is decoded by its fields (UG470), nothing is matched as a
whole word. The prober's own guard (prober/sm_core.c) works the other way round — a short list of
whole words — so the two cannot share a mistake of form. tests/ hold them against each other.
"""
from __future__ import annotations

DUMMY, SYNC, NOOP = 0xFFFFFFFF, 0xAA995566, 0x20000000
FRAME_WORDS = 101
REG = {0: "CRC", 1: "FAR", 2: "FDRI", 3: "FDRO", 4: "CMD", 5: "CTL0", 6: "MASK", 7: "STAT", 8: "LOUT",
       9: "COR0", 10: "MFWR", 11: "CBC", 12: "IDCODE", 13: "AXSS", 14: "COR1", 16: "WBSTAR", 17: "TIMER",
       22: "BOOTSTS", 24: "CTL1", 31: "BSPI"}
CMD = {0: "NULL", 1: "WCFG", 2: "MFW", 3: "DGHIGH", 4: "RCFG", 5: "START", 6: "RCAP", 7: "RCRC", 8: "AGHIGH",
       9: "SWITCH", 10: "GRESTORE", 11: "SHUTDOWN", 12: "GCAPTURE", 13: "DESYNC", 15: "IPROG", 16: "CRCC", 17: "LTIMER"}
OPS = {0: "nop", 1: "read", 2: "write", 3: "reserved"}


def decode(words: list[int]) -> list[dict]:
    """The packets of a stream. A leading run of dummies and one sync word is a prefix; without it the
    stream is taken to continue an already synchronised session (the cleanup stream)."""
    out: list[dict] = []
    i, n = 0, len(words)
    if n and words[0] in (DUMMY, SYNC):
        while i < n and words[i] == DUMMY:
            out.append({"at": i, "kind": "dummy"}); i += 1
        if i >= n or words[i] != SYNC:
            out.append({"at": i, "kind": "error", "why": "dummies not followed by the sync word"})
            return out
        out.append({"at": i, "kind": "sync"}); i += 1
    last_reg = None
    while i < n:
        x = words[i]; at = i; i += 1
        kind, op = x >> 29, (x >> 27) & 3
        if kind == 1:
            reg, count = (x >> 13) & 0x3FFF, x & 0x7FF
            if x & 0x1800:
                out.append({"at": at, "kind": "error", "why": f"reserved bits set in {x:#010x}"}); return out
            last_reg = reg
        elif kind == 2:
            reg, count = last_reg, x & 0x07FFFFFF
            if reg is None:
                out.append({"at": at, "kind": "error", "why": "type-2 packet with no preceding type-1"}); return out
        else:
            out.append({"at": at, "kind": "error", "why": f"header type {kind} in {x:#010x}"}); return out
        payload: list[int] = []
        if OPS[op] == "write":
            if i + count > n:
                out.append({"at": at, "kind": "error", "why": "write payload runs past the end"}); return out
            payload = words[i:i + count]; i += count
        out.append({"at": at, "kind": f"type{kind}", "op": OPS[op], "reg": reg, "reg_name": REG.get(reg, f"reg{reg}"),
                    "count": count, "payload": payload})
    return out


def readonly_problems(words: list[int], far_lo: int, far_hi: int, max_read: int) -> list[str]:
    """Why a stream is not something a read-only stage may send; empty when it is."""
    problems: list[str] = []
    if not words:
        return ["an empty stream"]
    rcfg = far = False
    far_value = 0
    pending_read = False
    for p in decode(words):
        k = p["kind"]
        if k == "error":
            problems.append(f"word {p['at']}: {p['why']}"); break
        if k in ("dummy", "sync"):
            continue
        op, reg, count = p["op"], p["reg_name"], p["count"]
        where = f"word {p['at']}"
        if pending_read and not (k == "type2" and op == "read"):
            problems.append(f"{where}: the zero-count FDRO read header is not followed by its type-2 read")
            pending_read = False
        if op == "nop":
            if k != "type1" or p["reg"] != 0 or count != 0:
                problems.append(f"{where}: a no-op that is not the plain NOOP word")
        elif op == "write":
            if k != "type1" or count != 1:
                problems.append(f"{where}: a write of {count} word(s) to {reg}")
            elif reg == "CMD":
                name = CMD.get(p["payload"][0], f"{p['payload'][0]:#x}")
                if name == "RCFG":
                    rcfg = True
                elif name != "DESYNC":
                    problems.append(f"{where}: CMD = {name}")
            elif reg == "FAR":
                value = p["payload"][0]
                if not far_lo <= value <= far_hi:
                    problems.append(f"{where}: FAR {value:#010x} outside the envelope {far_lo:#010x}..{far_hi:#010x}")
                far = True; far_value = value
            else:
                problems.append(f"{where}: a write to {reg}")
        elif op == "read":
            if reg == "FAR" and k == "type1" and count == 1:
                pass                                 # one word of the FAR register: a read, of a readable register
            elif reg != "FDRO":
                problems.append(f"{where}: a read of {reg}" + (f" ({count} words)" if reg == "FAR" else ""))
            elif k == "type1":
                if count != 0:
                    problems.append(f"{where}: a type-1 FDRO read of {count} words")
                pending_read = True
            else:
                if not pending_read:
                    problems.append(f"{where}: a type-2 read without the FDRO header before it")
                if not 1 <= count <= max_read:
                    problems.append(f"{where}: a read of {count} words (limit {max_read})")
                elif count % FRAME_WORDS:               # the pad alone (one frame of words) delivers no frame and is allowed
                    problems.append(f"{where}: a read of {count} words is not a pad frame plus whole frames")
                elif far and count >= 2 * FRAME_WORDS and far_value + count // FRAME_WORDS - 2 > far_hi:
                    problems.append(f"{where}: the read runs past the envelope (from {far_value:#010x}, {count // FRAME_WORDS - 1} frames)")
                if not (rcfg and far):
                    problems.append(f"{where}: a read with no RCFG, or with no frame address given since the last read")
                far = False                              # the register has moved on: another read needs a new, checked address
                pending_read = False
        else:
            problems.append(f"{where}: reserved opcode")
    if pending_read:
        problems.append("the stream ends on the FDRO read header")
    return problems
