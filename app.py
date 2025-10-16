# Copyright 2024, 2025 Prefeitura Municipal de Campo Largo <analistas@campolargo.pr.gov.br>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import csv
import subprocess
import time

from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.routing import BaseConverter


class MacAddress(BaseConverter):
    regex = r"[0-9a-f]{12}"


class IpAddress(BaseConverter):
    regex = r"(?:0|1[0-9]{0,2}|2([0-4][0-9]?|5[0-5]?|[6-9])?|[3-9][0-9]?)(?:\.(?:0|1[0-9]{0,2}|2([0-4][0-9]?|5[0-5]?|[6-9])?|[3-9][0-9]?)){3}"


class User(BaseConverter):
    regex = r"[0-9]{4}"


app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=2, x_proto=1, x_host=1, x_prefix=1)
app.url_map.converters["mac_address"] = MacAddress
app.url_map.converters["ip_address"] = IpAddress
app.url_map.converters["user"] = User
SERVER_ADDRESS = "127.0.0.1"
SERVER_PORT = "10051"
MAX_RETRIES = 10
HOSTS = {}


class ZabbixSenderError(Exception):
    def __init__(self):
        super().__init__("Reached maximum number of retries.")


def load_hosts():
    global HOSTS

    try:
        with open("hosts.csv", newline="") as file:
            hosts_csv = csv.DictReader(file)
            HOSTS = {host["MAC"]: host["Name"] for host in hosts_csv}
    except FileNotFoundError:
        pass


def zabbix_sender(mac_address, key, value):
    for _ in range(MAX_RETRIES):
        try:
            subprocess.run(
                ["zabbix_sender", "-z", SERVER_ADDRESS, "-p", SERVER_PORT, "-s", f"voip_{mac_address}", "-k", key, "-o", value], check=True
            )
            return
        except subprocess.CalledProcessError:
            time.sleep(1)

    raise ZabbixSenderError()


def voip_discovery(mac_address):
    load_hosts()
    zabbix_sender("discovery", "voip.discovery", f'[{{"{{#MAC}}": "{mac_address}", "{{#NAME}}": "{HOSTS.get(mac_address, "")}", "{{#IP}}": "{request.remote_addr}"}}]')


def registration_discovery(mac_address, user):
    zabbix_sender(mac_address, "registration.discovery", f'[{{"{{#USER}}": {user}}}]')


@app.get("/test")
def test():
    return "It's alive!"


@app.get("/<mac_address:mac_address>/registration_succeeded/<user:user>")
def registration_succeeded(mac_address, user):
    voip_discovery(mac_address)
    registration_discovery(mac_address, user)
    zabbix_sender(mac_address, f"registration[{user}]", "2")
    return ""


@app.get("/<mac_address:mac_address>/registration_disabled/<user:user>")
def registration_disabled(mac_address, user):
    voip_discovery(mac_address)
    registration_discovery(mac_address, user)
    zabbix_sender(mac_address, f"registration[{user}]", "1")
    return ""


@app.get("/<mac_address:mac_address>/registration_failed/<user:user>")
def registration_failed(mac_address, user):
    voip_discovery(mac_address)
    registration_discovery(mac_address, user)
    zabbix_sender(mac_address, f"registration[{user}]", "0")
    return ""


@app.get("/<mac_address:mac_address>/dnd_enabled")
def dnd_enabled(mac_address):
    voip_discovery(mac_address)
    zabbix_sender(mac_address, "dnd", "1")
    return ""


@app.get("/<mac_address:mac_address>/dnd_disabled")
def dnd_disabled(mac_address):
    voip_discovery(mac_address)
    zabbix_sender(mac_address, "dnd", "0")
    return ""


@app.get("/<mac_address:mac_address>/mute")
def mute(mac_address):
    voip_discovery(mac_address)
    zabbix_sender(mac_address, "mute", "1")
    return ""


@app.get("/<mac_address:mac_address>/unmute")
def unmute(mac_address):
    voip_discovery(mac_address)
    zabbix_sender(mac_address, "mute", "0")
    return ""


@app.get("/<mac_address:mac_address>/ip_changed/<ip_address:ip_address>")
def ip_changed(mac_address, ip_address):
    voip_discovery(mac_address)
    zabbix_sender(mac_address, "ip", ip_address)
    return ""
