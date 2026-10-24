"""
TP-Link Cihaz Keşif Modülü — UDP broadcast + TCP subnet tarama.

İki yöntem kullanarak ağdaki TP-Link cihazları bulur:

  1. UDP Broadcast (hızlı, ~3s)
     → 255.255.255.255:9999 adresine get_sysinfo gönderir
     → Ağdaki tüm cihazlar anında yanıt verir
     ⚠ Windows Firewall veya router bu yöntemi engelleyebilir

  2. TCP Subnet Scan (yavaş ama güvenilir, ~10-30s)
     → Subnet'teki her IP'ye TCP 9999 ile bağlanmayı dener
     → Bağlanan IP'lerden get_sysinfo alır
     → ThreadPoolExecutor ile paralel çalışır (hızlandırılmış)
     ✓ Firewall genellikle engellemez

Strateji:
  - Önce UDP dene
  - UDP sonuç bulamazsa otomatik TCP fallback yap
"""

import json
import socket
import struct
import logging
import asyncio
import ipaddress
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed

from core.protocol import INITIAL_KEY, encrypt, decrypt

logger = logging.getLogger(__name__)

TPLINK_PORT = 9999
BROADCAST_ADDR = "10.141.5.255"
DISCOVERY_QUERY = '{"system":{"get_sysinfo":{}}}'


@dataclass
class DiscoveredDevice:
    """Keşfedilen cihaz bilgisi."""
    ip: str
    alias: str = ""
    model: str = ""
    mac: str = ""
    device_id: str = ""
    is_on: bool = False
    rssi: int = 0
    hardware_version: str = ""
    software_version: str = ""


# ─── XOR Şifreleme (UDP) ──────────────────────────────────

def _xor_encrypt_udp(message: str) -> bytes:
    """UDP için XOR şifreleme — 4-byte header OLMADAN."""
    key = INITIAL_KEY
    result = bytearray()
    for char in message:
        encrypted_byte = ord(char) ^ key
        key = encrypted_byte
        result.append(encrypted_byte & 0xFF)
    return bytes(result)


def _xor_decrypt_auto(data: bytes) -> str:
    """XOR çözme — header varsa otomatik atlar."""
    if len(data) > 4:
        potential_length = struct.unpack(">I", data[:4])[0]
        if potential_length == len(data) - 4:
            data = data[4:]
    key = INITIAL_KEY
    result = []
    for byte in data:
        decrypted = byte ^ key
        key = byte
        result.append(chr(decrypted))
    return "".join(result)


def _parse_sysinfo(ip: str, response: dict) -> DiscoveredDevice:
    """get_sysinfo yanıtından DiscoveredDevice oluşturur."""
    info = response.get("system", {}).get("get_sysinfo", {})
    return DiscoveredDevice(
        ip=ip,
        alias=info.get("alias", ""),
        model=info.get("model", ""),
        mac=info.get("mac", ""),
        device_id=info.get("deviceId", ""),
        is_on=info.get("relay_state", 0) == 1,
        rssi=info.get("rssi", 0),
        hardware_version=info.get("hw_ver", ""),
        software_version=info.get("sw_ver", ""),
    )


# ─── Yöntem 1: UDP Broadcast ──────────────────────────────

def _discover_udp(timeout: float = 3.0) -> list[DiscoveredDevice]:
    """UDP broadcast ile hızlı keşif."""
    devices = []
    seen_ips = set()

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(timeout)

        encrypted = _xor_encrypt_udp(DISCOVERY_QUERY)
        sock.sendto(encrypted, (BROADCAST_ADDR, TPLINK_PORT))
        logger.info(f"[UDP] Broadcast gönderildi → {BROADCAST_ADDR}:{TPLINK_PORT}")

        while True:
            try:
                data, addr = sock.recvfrom(4096)
                ip = addr[0]
                if ip in seen_ips:
                    continue
                seen_ips.add(ip)

                decrypted = _xor_decrypt_auto(data)
                response = json.loads(decrypted)
                device = _parse_sysinfo(ip, response)
                devices.append(device)
                logger.info(f"[UDP] ✓ {device.alias or '?'} ({ip})")

            except socket.timeout:
                break
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue

        sock.close()
    except OSError as e:
        logger.warning(f"[UDP] Hata: {e}")

    return devices


