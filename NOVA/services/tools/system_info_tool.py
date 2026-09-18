"""
System Information Tool
"""

import json
import re
import shutil
import socket
import subprocess

from services.tools.base import Tool
from services.system import SystemProfiler


class SystemInfoTool(Tool):

    def __init__(self):

        self.profiler = SystemProfiler()
        self.last_bluetooth_target = None

    @property
    def name(self):

        return "system"

    def can_handle(self, message: str):

        text = message.lower()

        keywords = [

            "system",

            "system info",

            "system information",

            "computer",

            "device",

            "machine",

            "my mac",

            "my laptop",

            "hardware",

            "specifications",

            "specs",

            "configuration",
            "ip address",
            "ipaddress",
            "my ip",
            "network",

        ]

        return any(
            keyword in text
            for keyword in keywords
        )

    def execute(self, message: str):

        text = message.lower()

        if self._is_bluetooth_query(text):
            if self._is_bluetooth_discoverable_toggle_request(text):
                return self._set_bluetooth_discoverable(text)
            if self._is_bluetooth_power_toggle_request(text):
                return self._set_bluetooth_power(text)
            if self._is_bluetooth_connect_request(text):
                return self._connect_bluetooth_device(message)
            if self._is_bluetooth_pair_request(text):
                return self._pair_bluetooth_device(message)
            if self._is_bluetooth_disconnect_request(text):
                return self._disconnect_bluetooth_device(message)
            if self._is_bluetooth_connection_status_query(text):
                return self._bluetooth_connection_status(message)
            if self._is_paired_devices_query(text):
                return self._paired_devices_response()
            if self._is_connected_devices_query(text):
                return self._connected_devices_response()
            if self._is_available_for_pairing_query(text):
                return self._available_for_pairing_response()
            return self._bluetooth_status_response()

        data = self.profiler.collect()

        network = data.get("network", {})
        primary_ip = self._resolve_ip(network)

        if "ip address" in text or "ipaddress" in text or "my ip" in text or text.strip() == "ip":
            ip_value = primary_ip or "Unavailable"
            return {
                "action": "system_info",
                "success": True,
                "data": {"ip_address": ip_value},
                "response": f"Your IP address is: {ip_value}",
            }

        general = data.get("general", {})
        hardware = data.get("hardware", {})
        cpu = data.get("cpu", {})
        memory = data.get("memory", {})
        storage = data.get("storage", {})

        response = f"""
System Information

Hostname : {general.get('hostname')}
User     : {general.get('username')}

Operating System : {general.get('platform')} {general.get('platform_release')}
Architecture     : {general.get('architecture')}

Model            : {hardware.get('model')}
Chip             : {hardware.get('chip')}
Memory           : {hardware.get('memory')}

CPU Usage        : {cpu.get('cpu_usage_percent')}%

RAM Used         : {memory.get('used_gb')} GB / {memory.get('total_gb')} GB

Disk Used        : {storage.get('current_drive', {}).get('used_gb')} GB
Disk Free        : {storage.get('current_drive', {}).get('free_gb')} GB

Current Time     : {general.get('current_time')}
Boot Time        : {general.get('boot_time')}
Uptime           : {general.get('uptime_seconds')} seconds
"""

        return {

            "action": "system_info",

            "success": True,

            "data": data,

            "response": response.strip()

        }

    def _resolve_ip(self, network: dict) -> str | None:
        primary_ip = network.get("primary_ip")
        if primary_ip and primary_ip not in {"127.0.0.1", "0.0.0.0"}:
            return primary_ip

        interfaces = network.get("interfaces", {})
        for _, info in interfaces.items():
            for ip in info.get("ipv4", []):
                if ip and not ip.startswith("127."):
                    return ip

        # Last-resort fallback that does not rely on hostname DNS resolution.
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            sock.close()
            if ip:
                return ip
        except Exception:
            pass

        return primary_ip

    def _is_bluetooth_query(self, text: str) -> bool:
        keywords = [
            "bluetooth",
            "pairing",
            "pair",
            "pair with",
            "available for pairing",
            "devices for pairing",
            "connect with",
            "connect to",
            "conect with",
            "conect to",
            "is it connected",
            "connected?",
            "connected device",
            "connected devices",
            "disconnect device",
            "disconnect bluetooth",
            "turn on bluetooth",
            "turn off bluetooth",
            "enable bluetooth",
            "disable bluetooth",
            "discoverable",
            "unpair",
        ]
        if any(keyword in text for keyword in keywords):
            return True

        return bool(
            "disconnect" in text
            and re.search(r"\b(buds|airpods|earbuds|airdopes|headset|speaker|keyboard|mouse|device)\b", text)
        )

    def _is_bluetooth_disconnect_request(self, text: str) -> bool:
        return any(
            phrase in text
            for phrase in [
                "disconnect",
                "remove device",
                "unpair",
            ]
        )

    def _is_bluetooth_power_toggle_request(self, text: str) -> bool:
        return any(
            phrase in text
            for phrase in [
                "turn on bluetooth",
                "turn off bluetooth",
                "enable bluetooth",
                "disable bluetooth",
                "bluetooth on",
                "bluetooth off",
            ]
        )

    def _is_bluetooth_discoverable_toggle_request(self, text: str) -> bool:
        return any(
            phrase in text
            for phrase in [
                "turn on discoverable",
                "turn off discoverable",
                "enable discoverable",
                "disable discoverable",
                "make bluetooth discoverable",
                "turn on bluetooth discoverable",
                "turn off bluetooth discoverable",
                "turn on bluetooth discoverable mode",
                "turn off bluetooth discoverable mode",
                "pairing mode",
            ]
        )

    def _is_available_for_pairing_query(self, text: str) -> bool:
        phrases = [
            "available for pairing",
            "devices for pairing",
            "set devices for pairing",
            "what devices are available for pairing",
            "show devices for pairing",
            "pairable devices",
            "available devices",
            "show available devices",
            "available bluetooth devices",
            "show available bluetooth devices",
            "what devices are available",
            "devices available to pair",
            "devices available",
            "show bluetooth devices",
            "bluetooth devices available",
        ]
        if any(phrase in text for phrase in phrases):
            return True
        # Regex for "available devices", "nearby devices", "show devices", etc
        if re.search(r"\b(available|nearby|scannable)\s+(bluetooth\s+)?devices?\b", text):
            return True
        if re.search(r"\b(show|list|display|see)\s+(bluetooth\s+)?devices\b", text):
            return True
        return False

    def _is_bluetooth_pair_request(self, text: str) -> bool:
        return bool(
            re.search(r"\b(pair with|pair to|pair)\b", text)
            and not self._is_available_for_pairing_query(text)
        )

    def _is_bluetooth_connect_request(self, text: str) -> bool:
        return bool(re.search(r"\b(connect with|connect to|conect with|conect to)\b", text))

    def _is_bluetooth_connection_status_query(self, text: str) -> bool:
        if text.strip() in {"connected", "connected?", "is it connected", "is it connected?"}:
            return True
        return bool(re.search(r"\bis\s+.+\s+connected\b", text))

    def _is_paired_devices_query(self, text: str) -> bool:
        """Detect queries for paired/saved devices."""
        phrases = [
            "paired devices",
            "paired device",
            "saved devices",
            "saved device",
            "my paired devices",
            "show paired devices",
            "show paired device",
            "list paired devices",
            "what devices are paired",
            "what devices are saved",
            "which devices are paired",
            "all paired devices",
            "all saved devices",
        ]
        if any(phrase in text for phrase in phrases):
            return True
        # Regex for patterns like "paired [devices/device]", "saved [devices/device]"
        return bool(re.search(r"\b(paired|saved)\s+(devices?|device)\b", text))

    def _is_connected_devices_query(self, text: str) -> bool:
        """Detect queries for currently connected devices."""
        phrases = [
            "connected devices",
            "connected device",
            "currently connected",
            "show connected devices",
            "show connected device",
            "list connected devices",
            "what devices are connected",
            "which devices are connected",
            "active devices",
            "active device",
            "show active devices",
            "currently paired",
        ]
        if any(phrase in text for phrase in phrases):
            return True
        # Regex for patterns like "connected devices", "active devices"
        return bool(re.search(r"\b(connected|active)\s+devices?\b", text))

    def _bluetooth_status_response(self) -> dict:
        bluetooth = self._collect_bluetooth_data()
        if bluetooth.get("error"):
            return {
                "action": "system_info",
                "success": False,
                "data": {"bluetooth": bluetooth},
                "response": f"Bluetooth status unavailable: {bluetooth['error']}",
            }

        controller = bluetooth.get("controller", {})
        connected = bluetooth.get("connected_devices", [])
        paired_not_connected = bluetooth.get("paired_not_connected", [])

        connected_lines = [
            f"- {device['name']} ({device.get('address', 'unknown address')})"
            for device in connected
        ] or ["- None"]

        paired_lines = [
            f"- {device['name']} ({device.get('address', 'unknown address')})"
            for device in paired_not_connected
        ] or ["- None"]

        discoverable = str(controller.get("discoverable", "Unknown"))
        pairing_readiness = (
            "Your Mac is discoverable and can accept new pairing requests."
            if discoverable.lower() == "on"
            else "Discoverable is off. Turn on Bluetooth discoverable mode for new pairing requests."
        )

        response = "\n".join(
            [
                "Bluetooth Status",
                "",
                f"Controller State : {controller.get('state', 'Unknown')}",
                f"Discoverable     : {discoverable}",
                f"Controller Addr  : {controller.get('address', 'Unknown')}",
                "",
                f"Connected Devices ({len(connected)}):",
                *connected_lines,
                "",
                f"Paired Not Connected ({len(paired_not_connected)}):",
                *paired_lines,
                "",
                f"Pairing Readiness: {pairing_readiness}",
            ]
        )

        return {
            "action": "system_info",
            "success": True,
            "data": {"bluetooth": bluetooth},
            "response": response,
        }

    def _collect_bluetooth_data(self) -> dict:
        try:
            output = subprocess.check_output(
                ["system_profiler", "SPBluetoothDataType"],
                text=True,
                stderr=subprocess.STDOUT,
            )
        except Exception as ex:
            return {"error": str(ex)}

        controller = {}
        connected_devices = []
        paired_not_connected = []
        section = None
        current_device = None

        for raw_line in output.splitlines():
            stripped = raw_line.strip()
            if not stripped:
                continue

            if stripped.startswith("Bluetooth Controller:"):
                section = "controller"
                current_device = None
                continue

            if stripped.startswith("Connected:"):
                section = "connected"
                current_device = None
                continue

            if stripped.startswith("Not Connected:"):
                section = "not_connected"
                current_device = None
                continue

            if section == "controller" and ":" in stripped:
                key, value = stripped.split(":", 1)
                key = key.strip().lower().replace(" ", "_")
                controller[key] = value.strip()
                continue

            if section in {"connected", "not_connected"} and stripped.endswith(":") and ": " not in stripped:
                device_name = stripped[:-1].strip()
                if device_name:
                    current_device = {"name": device_name}
                    if section == "connected":
                        connected_devices.append(current_device)
                    else:
                        paired_not_connected.append(current_device)
                continue

            if current_device and ":" in stripped:
                key, value = stripped.split(":", 1)
                key = key.strip().lower().replace(" ", "_")
                current_device[key] = value.strip()

        return {
            "controller": {
                "state": controller.get("state"),
                "discoverable": controller.get("discoverable"),
                "address": controller.get("address"),
                "chipset": controller.get("chipset"),
            },
            "connected_devices": connected_devices,
            "paired_not_connected": paired_not_connected,
        }

    def get_connected_devices_snapshot(self) -> dict:
        """Return currently connected Bluetooth and wired/external devices."""
        bluetooth = self._collect_bluetooth_data()
        bt_connected_raw = bluetooth.get("connected_devices", []) if isinstance(bluetooth, dict) else []

        bluetooth_connected = []
        for device in bt_connected_raw:
            if not isinstance(device, dict):
                continue
            bluetooth_connected.append(
                {
                    "name": device.get("name") or "Unknown Bluetooth Device",
                    "address": device.get("address"),
                    "battery": self._extract_battery_value(device),
                    "raw": device,
                }
            )

        wired_external = self._collect_wired_external_devices()
        wifi = self._collect_wifi_status()
        power = self._collect_power_status()

        return {
            "ok": True,
            "power": power,
            "wifi": wifi,
            "bluetooth": {
                "controller": bluetooth.get("controller", {}) if isinstance(bluetooth, dict) else {},
                "connected": bluetooth_connected,
            },
            "wired_external": wired_external,
        }

    def _collect_power_status(self) -> dict:
        """Best-effort macOS battery/charger status via pmset."""
        try:
            output = subprocess.check_output(
                ["pmset", "-g", "batt"],
                text=True,
                stderr=subprocess.STDOUT,
            )
        except Exception:
            return {
                "available": False,
                "source": None,
                "charging": None,
                "percentage": None,
                "state": None,
            }

        source_match = re.search(r"Now drawing from\s+'([^']+)'", output)
        source = source_match.group(1).strip() if source_match else None

        percent_match = re.search(r"(\d{1,3})%", output)
        percentage = int(percent_match.group(1)) if percent_match else None

        state_match = re.search(r"\d{1,3}%\s*;\s*([^;\n]+)", output)
        state = state_match.group(1).strip().lower() if state_match else None

        charging: bool | None
        if state is None:
            charging = None
        elif "discharging" in state:
            charging = False
        elif "charging" in state or "charged" in state or "finishing" in state:
            charging = True
        else:
            charging = source == "AC Power"

        return {
            "available": True,
            "source": source,
            "charging": charging,
            "percentage": percentage,
            "state": state,
        }

    def _collect_wifi_status(self) -> dict:
        """Best-effort Wi-Fi status with active interface and SSID on macOS."""
        iface = self._resolve_wifi_interface()
        if not iface:
            return {"connected": False, "ssid": None, "interface": None, "ssid_hidden": False}

        try:
            result = subprocess.run(
                ["networksetup", "-getairportnetwork", iface],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except Exception:
            return {"connected": False, "ssid": None, "interface": iface, "ssid_hidden": False}

        output = (result.stdout or result.stderr or "").strip()
        if result.returncode != 0 or "You are not associated" in output:
            ipconfig_status = self._collect_wifi_status_ipconfig(iface)
            if ipconfig_status.get("connected"):
                return ipconfig_status
            return self._collect_wifi_status_airport_fallback(iface)

        match = re.search(r"Current\s+Wi-Fi\s+Network:\s*(.+)$", output)
        if not match:
            ipconfig_status = self._collect_wifi_status_ipconfig(iface)
            if ipconfig_status.get("connected"):
                return ipconfig_status
            return self._collect_wifi_status_airport_fallback(iface)

        ssid = match.group(1).strip()
        if ssid.lower().startswith("<redacted"):
            return {
                "connected": True,
                "ssid": None,
                "interface": iface,
                "ssid_hidden": True,
            }
        return {
            "connected": bool(ssid),
            "ssid": ssid or None,
            "interface": iface,
            "ssid_hidden": False,
        }

    def _collect_wifi_status_ipconfig(self, iface: str) -> dict:
        """Fallback for macOS builds where networksetup may not return SSID correctly."""
        try:
            result = subprocess.run(
                ["ipconfig", "getsummary", iface],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except Exception:
            return {"connected": False, "ssid": None, "interface": iface, "ssid_hidden": False}

        if result.returncode != 0:
            return {"connected": False, "ssid": None, "interface": iface, "ssid_hidden": False}

        output = result.stdout or ""
        link_active = re.search(r"\bLinkStatusActive\s*:\s*TRUE\b", output, flags=re.IGNORECASE) is not None
        ssid_match = re.search(r"\bSSID\s*:\s*(.+)$", output, flags=re.MULTILINE)
        ssid = ssid_match.group(1).strip() if ssid_match else ""

        if not link_active and not ssid:
            return {"connected": False, "ssid": None, "interface": iface, "ssid_hidden": False}

        if ssid.lower().startswith("<redacted"):
            return {
                "connected": True,
                "ssid": None,
                "interface": iface,
                "ssid_hidden": True,
            }

        return {
            "connected": True,
            "ssid": ssid or "Connected Wi-Fi",
            "interface": iface,
            "ssid_hidden": False,
        }

    def _collect_wifi_status_airport_fallback(self, iface: str) -> dict:
        airport_bin = "/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport"
        if not shutil.which(airport_bin):
            return {"connected": False, "ssid": None, "interface": iface, "ssid_hidden": False}

        try:
            result = subprocess.run(
                [airport_bin, "-I"],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except Exception:
            return {"connected": False, "ssid": None, "interface": iface, "ssid_hidden": False}

        if result.returncode != 0:
            return {"connected": False, "ssid": None, "interface": iface, "ssid_hidden": False}

        output = result.stdout or ""
        ssid_match = re.search(r"\bSSID:\s*(.+)$", output, flags=re.MULTILINE)
        if not ssid_match:
            return {"connected": False, "ssid": None, "interface": iface, "ssid_hidden": False}

        ssid = ssid_match.group(1).strip()
        if ssid.lower().startswith("<redacted"):
            return {"connected": True, "ssid": None, "interface": iface, "ssid_hidden": True}
        return {
            "connected": bool(ssid),
            "ssid": ssid or None,
            "interface": iface,
            "ssid_hidden": False,
        }

    def _resolve_wifi_interface(self) -> str | None:
        try:
            result = subprocess.run(
                ["networksetup", "-listallhardwareports"],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except Exception:
            return None

        if result.returncode != 0:
            return None

        current_port = ""
        for line in result.stdout.splitlines():
            stripped = line.strip()
            if stripped.startswith("Hardware Port:"):
                current_port = stripped.split(":", 1)[1].strip().lower()
                continue
            if stripped.startswith("Device:") and current_port in {"wi-fi", "airport"}:
                return stripped.split(":", 1)[1].strip()
        return None

    def _extract_battery_value(self, device: dict) -> str | None:
        for key, value in device.items():
            key_l = str(key).lower()
            if "battery" in key_l and value not in (None, ""):
                val = str(value).strip()
                if val:
                    return val
        return None

    def _collect_wired_external_devices(self) -> list[dict]:
        combined: list[dict] = []
        combined.extend(self._collect_usb_devices())
        combined.extend(self._collect_wired_audio_devices())

        # Deduplicate by normalized name, preserving first occurrence.
        deduped: list[dict] = []
        seen: set[str] = set()
        for item in combined:
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _collect_usb_devices(self) -> list[dict]:
        try:
            raw = subprocess.check_output(
                ["system_profiler", "SPUSBDataType", "-json"],
                text=True,
                stderr=subprocess.STDOUT,
            )
            payload = json.loads(raw)
        except Exception:
            return []

        roots = payload.get("SPUSBDataType", []) if isinstance(payload, dict) else []
        devices: list[dict] = []

        def walk(node: dict) -> None:
            if not isinstance(node, dict):
                return

            name = str(node.get("_name") or "").strip()
            vendor_id = node.get("vendor_id")
            product_id = node.get("product_id")
            serial_num = node.get("serial_num")
            manufacturer = node.get("manufacturer")

            if name and any(v not in (None, "") for v in [vendor_id, product_id, serial_num]):
                name_l = name.lower()
                if not any(
                    blocked in name_l
                    for blocked in [
                        "internal",
                        "facetime",
                        "trackpad",
                        "keyboard",
                        "touch bar",
                    ]
                ):
                    devices.append(
                        {
                            "name": name,
                            "type": "usb",
                            "manufacturer": manufacturer,
                            "vendor_id": vendor_id,
                            "product_id": product_id,
                            "serial": serial_num,
                        }
                    )

            for child in node.get("_items", []) or []:
                walk(child)

        for root in roots:
            walk(root)

        return devices

    def _collect_wired_audio_devices(self) -> list[dict]:
        """Best-effort wired audio detection (e.g. headphones/headset)."""
        try:
            output = subprocess.check_output(
                ["system_profiler", "SPAudioDataType"],
                text=True,
                stderr=subprocess.STDOUT,
            )
        except Exception:
            return []

        devices: list[dict] = []
        current_name: str | None = None
        current_transport: str | None = None
        current_connected: str | None = None
        has_output = False

        def flush_current() -> None:
            nonlocal current_name, current_transport, current_connected, has_output
            if not current_name:
                return
            name_l = current_name.lower()
            if has_output and not any(skip in name_l for skip in ["built-in", "speaker"]):
                devices.append(
                    {
                        "name": current_name,
                        "type": "audio",
                        "transport": current_transport,
                        "connected": current_connected,
                    }
                )
            current_name = None
            current_transport = None
            current_connected = None
            has_output = False

        for line in output.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.endswith(":") and ": " not in stripped:
                flush_current()
                current_name = stripped[:-1].strip()
                continue

            if current_name and stripped.startswith("Transport:"):
                current_transport = stripped.split(":", 1)[1].strip()
                continue

            if current_name and stripped.startswith("Connected:"):
                current_connected = stripped.split(":", 1)[1].strip()
                continue

            if current_name and (
                stripped.startswith("Output Channels:")
                or stripped.startswith("Default Output Device:")
                or stripped.startswith("Output Source:")
            ):
                has_output = True

        flush_current()
        return devices

    def _set_bluetooth_power(self, text: str) -> dict:
        if shutil.which("blueutil") is None:
            return self._missing_blueutil_response("change Bluetooth power")

        power_value = "1" if any(p in text for p in ["turn on bluetooth", "enable bluetooth", "bluetooth on"]) else "0"

        try:
            result = subprocess.run(
                ["blueutil", "--power", power_value],
                capture_output=True,
                text=True,
                timeout=12,
            )
        except Exception as ex:
            return {
                "action": "system_info",
                "success": False,
                "response": f"Failed to change Bluetooth power: {ex}",
            }

        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "Unknown error").strip()
            return {
                "action": "system_info",
                "success": False,
                "response": f"Failed to change Bluetooth power: {error_text}",
            }

        state_text = "on" if power_value == "1" else "off"
        return {
            "action": "system_info",
            "success": True,
            "response": f"Bluetooth is now {state_text}.",
        }

    def _set_bluetooth_discoverable(self, text: str) -> dict:
        if shutil.which("blueutil") is None:
            return self._missing_blueutil_response("change Bluetooth discoverable mode")

        discoverable_on = any(
            p in text
            for p in [
                "turn on discoverable",
                "enable discoverable",
                "make bluetooth discoverable",
                "turn on bluetooth discoverable",
                "turn on bluetooth discoverable mode",
                "pairing mode",
            ]
        )
        discoverable_value = "1" if discoverable_on else "0"

        try:
            result = subprocess.run(
                ["blueutil", "--discoverable", discoverable_value],
                capture_output=True,
                text=True,
                timeout=12,
            )
        except Exception as ex:
            return {
                "action": "system_info",
                "success": False,
                "response": f"Failed to change Bluetooth discoverable mode: {ex}",
            }

        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "Unknown error").strip()
            return {
                "action": "system_info",
                "success": False,
                "response": f"Failed to change Bluetooth discoverable mode: {error_text}",
            }

        state_text = "on" if discoverable_on else "off"
        return {
            "action": "system_info",
            "success": True,
            "response": f"Bluetooth discoverable mode is now {state_text}.",
        }

    def _available_for_pairing_response(self) -> dict:
        bluetooth = self._collect_bluetooth_data()
        if bluetooth.get("error"):
            return {
                "action": "system_info",
                "success": False,
                "response": f"Bluetooth status unavailable: {bluetooth['error']}",
            }

        controller = bluetooth.get("controller", {})
        discoverable = str(controller.get("discoverable", "Unknown"))

        nearby_lines = []
        nearby_devices = self._scan_nearby_bluetooth_devices()
        for device in nearby_devices:
            name = device.get("name") or "Unknown"
            address = device.get("address") or "unknown address"
            nearby_lines.append(f"- {name} ({address})")

        if not nearby_lines:
            nearby_lines = ["- None detected in this scan"]

        discoverable_hint = (
            "Your Mac is discoverable for incoming pairing requests."
            if discoverable.lower() == "on"
            else "Discoverable is off. Say 'turn on bluetooth discoverable mode' to accept incoming pairing requests."
        )

        response = "\n".join(
            [
                "Available Devices For Pairing",
                "",
                f"Discoverable: {discoverable}",
                discoverable_hint,
                "",
                f"Nearby Devices ({len(nearby_devices)}):",
                *nearby_lines,
                "",
                "To pair, say: pair with <device name>",
            ]
        )

        return {
            "action": "system_info",
            "success": True,
            "data": {
                "bluetooth": bluetooth,
                "nearby_scan": nearby_devices,
            },
            "response": response,
        }

    def _paired_devices_response(self) -> dict:
        """Return ONLY paired (saved) devices, whether connected or not."""
        bluetooth = self._collect_bluetooth_data()
        if bluetooth.get("error"):
            return {
                "action": "system_info",
                "success": False,
                "response": f"Bluetooth status unavailable: {bluetooth['error']}",
            }

        connected = bluetooth.get("connected_devices", [])
        paired_not_connected = bluetooth.get("paired_not_connected", [])
        
        all_paired = []
        for device in connected:
            name = device.get("name") or "Unknown"
            address = device.get("address") or "unknown address"
            all_paired.append(f"- {name} ({address}) [connected]")
        
        for device in paired_not_connected:
            name = device.get("name") or "Unknown"
            address = device.get("address") or "unknown address"
            all_paired.append(f"- {name} ({address})")

        paired_lines = all_paired or ["- None"]

        response = "\n".join(
            [
                f"Paired Devices ({len(all_paired)}):",
                *paired_lines,
            ]
        )

        return {
            "action": "system_info",
            "success": True,
            "data": {"bluetooth": bluetooth},
            "response": response,
        }

    def _connected_devices_response(self) -> dict:
        """Return ONLY currently connected devices."""
        bluetooth = self._collect_bluetooth_data()
        if bluetooth.get("error"):
            return {
                "action": "system_info",
                "success": False,
                "response": f"Bluetooth status unavailable: {bluetooth['error']}",
            }

        connected = bluetooth.get("connected_devices", [])
        
        connected_lines = []
        for device in connected:
            name = device.get("name") or "Unknown"
            address = device.get("address") or "unknown address"
            connected_lines.append(f"- {name} ({address})")

        if not connected_lines:
            connected_lines = ["- None"]

        response = "\n".join(
            [
                f"Connected Devices ({len(connected)}):",
                *connected_lines,
            ]
        )

        return {
            "action": "system_info",
            "success": True,
            "data": {"bluetooth": bluetooth},
            "response": response,
        }

    def _scan_nearby_bluetooth_devices(self) -> list:
        if shutil.which("blueutil") is None:
            return []

        try:
            result = subprocess.run(
                ["blueutil", "--inquiry", "6", "--format", "json"],
                capture_output=True,
                text=True,
                timeout=12,
            )
        except Exception:
            return []

        if result.returncode != 0:
            return []

        raw = (result.stdout or "").strip()
        if not raw:
            return []

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [item for item in parsed if isinstance(item, dict)]
        except Exception:
            return []
        return []

    def _pair_bluetooth_device(self, message: str) -> dict:
        if shutil.which("blueutil") is None:
            return self._missing_blueutil_response("pair Bluetooth devices")

        target = self._extract_pair_target(message)
        if not target:
            return {
                "action": "system_info",
                "success": False,
                "response": "Tell me which device to pair with, for example: pair with OnePlus Buds 3",
            }

        bluetooth = self._collect_bluetooth_data()
        known_devices = []
        known_devices.extend(bluetooth.get("paired_not_connected", []))
        known_devices.extend(bluetooth.get("connected_devices", []))
        known_devices.extend(self._scan_nearby_bluetooth_devices())

        target_id = self._resolve_bluetooth_device_identifier(target, known_devices)
        if not target_id:
            target_id = target

        # Try pairing first; if already paired, fallback to connect.
        pair_result = self._run_blueutil_command(["blueutil", "--pair", target_id], timeout=20)
        if pair_result["ok"]:
            self.last_bluetooth_target = {"name": target, "id": target_id}
            return {
                "action": "system_info",
                "success": True,
                "response": f"Paired with {target} ({target_id}).",
            }

        connect_result = self._run_blueutil_command(["blueutil", "--connect", target_id], timeout=20)
        if connect_result["ok"]:
            self.last_bluetooth_target = {"name": target, "id": target_id}
            return {
                "action": "system_info",
                "success": True,
                "response": f"Connected to {target} ({target_id}).",
            }

        error_text = connect_result["error"] or pair_result["error"] or "Unknown error"
        return {
            "action": "system_info",
            "success": False,
            "response": f"Could not pair/connect {target} ({target_id}): {error_text}",
        }

    def _connect_bluetooth_device(self, message: str) -> dict:
        if shutil.which("blueutil") is None:
            return self._missing_blueutil_response("connect Bluetooth devices")

        target = self._extract_connect_target(message)
        if not target:
            return {
                "action": "system_info",
                "success": False,
                "response": "Tell me which device to connect, for example: connect with Airdopes 441",
            }

        bluetooth = self._collect_bluetooth_data()
        known_devices = []
        known_devices.extend(bluetooth.get("paired_not_connected", []))
        known_devices.extend(bluetooth.get("connected_devices", []))
        known_devices.extend(self._scan_nearby_bluetooth_devices())

        target_id = self._resolve_bluetooth_device_identifier(target, known_devices) or target
        self.last_bluetooth_target = {"name": target, "id": target_id}

        connect_result = self._run_blueutil_command(["blueutil", "--connect", target_id], timeout=20)
        if not connect_result["ok"]:
            return {
                "action": "system_info",
                "success": False,
                "response": f"Could not start connection to {target} ({target_id}): {connect_result['error']}",
            }

        wait_result = self._run_blueutil_command(["blueutil", "--wait-connect", target_id, "18"], timeout=22)
        connected, status_error = self._is_device_connected(target_id)

        if connected:
            return {
                "action": "system_info",
                "success": True,
                "response": f"Connected to {target} ({target_id}).",
            }

        if wait_result["ok"]:
            return {
                "action": "system_info",
                "success": True,
                "response": f"Connected to {target} ({target_id}).",
            }

        monitor_error = wait_result.get("error") or status_error or "connection not confirmed yet"
        return {
            "action": "system_info",
            "success": False,
            "response": f"Connection to {target} is still pending or failed: {monitor_error}",
        }

    def _bluetooth_connection_status(self, message: str) -> dict:
        if shutil.which("blueutil") is None:
            return self._missing_blueutil_response("check Bluetooth connection status")

        target = self._extract_status_target(message)
        target_id = None
        target_name = None

        if target:
            if target.lower() in {"it", "this", "device"} and self.last_bluetooth_target:
                target = None

        if target:
            bluetooth = self._collect_bluetooth_data()
            known_devices = []
            known_devices.extend(bluetooth.get("paired_not_connected", []))
            known_devices.extend(bluetooth.get("connected_devices", []))
            known_devices.extend(self._scan_nearby_bluetooth_devices())
            target_id = self._resolve_bluetooth_device_identifier(target, known_devices) or target
            target_name = target
        elif self.last_bluetooth_target:
            target_id = self.last_bluetooth_target.get("id")
            target_name = self.last_bluetooth_target.get("name") or target_id

        if not target_id:
            return {
                "action": "system_info",
                "success": False,
                "response": "No recent Bluetooth target to monitor. Say: connect with <device name> first.",
            }

        connected, status_error = self._is_device_connected(target_id)
        if connected:
            return {
                "action": "system_info",
                "success": True,
                "response": f"{target_name} is connected.",
            }

        wait_result = self._run_blueutil_command(["blueutil", "--wait-connect", target_id, "15"], timeout=19)
        connected, status_error = self._is_device_connected(target_id)
        if connected:
            return {
                "action": "system_info",
                "success": True,
                "response": f"{target_name} is now connected.",
            }

        error_text = wait_result.get("error") or status_error or "still pending"
        return {
            "action": "system_info",
            "success": False,
            "response": f"{target_name} is not connected yet. Monitoring result: {error_text}",
        }

    def _extract_pair_target(self, message: str) -> str | None:
        text = message.strip()
        patterns = [
            r"pair with\s+(.+)$",
            r"pair to\s+(.+)$",
            r"connect to\s+(.+)$",
            r"connect with\s+(.+)$",
            r"pair\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip().strip(".?!")
                if candidate:
                    return candidate
        return None

    def _extract_connect_target(self, message: str) -> str | None:
        text = message.strip()
        patterns = [
            r"connect with\s+(.+)$",
            r"connect to\s+(.+)$",
            r"conect with\s+(.+)$",
            r"conect to\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip().strip(".?!")
                if candidate:
                    return candidate
        return None

    def _extract_status_target(self, message: str) -> str | None:
        text = message.strip()
        patterns = [
            r"is\s+(.+?)\s+connected\??$",
            r"connected to\s+(.+)$",
            r"connection status(?: for)?\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip().strip(".?!")
                if candidate:
                    return candidate
        return None

    def _is_device_connected(self, target_id: str) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                ["blueutil", "--is-connected", target_id],
                capture_output=True,
                text=True,
                timeout=8,
            )
        except Exception as ex:
            return False, str(ex)

        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "Unknown error").strip()
            return False, error_text

        value = (result.stdout or "").strip()
        return value == "1", ""

    def _resolve_bluetooth_device_identifier(self, target: str, devices: list) -> str | None:
        mac_match = re.search(r"([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}", target)
        if mac_match:
            return mac_match.group(0)

        target_l = target.lower().strip()
        for device in devices:
            name = str(device.get("name", "")).strip()
            if not name:
                continue
            if target_l == name.lower() or target_l in name.lower():
                address = device.get("address")
                if address:
                    return str(address)
                return name

        return None

    def _run_blueutil_command(self, command: list, timeout: int = 15) -> dict:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except Exception as ex:
            return {"ok": False, "error": str(ex)}

        if result.returncode == 0:
            return {"ok": True, "error": ""}

        error_text = (result.stderr or result.stdout or "Unknown error").strip()
        return {"ok": False, "error": error_text}

    def _disconnect_bluetooth_device(self, message: str) -> dict:
        if shutil.which("blueutil") is None:
            return self._missing_blueutil_response("disconnect Bluetooth devices")

        target = self._extract_disconnect_target(message)
        if not target:
            return {
                "action": "system_info",
                "success": False,
                "response": "Tell me which Bluetooth device to disconnect, for example: disconnect OnePlus Buds 3",
            }

        bluetooth = self._collect_bluetooth_data()
        if bluetooth.get("error"):
            return {
                "action": "system_info",
                "success": False,
                "response": f"Bluetooth status unavailable: {bluetooth['error']}",
            }

        connected = bluetooth.get("connected_devices", [])
        if not connected:
            return {
                "action": "system_info",
                "success": False,
                "response": "No Bluetooth devices are currently connected.",
            }

        target_address = None
        target_name = target

        mac_match = re.search(r"([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", target)
        if mac_match:
            target_address = mac_match.group(0)

        if target_address is None:
            lower_target = target.lower()
            for device in connected:
                name = str(device.get("name", ""))
                if lower_target in name.lower():
                    target_name = name
                    target_address = device.get("address")
                    break

        if not target_address:
            connected_names = ", ".join(d.get("name", "Unknown") for d in connected)
            return {
                "action": "system_info",
                "success": False,
                "response": f"Could not find a connected device matching '{target}'. Connected: {connected_names}",
            }

        try:
            result = subprocess.run(
                ["blueutil", "--disconnect", target_address],
                capture_output=True,
                text=True,
                timeout=15,
            )
        except Exception as ex:
            return {
                "action": "system_info",
                "success": False,
                "response": f"Failed to disconnect Bluetooth device: {ex}",
            }

        if result.returncode != 0:
            error_text = (result.stderr or result.stdout or "Unknown error").strip()
            return {
                "action": "system_info",
                "success": False,
                "response": f"Disconnect failed for {target_name} ({target_address}): {error_text}",
            }

        # Confirm disconnection before reporting success.
        self._run_blueutil_command(["blueutil", "--wait-disconnect", target_address, "10"], timeout=12)
        still_connected, status_error = self._is_device_connected(target_address)
        if still_connected:
            return {
                "action": "system_info",
                "success": False,
                "response": (
                    f"I attempted to disconnect {target_name} ({target_address}), "
                    "but it is still connected."
                ),
            }

        if status_error:
            return {
                "action": "system_info",
                "success": True,
                "response": (
                    f"Disconnect command sent to {target_name} ({target_address}). "
                    f"Final status check returned: {status_error}"
                ),
            }

        return {
            "action": "system_info",
            "success": True,
            "response": f"Disconnected {target_name} ({target_address}).",
        }

    def _extract_disconnect_target(self, message: str) -> str | None:
        text = message.strip()
        patterns = [
            r"disconnect(?:\s+my)?(?:\s+bluetooth)?(?:\s+device)?\s+(.+)$",
            r"unpair(?:\s+my)?(?:\s+bluetooth)?(?:\s+device)?\s+(.+)$",
            r"remove(?:\s+my)?(?:\s+bluetooth)?(?:\s+device)?\s+(.+)$",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                candidate = match.group(1).strip().strip(".?!")
                if candidate:
                    return candidate
        return None

    def _missing_blueutil_response(self, purpose: str) -> dict:
        package = "blueutil"
        return {
            "action": "system_info",
            "success": False,
            "needs_install": True,
            "package": package,
            "purpose": purpose,
            "install_args": ["brew", "install", package],
            "response": (
                f"{package} is required to {purpose}. "
                f"Should I install it now? Reply exactly: 'yes install {package}' or 'no'."
            ),
        }