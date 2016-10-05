# Copyright 2016 Mycroft AI, Inc.
#
# This file is part of Mycroft Core.
#
# Mycroft Core is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Mycroft Core is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Mycroft Core.  If not, see <http://www.gnu.org/licenses/>.
import sys
import traceback
import threading
from SimpleHTTPServer import SimpleHTTPRequestHandler
from SocketServer import TCPServer
from shutil import copyfile
from subprocess import Popen, PIPE
from threading import Thread
from time import sleep
import urlparse

import os
import time
from os.path import dirname, realpath
from pyric import pyw
from wifi import Cell

from mycroft.client.enclosure.api import EnclosureAPI
from mycroft.configuration import ConfigurationManager
from mycroft.messagebus.client.ws import WebsocketClient
from mycroft.messagebus.message import Message
from mycroft.util import str2bool
from mycroft.util.log import getLogger

__author__ = 'aatchison'

LOG = getLogger("WiFiClient")


def cli_no_output(*args):
    LOG.info("Command: %s" % list(args))
    proc = Popen(args=args, stdout=PIPE, stderr=PIPE)
    stdout, stderr = proc.communicate()
    return {'code': proc.returncode, 'stdout': stdout, 'stderr': stderr}


def cli(*args):
    LOG.info("Command: %s" % list(args))
    proc = Popen(args=args, stdout=PIPE, stderr=PIPE)
    stdout, stderr = proc.communicate()
    result = {'code': proc.returncode, 'stdout': stdout, 'stderr': stderr}
    LOG.info("Command result: %s" % result)
    return result


def wpa(*args):
    idx = 0
    result = cli('wpa_cli', '-i', *args)
    out = result.get("stdout", "\n")
    if "interface" in out:
        idx = 1
    return str(out.split("\n")[idx])


def sysctrl(*args):
    return cli('systemctl', *args)

REDIRECT_RESPONSE = """Location: http://start.mycroft.ai
"""
DUMMY_RESPONSE = """Content-type: text/html
<html>
<head>
<title>Python Test</title>
</head>
<body>
Test page...success.
</body>
</html>
"""

SCRIPT_DIR = dirname(realpath(__file__))


class MycroftHTTPRequestHandler(SimpleHTTPRequestHandler):

    def do_HEAD(self):
        LOG.info("do_HEAD being called....")
        if not self.redirect():
            SimpleHTTPRequestHandler.do_HEAD(self)

    def do_GET(self):
        LOG.info("do_GET being called....")
        if not self.redirect():
            SimpleHTTPRequestHandler.do_GET(self)

    def redirect(self):
        try:
            LOG.info("***********************")
            LOG.info("**   HTTP Request   ***")
            LOG.info("***********************")
            LOG.info("Requesting: "+self.path)
            LOG.info("REMOTE_ADDR:"+self.client_address[0])
            LOG.info("SERVER_NAME:"+self.server.server_address[0])
            LOG.info("SERVER_PORT:"+str(self.server.server_address[1]))
            LOG.info("SERVER_PROTOCOL:"+self.request_version)
            LOG.info("HEADERS...")
            LOG.info(self.headers)
            LOG.info("***********************")

            # path = self.translate_path(self.path)
            if "start.mycroft.ai" in self.headers['host']:
                LOG.info("No redirect")
                return False
            else:
                LOG.info("303 redirect to http://start.mycroft.ai")
                self.send_response(303)
                self.send_header("Location", "http://start.mycroft.ai")
                self.end_headers()
                return True

            # res = urlparse.urlparse(self.path)
            # if res.scheme == 'http':
            #     reqFile = os.path.join(SCRIPT_DIR, 'web', res.path)
            # else:
            #     LOG.info("Unexpected scheme")
            #     return
            # LOG.info("Looking for: "+reqFile)
            # if os.path.isfile(reqFile):
            #     LOG.info("Found!  Serving...")
            #     return SimpleHTTPRequestHandler.do_GET(self)
            #
            # if "start.mycroft.ai" not in self.headers:
            #    LOG.info("Redirect to: /start.mycroft.ai")
            #    self.send_response(301)
            #    self.send_header("Location", "http://start.mycroft.ai")
            #    # # self.send_header("Content-length", len(DUMMY_RESPONSE))
            #    self.end_headers()
            #    # # self.wfile.write(DUMMY_RESPONSE)
            #    return
            # self.path = '/index.html'
            #
            # return SimpleHTTPRequestHandler.do_GET(self)
        except:
            tb = traceback.format_exc()
            LOG.info("exception caught")
            LOG.info(tb)


class WebServer(Thread):
    def __init__(self, host, port):
        super(WebServer, self).__init__()
        self.daemon = True
        LOG.info("Creating TCPServer...")
        self.server = TCPServer((host, port), MycroftHTTPRequestHandler)
        # self.server = TCPServer((host, port), SimpleHTTPRequestHandler)
        LOG.info("Created TCPServer")

    def run(self):
        LOG.info("Starting Web Server at %s:%s" % self.server.server_address)
        os.chdir(os.path.join(SCRIPT_DIR, 'web'))
        LOG.info("Serving from: %s" % os.path.join(SCRIPT_DIR, 'web'))
        self.server.serve_forever()
        LOG.info("Web Server stopped!")


