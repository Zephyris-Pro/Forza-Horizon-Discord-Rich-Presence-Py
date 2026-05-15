use std::net::{UdpSocket, SocketAddr};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use socket2::{Domain, Protocol, Socket, Type};
use tokio::sync::broadcast;

#[derive(Clone, Debug, Default)]
pub struct TelemetryData {
    pub car_ordinal: i32,
    pub car_class: i32,
    pub car_pi: i32,
    pub _speed_kmh: f32,
    pub _is_race_on: i32,
}

pub struct TelemetryServer {
    is_running: Arc<AtomicBool>,
}

impl TelemetryServer {
    pub fn new() -> Self {
        Self {
            is_running: Arc::new(AtomicBool::new(false)),
        }
    }

    /// Start the telemetry server with optional relay forwarding.
    ///
    /// If `forward_addrs` is non-empty, every raw UDP packet received from Forza
    /// will be forwarded to each address ("ip:port" strings). This lets SimHub
    /// (or any other tool) receive the telemetry stream even though this app
    /// owns the primary UDP socket — eliminating the port conflict entirely.
    pub fn start_with_relay(&self, port: u16, tx: broadcast::Sender<TelemetryData>, forward_addrs: Vec<String>) {
        if self.is_running.load(Ordering::SeqCst) {
            return;
        }
        self.is_running.store(true, Ordering::SeqCst);

        let is_running_clone = self.is_running.clone();

        std::thread::spawn(move || {
            // Use socket2 to set SO_REUSEADDR before bind.
            // This is required so that if SimHub starts BEFORE this app, we can
            // still bind to the same port (Windows requires both sides to opt-in).
            let raw_socket = match Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP)) {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("[Telemetry] Failed to create UDP socket: {}", e);
                    is_running_clone.store(false, Ordering::SeqCst);
                    return;
                }
            };

            if let Err(e) = raw_socket.set_reuse_address(true) {
                eprintln!("[Telemetry] Failed to set SO_REUSEADDR: {}", e);
            }

            // Bind to 0.0.0.0 — Forza may send packets to the real adapter IP,
            // not just 127.0.0.1.
            let addr: SocketAddr = format!("0.0.0.0:{}", port).parse().unwrap();
            if let Err(e) = raw_socket.bind(&addr.into()) {
                eprintln!("[Telemetry] Failed to bind UDP socket on port {}: {}", port, e);
                is_running_clone.store(false, Ordering::SeqCst);
                return;
            }

            // Convert to a standard UdpSocket
            let socket: UdpSocket = raw_socket.into();
            socket
                .set_read_timeout(Some(std::time::Duration::from_millis(1000)))
                .unwrap();

            // Create a separate outbound socket for relaying packets to SimHub.
            // Bound to port 0 (OS picks an ephemeral port), used only for sending.
            let relay_socket = if !forward_addrs.is_empty() {
                match UdpSocket::bind("0.0.0.0:0") {
                    Ok(s) => {
                        println!("[Telemetry] Relay active: forwarding packets to {:?}", forward_addrs);
                        Some(s)
                    }
                    Err(e) => {
                        eprintln!("[Telemetry] Failed to create relay socket: {}", e);
                        None
                    }
                }
            } else {
                None
            };

            let mut buf = [0u8; 512];

            while is_running_clone.load(Ordering::SeqCst) {
                match socket.recv_from(&mut buf) {
                    Ok((size, _src)) => {
                        // Forward raw bytes to each configured address.
                        if let Some(ref relay) = relay_socket {
                            for dest in &forward_addrs {
                                if let Err(e) = relay.send_to(&buf[..size], dest.as_str()) {
                                    eprintln!("[Telemetry] Relay send error to {}: {}", dest, e);
                                }
                            }
                        }

                        // Forza Horizon 4/5 Data Out (Dash v2) packet is typically 311-324 bytes
                        if size >= 311 {
                            let data = Self::parse_packet(&buf);
                            let _ = tx.send(data);
                        }
                    }
                    Err(_) => {} // Timeout — loop back and check is_running
                }
            }
        });
    }

    pub fn stop(&self) {
        self.is_running.store(false, Ordering::SeqCst);
    }

    fn parse_packet(buf: &[u8]) -> TelemetryData {
        // Read f32/i32 from byte slices safely
        let read_i32 = |offset: usize| -> i32 {
            if offset + 4 <= buf.len() {
                i32::from_le_bytes(buf[offset..offset+4].try_into().unwrap())
            } else {
                0
            }
        };

        let read_f32 = |offset: usize| -> f32 {
            if offset + 4 <= buf.len() {
                f32::from_le_bytes(buf[offset..offset+4].try_into().unwrap())
            } else {
                0.0
            }
        };

        let is_race_on = read_i32(0);
        let car_ordinal = read_i32(212);
        let car_class = read_i32(216);
        let car_pi = read_i32(220);
        let speed_mps = read_f32(256);
        let speed_kmh = speed_mps * 3.6;

        TelemetryData {
            car_ordinal,
            car_class,
            car_pi,
            _speed_kmh: speed_kmh,
            _is_race_on: is_race_on,
        }
    }
}
