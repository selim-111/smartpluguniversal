"""
HS110 Otomatik WiFi Provisioning Script
========================================
Bu script tek bir komutla:
  1. Mevcut WiFi baglantinizi kaydeder
  2. Cihazan AP'sine (TP-LINK_Smart Plug_XXXX) baglanir
  3. Cihaza WiFi bilgilerinizi gonderir
  4. Sizi tekrar kendi WiFi'nize geri baglar

Kullanim:
  python auto_provision.py --ssid "EvWiFi" --password "sifre123"
  python auto_provision.py --ssid "EvWiFi" --password "sifre123" --device-ap "TP-LINK_Smart Plug_3A7F"
  python auto_provision.py --ssid "EvWiFi" --password "sifre123" --device-ip 192.168.0.1
"""

import json
import socket
import struct
import subprocess
import sys
import time
import argparse
import re


# ─── TP-Link Protocol ─────────────────────────────────────

INITIAL_KEY = 0xAB


def encrypt(message: str) -> bytes:
    key = INITIAL_KEY
    result = struct.pack(">I", len(message))
    for char in message:
        encrypted_byte = ord(char) ^ key
        key = encrypted_byte
        result += bytes([encrypted_byte & 0xFF])
    return result


def decrypt(data: bytes) -> str:
    key = INITIAL_KEY
    result = []
    for byte in data[4:]:
        decrypted = byte ^ key
        key = byte
        result.append(chr(decrypted))
    return "".join(result)


def send_command(ip: str, command: dict, timeout: float = 5.0) -> dict:
    message = json.dumps(command, separators=(",", ":"))
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((ip, 9999))
        sock.sendall(encrypt(message))

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
            return {}

        return json.loads(decrypt(response_data))
    except Exception as e:
        print(f"  [HATA] {e}")
        return {}


# ─── Windows WiFi Yonetimi (netsh) ────────────────────────

def get_current_wifi() -> str:
    """Suanda bagli olunan WiFi ag adini dondurur."""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "interfaces"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        for line in result.stdout.split("\n"):
            # "SSID" satiri ama "BSSID" degil
            stripped = line.strip()
            if stripped.startswith("SSID") and "BSSID" not in stripped:
                return stripped.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


