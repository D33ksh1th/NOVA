"""
Network Collector
"""

import socket
import uuid

import psutil

from .base import Collector


class NetworkCollector(Collector):

    @property
    def name(self):

        return "network"

    def collect(self):

        try:

            interfaces = {}

            addresses = psutil.net_if_addrs()

            stats = psutil.net_if_stats()

            for interface, addrs in addresses.items():

                info = {
                    "ipv4": [],
                    "ipv6": [],
                    "mac": None,
                    "is_up": False,
                    "speed_mbps": None,
                }

                if interface in stats:

                    info["is_up"] = stats[interface].isup
                    info["speed_mbps"] = stats[interface].speed

                for addr in addrs:

                    # IPv4
                    if addr.family == socket.AF_INET:

                        info["ipv4"].append(addr.address)

                    # IPv6
                    elif addr.family == socket.AF_INET6:

                        info["ipv6"].append(addr.address)

                    # MAC Address
                    elif str(addr.family) == "AddressFamily.AF_LINK":

                        info["mac"] = addr.address

                interfaces[interface] = info

            return {

                "hostname": socket.gethostname(),

                "fqdn": socket.getfqdn(),

                "primary_ip": socket.gethostbyname(
                    socket.gethostname()
                ),

                "mac_address": ":".join(
                    f"{(uuid.getnode() >> ele) & 0xff:02x}"
                    for ele in range(40, -8, -8)
                ),

                "interfaces": interfaces,

            }

        except Exception as ex:

            return {

                "error": str(ex)

            }