# ─── Yöntem 2: TCP Subnet Scan ────────────────────────────

def _get_arp_ips() -> list[str]:
    """
    ARP tablosundan bilinen IP adreslerini çeker.
    Bu IP'ler zaten ağda aktif — en hızlı tarama yöntemi.
    """
    import subprocess
    ips = []
    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        for line in result.stdout.split("\n"):
            line = line.strip()
            # "10.141.5.100  aa-bb-cc-dd-ee-ff  dynamic" formatı
            parts = line.split()
            if len(parts) >= 2:
                candidate = parts[0]
                # Geçerli IP mi kontrol et
                try:
                    addr = ipaddress.ip_address(candidate)
                    if addr.is_private and not addr.is_loopback:
                        ips.append(str(addr))
                except ValueError:
                    continue
    except Exception as e:
        logger.warning(f"ARP tablosu okunamadı: {e}")
    return ips


def _get_all_subnets() -> list[str]:
    """
    Tüm ağ adaptörlerinden subnet bilgisini alır ve taranacak
    IP listesini döner. Gerçek subnet maskını kullanır.

    /24 = 254 IP, /23 = 510 IP, /21 = 2046 IP
    Büyük subnet'lerde ARP tablosundaki IP'lerin /24 bloklarını tarar.
    """
    import subprocess
    all_ips = set()

    try:
        # Windows: ipconfig ile tüm adaptörleri al
        result = subprocess.run(
            ["ipconfig"], capture_output=True, text=True,
            encoding="utf-8", errors="replace"
        )

        lines = result.stdout.split("\n")
        current_ip = None
        for line in lines:
            stripped = line.strip()
            # IPv4 Address satırı
            if "IPv4" in stripped and ":" in stripped:
                ip_str = stripped.split(":")[-1].strip()
                try:
                    addr = ipaddress.ip_address(ip_str)
                    if addr.is_private and not addr.is_loopback:
                        current_ip = ip_str
                except ValueError:
                    current_ip = None
            # Subnet Mask satırı
            elif current_ip and ("Subnet" in stripped or "Alt" in stripped) and ":" in stripped:
                mask_str = stripped.split(":")[-1].strip()
                try:
                    network = ipaddress.IPv4Network(
                        f"{current_ip}/{mask_str}", strict=False
                    )
                    prefix = network.prefixlen
                    num_hosts = network.num_addresses - 2

                    if num_hosts <= 510:  # /24 veya /23 — tamamını tara
                        for host in network.hosts():
                            all_ips.add(str(host))
                        logger.info(
                            f"[TCP] Adaptör {current_ip}/{prefix} → "
                            f"{num_hosts} IP taranacak"
                        )
                    else:
                        # /21 gibi büyük subnet — sadece PC'nin /24 bloğunu tara
                        parts = current_ip.split(".")
                        base = f"{parts[0]}.{parts[1]}.{parts[2]}"
                        for i in range(1, 255):
                            all_ips.add(f"{base}.{i}")
                        logger.info(
                            f"[TCP] Adaptör {current_ip}/{prefix} (büyük subnet) → "
                            f"{base}.0/24 taranacak (254 IP)"
                        )
                except (ValueError, TypeError):
                    pass
                current_ip = None
    except Exception as e:
        logger.warning(f"Adaptör bilgisi alınamadı: {e}")

    # Fallback
    if not all_ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            parts = local_ip.split(".")
            base = f"{parts[0]}.{parts[1]}.{parts[2]}"
            all_ips = {f"{base}.{i}" for i in range(1, 255)}
        except Exception:
            all_ips = {f"192.168.1.{i}" for i in range(1, 255)}

    return list(all_ips)