def find_device_ap() -> str:
    """Mevcut WiFi taramasinda TP-LINK_Smart Plug ile baslayan agi bulur."""
    try:
        result = subprocess.run(
            ["netsh", "wlan", "show", "networks"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        for line in result.stdout.split("\n"):
            stripped = line.strip()
            if stripped.startswith("SSID") and "BSSID" not in stripped:
                ssid = stripped.split(":", 1)[1].strip()
                if ssid.startswith("TP-LINK_Smart Plug") or ssid.startswith("TP-Link_Smart Plug"):
                    return ssid
    except Exception:
        pass
    return ""


def connect_to_wifi(ssid: str, max_wait: int = 15) -> bool:
    """
    Belirtilen WiFi agina baglanir.
    Eger profil yoksa (cihaz AP'si gibi acik aglar icin) gecici profil olusturur.
    """
    print(f"  WiFi'ye baglaniliyor: '{ssid}'...")

    # Once mevcut profil ile dene
    result = subprocess.run(
        ["netsh", "wlan", "connect", f"name={ssid}"],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )

    if "bulunamad" in result.stdout.lower() or "not found" in result.stdout.lower() or result.returncode != 0:
        # Profil yok — acik ag icin gecici profil olustur
        print(f"  Profil bulunamadi, acik ag profili olusturuluyor...")
        profile_xml = f"""<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>{ssid}</name>
    <SSIDConfig>
        <SSID>
            <name>{ssid}</name>
        </SSID>
    </SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>manual</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>open</authentication>
                <encryption>none</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
        </security>
    </MSM>
</WLANProfile>"""
        # Gecici profil dosyasi olustur
        profile_path = "temp_wifi_profile.xml"
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(profile_xml)

        # Profili ekle
        subprocess.run(
            ["netsh", "wlan", "add", "profile", f"filename={profile_path}"],
            capture_output=True, text=True
        )

        # Simdi baglan
        result = subprocess.run(
            ["netsh", "wlan", "connect", f"name={ssid}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )

        # Gecici dosyayi sil
        try:
            import os
            os.remove(profile_path)
        except Exception:
            pass

    # Baglanmayi bekle
    print(f"  Baglanti bekleniyor (max {max_wait}s)...")
    for i in range(max_wait):
        time.sleep(1)
        current = get_current_wifi()
        if current == ssid:
            print(f"  Baglandi! ({i+1}s)")
            return True
        print(f"  Bekleniyor... ({i+1}s) - Mevcut: '{current}'")

    print(f"  BASARISIZ - {max_wait}s icerisinde '{ssid}' agina baglanilamadi")
    return False


def get_gateway_ip() -> str:
    """Mevcut baglantinin gateway IP adresini dondurur (bu genelde cihazan IP'sidir)."""
    try:
        result = subprocess.run(
            ["ipconfig"], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        lines = result.stdout.split("\n")
        for line in lines:
            if "Gateway" in line or "Varsay" in line:
                # IP adresini bul
                match = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
                if match:
                    ip = match.group(1)
                    if ip != "0.0.0.0":
                        return ip
    except Exception:
        pass
    return ""


def main():
    parser = argparse.ArgumentParser(description="HS110 Otomatik WiFi Provisioning")
    parser.add_argument("--ssid", required=True, help="Baglanilacak WiFi ag adi (ev WiFi'niz)")
    parser.add_argument("--password", required=True, help="WiFi sifresi")
    parser.add_argument("--key-type", type=int, default=3, help="Sifreleme tipi (varsayilan: 3=WPA2)")
    parser.add_argument("--device-ap", default="", help="Cihaz AP adi (bos ise otomatik bulur)")
    parser.add_argument("--device-ip", default="", help="Cihaz IP (bos ise gateway'den bulur)")
    args = parser.parse_args()

    print("=" * 60)
    print("  HS110 OTOMATIK WIFI PROVISIONING")
    print("=" * 60)

    # ── 1. Mevcut WiFi'yi kaydet ──
    print("\n[1/5] Mevcut WiFi baglantisi kaydediliyor...")
    original_wifi = get_current_wifi()
    if original_wifi:
        print(f"  Mevcut WiFi: '{original_wifi}'")
    else:
        print("  UYARI: Mevcut WiFi baglantisi bulunamadi!")
        original_wifi = args.ssid  # Geri donus icin hedef WiFi'yi kullan

    # ── 2. Cihaz AP'sini bul ──
    print("\n[2/5] Cihaz AP'si araniyor...")
    device_ap = args.device_ap
    if not device_ap:
        device_ap = find_device_ap()

    if not device_ap:
        print("  HATA: TP-LINK_Smart Plug AP'si bulunamadi!")
        print("  Cihazin resetli ve AP modunda oldugundan emin olun.")
        print("  veya --device-ap ile AP adini elle belirtin.")

        # Mevcut aglari listele
        print("\n  Mevcut aglar:")
        result = subprocess.run(
            ["netsh", "wlan", "show", "networks"],
            capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        for line in result.stdout.split("\n"):
            stripped = line.strip()
            if stripped.startswith("SSID") and "BSSID" not in stripped:
                print(f"    {stripped}")
        return False

    print(f"  Cihaz AP bulundu: '{device_ap}'")

    # ── 3. Cihaz AP'sine baglan ──
    print(f"\n[3/5] Cihaz AP'sine baglaniliyor: '{device_ap}'...")
    print("  *** INTERNET BAGLANTISI KESILECEK - BU NORMAL ***")

    if not connect_to_wifi(device_ap, max_wait=20):
        print("\n  Cihaz AP'sine baglanilamadi. Orijinal WiFi'ye donuluyor...")
        connect_to_wifi(original_wifi)
        return False

    # Gateway IP'sinden cihaz IP'sini bul
    time.sleep(2)  # DHCP'nin tamamlanmasini bekle
    device_ip = args.device_ip
    if not device_ip:
        device_ip = get_gateway_ip()
    if not device_ip:
        device_ip = "192.168.0.1"  # Varsayilan fallback

    print(f"  Cihaz IP: {device_ip}")

    # ── 4. Cihaza WiFi bilgilerini gonder ──
    print(f"\n[4/5] Cihaza WiFi bilgileri gonderiliyor...")
    print(f"  Hedef ag: '{args.ssid}'")

    # Once cihaz bilgisi alalim
    print("  Cihaz bilgisi aliniyor...")
    sysinfo = send_command(device_ip, {"system": {"get_sysinfo": {}}}, timeout=5.0)
    if sysinfo:
        info = sysinfo.get("system", {}).get("get_sysinfo", {})
        print(f"  Cihaz: {info.get('model', '?')} - {info.get('alias', '?')}")
        print(f"  MAC: {info.get('mac', '?')}")
    else:
        print("  UYARI: Cihaz bilgisi alinamadi, yine de WiFi ayari denenecek...")

    # WiFi bilgisini gonder
    wifi_cmd = {
        "netif": {
            "set_stainfo": {
                "ssid": args.ssid,
                "password": args.password,
                "key_type": args.key_type,
            }
        }
    }
    result = send_command(device_ip, wifi_cmd, timeout=10.0)

    success = False
    if result:
        err_code = result.get("netif", {}).get("set_stainfo", {}).get("err_code", -1)
        if err_code == 0:
            print("  BASARILI! Cihaz WiFi agina baglanmaya calisiyor.")
            success = True
        else:
            print(f"  HATA: err_code = {err_code}")
    else:
        # Yanit gelmemesi normal olabilir - cihaz WiFi degistirirken baglantiyi kesebilir
        print("  Yanit alinamadi (cihaz WiFi degistiriyor olabilir - bu normal)")
        success = True  # Optimistik varsayim

    # ── 5. Orijinal WiFi'ye geri don ──
    print(f"\n[5/5] Orijinal WiFi'ye geri baglaniliyor: '{original_wifi}'...")
    time.sleep(3)  # Cihazan WiFi'yi degistirmesini bekle

    if connect_to_wifi(original_wifi, max_wait=20):
        print("  Internet baglantisi geri geldi!")
    else:
        print("  UYARI: Orijinal WiFi'ye baglanilamadi!")
        print(f"  Elle '{original_wifi}' agina baglanin.")

    # ── Sonuc ──
    print("\n" + "=" * 60)
    if success:
        print("  PROVISIONING TAMAMLANDI!")
        print(f"  Cihaz '{args.ssid}' agina baglanmaya calisiyor.")
        print("  Birkaç saniye bekleyip su komutu calistirin:")
        print("    arp -a")
        print("  Cihazan yeni IP adresini bulun ve sisteme ekleyin.")
    else:
        print("  PROVISIONING BASARISIZ!")
        print("  Cihazi resetleyip tekrar deneyin.")
    print("=" * 60)

    return success


if __name__ == "__main__":
    main()