class AccessPoint:
    template = """interface={interface}
bind-interfaces
server={server}
domain-needed
bogus-priv
dhcp-range={dhcp_range_start}, {dhcp_range_end}, 12h
address=/#/{server}
"""

    def __init__(self, wiface):
        self.wiface = wiface
        self.iface = 'p2p-wlan0-0'
        self.subnet = '172.24.1'
        self.ip = self.subnet+'.1'
        self.ip_start = self.subnet+'.50'
        self.ip_end = self.subnet+'.150'
        self.password = None

    def up(self):
        try:
            card = pyw.getcard(self.iface)
        except:
            wpa(self.wiface, 'p2p_group_add', 'persistent=0')
            self.iface = self.get_iface()
            self.password = wpa(self.iface, 'p2p_get_passphrase')
            card = pyw.getcard(self.iface)
        pyw.inetset(card, self.ip)
        copyfile('/etc/dnsmasq.conf', '/tmp/dnsmasq-bk.conf')
        self.save()
        sysctrl('restart', 'dnsmasq.service')

    def get_iface(self):
        for iface in pyw.winterfaces():
            if "p2p" in iface:
                return iface

    def down(self):
        sysctrl('stop', 'dnsmasq.service')
        sysctrl('disable', 'dnsmasq.service')
        wpa(self.wiface, 'p2p_group_remove', self.iface)
        copyfile('/tmp/dnsmasq-bk.conf', '/etc/dnsmasq.conf')

    def save(self):
        data = {
            "interface": self.iface,
            "server": self.ip,
            "dhcp_range_start": self.ip_start,
            "dhcp_range_end": self.ip_end
        }
        try:
            LOG.info("Writing to: /etc/dnsmasq.conf")
            with open('/etc/dnsmasq.conf', 'w') as f:
                f.write(self.template.format(**data))
        except Exception as e:
            LOG.error("Fail to write: /etc/dnsmasq.conf")
            raise e


