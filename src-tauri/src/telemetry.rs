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
    pub speed_kmh: f32,
    pub is_race_on: i32,
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

    pub fn start(&self, port: u16, tx: broadcast::Sender<TelemetryData>) {
        if self.is_running.load(Ordering::SeqCst) {
            return;
        }
        self.is_running.store(true, Ordering::SeqCst);

        let is_running_clone = self.is_running.clone();

        std::thread::spawn(move || {
            // Use socket2 to set SO_REUSEADDR before bind.
            // This allows SimHub and other apps to listen on the same port
            // simultaneously — each process receives its own copy of incoming UDP packets.
            let raw_socket = match Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP)) {
                Ok(s) => s,
                Err(e) => {
                    eprintln!("Failed to create UDP socket: {}", e);
                    is_running_clone.store(false, Ordering::SeqCst);
                    return;
                }
            };

            if let Err(e) = raw_socket.set_reuse_address(true) {
                eprintln!("Failed to set SO_REUSEADDR: {}", e);
            }

            // Bind to 0.0.0.0 — Forza may send packets to the real adapter IP,
            // not just 127.0.0.1.
            let addr: SocketAddr = format!("0.0.0.0:{}", port).parse().unwrap();
            if let Err(e) = raw_socket.bind(&addr.into()) {
                eprintln!("Failed to bind UDP socket on port {}: {}", port, e);
                is_running_clone.store(false, Ordering::SeqCst);
                return;
            }

            // Convert to a standard UdpSocket
            let socket: UdpSocket = raw_socket.into();
            socket
                .set_read_timeout(Some(std::time::Duration::from_millis(1000)))
                .unwrap();

            let mut buf = [0u8; 512];

            while is_running_clone.load(Ordering::SeqCst) {
                if let Ok((size, _)) = socket.recv_from(&mut buf) {
                    // Forza Horizon 4/5 Data Out (Dash v2) packet is typically 324 or 311 bytes
                    if size >= 311 {
                        let data = Self::parse_packet(&buf);
                        let _ = tx.send(data);
                    }
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
            speed_kmh,
            is_race_on,
        }
    }
}