def _get_scan_targets() -> list[str]:
    """
    Taranacak IP listesini oluşturur:
      1. ARP tablosundaki bilinen IP'ler (en önemli!)
      2. Adaptör subnet'lerinden hesaplanan IP'ler
    ARP IP'leri önce, çünkü cihazın orada olma ihtimali en yüksek.
    """
    # 1. ARP tablosu — bilinen aktif cihazlar
    arp_ips = _get_arp_ips()
    logger.info(f"[TCP] ARP tablosunda {len(arp_ips)} IP bulundu")

    # 2. ARP IP'lerinin /24 bloklarını da ekle
    arp_subnets = set()
    for ip in arp_ips:
        parts = ip.split(".")
        base = f"{parts[0]}.{parts[1]}.{parts[2]}"
        for i in range(1, 255):
            arp_subnets.add(f"{base}.{i}")

    # 3. Adaptör subnet'leri
    adapter_ips = _get_all_subnets()

    # Birleştir, tekrarları kaldır
    all_ips = list(set(arp_ips) | arp_subnets | set(adapter_ips))
    logger.info(f"[TCP] Toplam {len(all_ips)} benzersiz IP taranacak")
    return all_ips


def _probe_single_ip(ip: str, timeout: float = 0.5) -> DiscoveredDevice | None:
    """Tek bir IP'ye TCP 9999 ile bağlanıp TP-Link cihaz mı kontrol eder."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, TPLINK_PORT))

        # protocol.py'deki encrypt() kullan — TCP için header'lı
        encrypted = encrypt(DISCOVERY_QUERY)
        sock.sendall(encrypted)

        response_data = b""
        while True:
            try:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response_data += chunk
            except socket.timeout:
                break
        sock.close()

        if not response_data:
            return None

        # protocol.py'deki decrypt() kullan
        decrypted = decrypt(response_data)
        response = json.loads(decrypted)
        device = _parse_sysinfo(ip, response)
        logger.info(f"[TCP] ✓ {device.alias or '?'} ({ip})")
        return device

    except (socket.timeout, socket.error, json.JSONDecodeError):
        return None


def _discover_tcp(timeout_per_ip: float = 0.5, max_workers: int = 100) -> list[DiscoveredDevice]:
    """
    TCP ile subnet taraması — paralel çalışır.
    ARP tablosu + tüm adaptör subnet'lerini tarar.
    """
    ips = _get_scan_targets()
    devices = []

    logger.info(f"[TCP] {len(ips)} IP taranıyor ({max_workers} paralel thread)...")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_probe_single_ip, ip, timeout_per_ip): ip
            for ip in ips
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                devices.append(result)

    logger.info(f"[TCP] Tarama tamamlandı → {len(devices)} cihaz bulundu")
    return devices


# ─── Ana Keşif Fonksiyonu ──────────────────────────────────

def discover_devices(timeout: float = 3.0, method: str = "auto") -> list[DiscoveredDevice]:
    """
    TP-Link cihazları keşfeder.

    Args:
        timeout: UDP bekleme süresi (saniye)
        method: Tarama yöntemi:
            "auto" — önce UDP, bulamazsa TCP fallback (önerilen)
            "udp"  — sadece UDP broadcast
            "tcp"  — sadece TCP subnet taraması

    Returns:
        Bulunan cihazların listesi.
    """
    if method == "udp":
        return _discover_udp(timeout)

    if method == "tcp":
        return _discover_tcp()

    # AUTO: önce UDP dene, bulamazsa TCP'ye düş
    logger.info("Keşif başlıyor (auto mod: UDP → TCP fallback)")

    devices = _discover_udp(timeout)
    if devices:
        logger.info(f"UDP ile {len(devices)} cihaz bulundu")
        return devices

    logger.info("UDP sonuç vermedi — TCP subnet taramasına geçiliyor...")
    devices = _discover_tcp()
    return devices


async def discover_devices_async(
    timeout: float = 3.0, method: str = "auto"
) -> list[DiscoveredDevice]:
    """Async wrapper — FastAPI endpoint'leri için."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, discover_devices, timeout, method)
