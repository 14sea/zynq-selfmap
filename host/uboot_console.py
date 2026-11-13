"""Minimal U-Boot console helper for this session: every byte sent and received is appended to a log; no bare CR is ever sent."""
import os, re, sys, time, serial
DEV = "/dev/serial/by-id/usb-1a86_USB_Serial-if00-port0"
LOG = os.environ.get("SELFMAP_CONSOLE_LOG", "build/console.log")
PROMPT = re.compile(rb"(?:zynq-uboot|Zynq)> \Z")
class UB:
    def __init__(self):
        self.s = serial.Serial(DEV, 115200, timeout=0.1); self.log = open(LOG, "ab")
    def _rd(self, t):
        end = time.time() + t; buf = b""
        while time.time() < end:
            d = self.s.read(4096)
            if d: buf += d; self.log.write(d); self.log.flush()
        return buf
    def until_prompt(self, timeout):
        end = time.time() + timeout; buf = b""
        while time.time() < end:
            d = self.s.read(4096)
            if d:
                buf += d; self.log.write(d); self.log.flush()
            elif PROMPT.search(buf):
                return buf, True
        return buf, False
    def tx(self, b):
        self.log.write(b"\n<<TX %r>>\n" % b); self.log.flush(); self.s.write(b); self.s.flush()
    def interrupt(self, tries=40):
        buf = b""
        for _ in range(tries):
            self.tx(b"\x03"); buf += self._rd(0.4)
            if PROMPT.search(buf) and not self._rd(0.6): return buf, True
        return buf, False
    def cmd(self, line, timeout=8):
        assert line.strip(), "a bare CR repeats U-Boot's previous command"
        self.s.reset_input_buffer(); self.tx(line.encode() + b"\r")
        return self.until_prompt(timeout)