class WiFi:
    NAME = "WiFiClient"

    def __init__(self):
        self.iface = pyw.winterfaces()[0]
        self.ap = AccessPoint(self.iface)
        self.server = None
        self.client = WebsocketClient()
        self.enclosure = EnclosureAPI(self.client)
        self.config = ConfigurationManager.get().get(self.NAME)
        self.init_events()
        self.first_setup()
        self.threadConMon = None
        self.threadConMon_stop = threading.Event()

    def init_events(self):
        self.client.on('mycroft.wifi.start', self.start)
        self.client.on('mycroft.wifi.stop', self.stop)
        self.client.on('mycroft.wifi.scan', self.scan)
        self.client.on('mycroft.wifi.connect', self.connect)

    def first_setup(self):
        if str2bool(self.config.get('setup')):
            self.start()

    def start(self, event=None):
        # Fire up the MYCROFT access point for the user to connect to
        # with a phone or computer.
        LOG.info("Starting access point...")

        # zap any existing leases file because:
        # a) we don't care about previous leases
        # b) we will monitor it for connections
        # os.remove('/var/lib/misc/dnsmasq.leases')

        # Fire up our access point
        self.ap.up()
        if not self.server:
            LOG.info("Creating web server...")
            self.server = WebServer(self.ap.ip, 80)
            LOG.info("Starting web server...")
            self.server.start()
            LOG.info("Created web server.")

        self.connectionPrompt("Allow me to walk you through the wifi setup process,")
        LOG.info("Access point started!\n%s" % self.ap.__dict__)
        self.startConnectionMonitor()

    def connectionPrompt(self, prefix):
        # let the user know to connect to it...
        passwordSpelled = ", ".join(self.ap.password)
        self.SpeakAndShow(
           prefix+" Connect your phone or computer to the wifi network MYCROFT and enter the uppercase password "+passwordSpelled,
           self.ap.password)

    def startConnectionMonitor(self):
        LOG.info("Starting monitor...\n")
        if self.threadConMon is not None:
            LOG.info("Killing old thread...\n")
            self.threadConMon_stop.set()
            self.threadConMon_stop.wait()

        self.threadConMon = threading.Thread(target=self.doConnectionMonitor, args={})
        self.threadConMon.daemon = True
        self.threadConMon.start()
        LOG.info("Monitor setup complete.\n")

    def SpeakAndShow(self, speak, show):
        self.client.emit(Message("speak", metadata={
            'utterance': speak}))

        # TODO: This should not be necessary, just sleeping to allow
        #       the system to catch up.  Remove the sleep once this is cleaned
        #       up.
        sleep(0.25)
        self.enclosure.mouth_text(show)

    def doConnectionMonitor(self):
        LOG.info("Starting monitor thread...\n")
        mtimeLast = os.path.getmtime('/var/lib/misc/dnsmasq.leases')
        bHasConnected = False
        cARPFailures = 0

        while not self.threadConMon_stop.isSet():
            # do our monitoring...
            mtime = os.path.getmtime('/var/lib/misc/dnsmasq.leases')
            if mtimeLast != mtime:
                # Something changed in the dnsmasq lease file -
                # presumably a (re)new lease
                self.SpeakAndShow(
                    "Now you can open your browser and go to start dot mycroft dot A I, then follow the instructions given there",
                    "start.mycroft.ai")
                bHasConnected = True
                cARPFailures = 0
                mtimeLast = mtime
                # Give the connection time to stabilize and get ARP entries
                sleep(10)

            if bHasConnected and False:
                # Flush the ARP entries associated with our access point
                # This will require all network hardware to re-register
                # with the ARP tables if still present.
                # call "ip -s -s neigh flush 172.24.1.0/24"
                if cARPFailures == 0:
                    res = cli_no_output('ip', '-s', '-s', 'neigh', 'flush', self.ap.subnet+'.0/24')
                    # Give ARP system time to settle and re-register hardware
                    sleep(5)

                # now look at the hardware that has responded, if no entry
                # shows up on our access point after 3*10=30 seconds, the user
                # has disconnected
                bConnected = False
                res = cli_no_output('/usr/sbin/arp', '-n')
                out = str(res.get("stdout"))
                if out:
                    # Parse output, skipping header
                    for o in out.split("\n")[1:]:
                        if o[0:len(self.ap.subnet)] == self.ap.subnet:
                            if "(incomplete)" in o:
                                print "LOST: "+o
                            else:
                                bConnected = True
                if not bConnected:
                    cARPFailures += 1
                    if cARPFailures > 3:
                        self.connectionPrompt("Connection lost,")
                        bHasConnected = False
                else:
                    cARPFailures = 0
            sleep(5)  # wait a bit before continuing

        LOG.info("Exiting monitor thread...\n")
        self.threadConMon_stop.clear()

    def scan(self, event=None):
        LOG.info("Scanning wifi connections...")
        networks = {}
        status = self.get_status()

        for cell in Cell.all(self.iface):
            update = True
            ssid = cell.ssid
            quality = self.get_quality(cell.quality)

            if networks.__contains__(ssid):
                update = networks.get(ssid).get("quality") < quality
            if update and ssid:
                networks[ssid] = {
                    'quality': quality,
                    'encrypted': cell.encrypted,
                    'connected': self.is_connected(ssid, status)
                }
        self.client.emit(Message("mycroft.wifi.scanned",
                                 {'networks': networks}))
        LOG.info("Wifi connections scanned!\n%s" % networks)

    @staticmethod
    def get_quality(quality):
        values = quality.split("/")
        return float(values[0]) / float(values[1])

    def connect(self, event=None):
        if event and event.metadata:
            ssid = event.metadata.get("ssid")
            connected = self.is_connected(ssid)

            if connected:
                LOG.warn("Mycroft is already connected to %s" % ssid)
            else:
                self.disconnect()
                LOG.info("Connecting to: %s" % ssid)
                nid = wpa(self.iface, 'add_network')
                wpa(self.iface, 'set_network', nid, 'ssid', '"' + ssid + '"')

                if event.metadata.__contains__("pass"):
                    psk = '"' + event.metadata.get("pass") + '"'
                    wpa(self.iface, 'set_network', nid, 'psk', psk)
                else:
                    wpa(self.iface, 'set_network', nid, 'key_mgmt', 'NONE')

                wpa(self.iface, 'enable', nid)
                connected = self.get_connected(ssid)
                if connected:
                    wpa(self.iface, 'save_config')
                    ConfigurationManager.set(self.NAME, 'setup', False, True)

            self.client.emit(Message("mycroft.wifi.connected",
                                     {'connected': connected}))
            LOG.info("Connection status for %s = %s" % (ssid, connected))

    def disconnect(self):
        status = self.get_status()
        nid = status.get("id")
        if nid:
            ssid = status.get("ssid")
            wpa(self.iface, 'disable', nid)
            LOG.info("Disconnecting %s id: %s" % (ssid, nid))

    def get_status(self):
        res = cli('wpa_cli', '-i', self.iface, 'status')
        out = str(res.get("stdout"))
        if out:
            return dict(o.split("=") for o in out.split("\n")[:-1])
        return {}

    def get_connected(self, ssid, retry=5):
        connected = self.is_connected(ssid)
        while not connected and retry > 0:
            sleep(2)
            retry -= 1
            connected = self.is_connected(ssid)
        return connected

    def is_connected(self, ssid, status=None):
        status = status or self.get_status()
        state = status.get("wpa_state")
        return status.get("ssid") == ssid and state == "COMPLETED"

    def stop(self, event=None):
        LOG.info("Stopping access point...")
        self.threadConMon_stop.set()
        self.ap.down()
        if self.server:
            self.server.server.shutdown()
            self.server.server.server_close()
            self.server.join()
            self.server = None
        LOG.info("Access point stopped!")

    def run(self):
        try:
            self.client.run_forever()
        except Exception as e:
            LOG.error("Error: {0}".format(e))
            self.stop()


def main():
    wifi = WiFi()
    try:
        wifi.run()
    except Exception as e:
        print (e)
    finally:
        wifi.stop()
        sys.exit()


if __name__ == "__main__":
    main()
