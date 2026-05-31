import queue
import socket
import struct
import threading
from dataclasses import dataclass
from socket import SO_REUSEADDR, SOL_SOCKET


@dataclass
class TelemetryData:
    car_ordinal: int = 0
    car_class: int = 0
    car_pi: int = 0
    speed_kmh: float = 0.0
    is_race_on: int = 0


def parse_packet(buf: bytes) -> TelemetryData:
    def read_i32(offset: int) -> int:
        if offset + 4 <= len(buf):
            return struct.unpack_from("<i", buf, offset)[0]
        return 0

    def read_f32(offset: int) -> float:
        if offset + 4 <= len(buf):
            return struct.unpack_from("<f", buf, offset)[0]
        return 0.0

    return TelemetryData(
        is_race_on=read_i32(0),
        car_ordinal=read_i32(212),
        car_class=read_i32(216),
        car_pi=read_i32(220),
        speed_kmh=read_f32(256) * 3.6,
    )


def _parse_addr(addr_str: str) -> tuple[str, int]:
    host, port = addr_str.rsplit(":", 1)
    return host, int(port)


class TelemetryServer:
    def __init__(self):
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event | None = None

    def start(self, port: int, data_queue: queue.Queue, relay_targets: list[str]):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            args=(port, data_queue, relay_targets, self._stop_event),
            daemon=True,
        )
        self._thread.start()

    def stop(self):
        if self._stop_event:
            self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self._thread = None
        self._stop_event = None

    def restart(self, port: int, data_queue: queue.Queue, relay_targets: list[str]):
        self.stop()
        self.start(port, data_queue, relay_targets)

    def _run(
        self,
        port: int,
        data_queue: queue.Queue,
        relay_targets: list[str],
        stop: threading.Event,
    ):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError as e:
            print(f"[Telemetry] Failed to bind port {port}: {e}")
            return
        sock.settimeout(1.0)

        relay_sock = None
        if relay_targets:
            relay_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            relay_sock.bind(("0.0.0.0", 0))

        try:
            while not stop.is_set():
                try:
                    data, _ = sock.recvfrom(512)
                except socket.timeout:
                    continue

                if relay_sock:
                    for dest in relay_targets:
                        try:
                            relay_sock.sendto(data, _parse_addr(dest))
                        except OSError:
                            pass

                if len(data) >= 311:
                    try:
                        data_queue.put_nowait(parse_packet(data))
                    except queue.Full:
                        pass
        finally:
            sock.close()
            if relay_sock:
                relay_sock.close()
