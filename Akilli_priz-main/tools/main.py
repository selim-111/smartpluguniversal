"""
TP-Link HS110 Smart Plug — CLI Control Tool

Usage:
    python main.py --ip 192.168.1.100 --action info
    python main.py --ip 192.168.1.100 --action energy
    python main.py --ip 192.168.1.100 --action on
    python main.py --ip 192.168.1.100 --action off
    python main.py --ip 192.168.1.100 --action poll --interval 3
    python main.py --ip 192.168.1.100 --action led-on
    python main.py --ip 192.168.1.100 --action led-off
"""

import argparse
import json
import logging
import signal
import sys
import time

from core.device import HS110Device
from core.poller import DevicePoller
from core.models import DeviceStatus


def setup_logging(verbose: bool = False):
    """Configure logging level."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def print_json(data: dict):
    """Pretty-print a dict as JSON."""
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def action_info(device: HS110Device):
    """Display device system information."""
    info = device.get_sysinfo()
    print("═" * 50)
    print(f"  📟 Device: {info.alias or 'N/A'}")
    print(f"  📋 Model:  {info.model}")
    print(f"  🔗 MAC:    {info.mac}")
    print(f"  💡 Power:  {'🟢 ON' if info.is_on else '🔴 OFF'}")
    print(f"  💡 LED:    {'🟢 ON' if info.is_led_on else '🔴 OFF'}")
    print(f"  📶 RSSI:   {info.rssi} dBm")
    print(f"  ⏱️  Uptime: {info.on_time}s")
    print(f"  🔧 SW:     {info.software_version}")
    print(f"  🔧 HW:     {info.hardware_version}")
    print("═" * 50)


def action_energy(device: HS110Device):
    """Display real-time energy consumption."""
    energy = device.get_realtime_energy()
    print("═" * 50)
    print(f"  ⚡ Voltage:  {energy.voltage_v:.1f} V")
    print(f"  ⚡ Current:  {energy.current_a:.3f} A")
    print(f"  ⚡ Power:    {energy.power_w:.1f} W")
    print(f"  ⚡ Total:    {energy.total_wh} Wh")
    print("═" * 50)


def action_poll(device: HS110Device, interval: float):
    """Start polling mode — continuously display device status."""
    print(f"🔄 Polling {device.ip} every {interval}s (Ctrl+C to stop)\n")

    poll_count = 0

    def on_update(status: DeviceStatus):
        nonlocal poll_count
        poll_count += 1

        if not status.online:
            print(f"[#{poll_count}] ❌ OFFLINE — {status.error}")
            return

        data = status.to_dict()
        power_state = data.get("power_state", "?")
        power_w = data.get("power_w", 0)
        voltage = data.get("voltage_v", 0)
        alias = data.get("alias", "?")
        ts = data.get("timestamp", "")

        print(
            f"[#{poll_count}] "
            f"{'🟢' if power_state == 'ON' else '🔴'} {alias} | "
            f"Power: {power_w:.1f}W | "
            f"Voltage: {voltage:.1f}V | "
            f"Time: {ts}"
        )

    # Graceful shutdown on Ctrl+C
    stop_requested = False

    def signal_handler(sig, frame):
        nonlocal stop_requested
        stop_requested = True
        print("\n⏹️  Stopping poller...")

    signal.signal(signal.SIGINT, signal_handler)

    with DevicePoller(device, interval=interval, callback=on_update) as poller:
        while not stop_requested:
            time.sleep(0.5)

    print(f"✅ Polling stopped after {poll_count} readings.")


def main():
    parser = argparse.ArgumentParser(
        description="TP-Link HS110 Smart Plug Control Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --ip 192.168.1.100 --action info
  python main.py --ip 192.168.1.100 --action energy
  python main.py --ip 192.168.1.100 --action on
  python main.py --ip 192.168.1.100 --action off
  python main.py --ip 192.168.1.100 --action poll --interval 3
  python main.py --ip 192.168.1.100 --action led-on
  python main.py --ip 192.168.1.100 --action led-off
  python main.py --ip 192.168.1.100 --action raw --command '{"system":{"get_sysinfo":{}}}'
        """,
    )

    parser.add_argument(
        "--ip", required=True, help="TP-Link HS110 device IP address"
    )
    parser.add_argument(
        "--action",
        required=True,
        choices=["info", "energy", "on", "off", "poll", "led-on", "led-off", "raw"],
        help="Action to perform",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="Polling interval in seconds (default: 5.0, used with --action poll)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Socket timeout in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--command",
        type=str,
        default=None,
        help="Raw JSON command (used with --action raw)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging"
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    device = HS110Device(ip=args.ip, timeout=args.timeout)

    try:
        if args.action == "info":
            action_info(device)

        elif args.action == "energy":
            action_energy(device)

        elif args.action == "on":
            device.turn_on()
            print(f"✅ {args.ip} turned ON")

        elif args.action == "off":
            device.turn_off()
            print(f"✅ {args.ip} turned OFF")

        elif args.action == "led-on":
            device.set_led(True)
            print(f"✅ LED turned ON on {args.ip}")

        elif args.action == "led-off":
            device.set_led(False)
            print(f"✅ LED turned OFF on {args.ip}")

        elif args.action == "poll":
            action_poll(device, args.interval)

        elif args.action == "raw":
            if not args.command:
                print("❌ --command is required for raw action")
                sys.exit(1)
            cmd = json.loads(args.command)
            result = device.send_command(cmd)
            print_json(result)

    except (ConnectionError, TimeoutError) as e:
        print(f"❌ Connection error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
