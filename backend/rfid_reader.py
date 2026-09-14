"""RFID reader boundary for newline-delimited opaque ESP32 token events."""

import os
import threading


class ReaderUnavailableError(RuntimeError):
    """Raised when a serial reader cannot be opened."""


class FakeRFIDReader:
    """Injectable reader used by tests and local development."""

    def __init__(self):
        self.connected = True
        self._lock = threading.Lock()
        self._events = []

    def push(self, token):
        with self._lock:
            self._events.append(str(token).strip())

    def read(self):
        with self._lock:
            return self._events.pop(0) if self._events else None

    def status(self):
        return {"connected": self.connected, "port": "fake", "mode": "fake"}

    def close(self):
        self.connected = False


class SerialRFIDReader:
    """Reads one opaque token per line from an ESP32 serial port."""

    def __init__(self, port=None, baudrate=None):
        self.port = port or os.getenv("RFID_SERIAL_PORT")
        self.baudrate = int(baudrate or os.getenv("RFID_SERIAL_BAUD", "115200"))
        self._serial = None
        self._lock = threading.Lock()

    def connect(self):
        if not self.port:
            return False
        try:
            import serial
            self._serial = serial.Serial(self.port, self.baudrate, timeout=0.1)
            return True
        except Exception:
            self._serial = None
            return False

    def read(self):
        with self._lock:
            if self._serial is None and not self.connect():
                return None
            raw = self._serial.readline()
            return raw.decode("utf-8", errors="ignore").strip() or None

    def status(self):
        return {
            "connected": self._serial is not None and self._serial.is_open,
            "port": self.port,
            "baudrate": self.baudrate,
            "mode": "serial",
        }

    def close(self):
        if self._serial is not None and self._serial.is_open:
            self._serial.close()
        self._serial = None
