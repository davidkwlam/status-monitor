from __future__ import with_statement
import socket
import random
import threading
import datetime
import time
import SimpleHTTPServer
import SocketServer
import os
import pickle
import Queue
import logging

udp_port = 5000 # status update listening port for nodes in the "nodes" list
tcp_port = 8000 # status monitor page is hosted on http://<MY_ADDRESS>:8000
status_interval = 180.0 # number of seconds in between sending updates
max_in_threads = 20
max_out_threads = 40
max_nodes_forward = 8 # max number of nodes to forward a status
home_dir = "."
logging.basicConfig(filename="%s/status_monitor.log" % home_dir,level=logging.DEBUG,format='%(asctime)s %(message)s',datefmt='%m/%d/%Y %I:%M:%S %p')

queue_in = Queue.Queue()
queue_out = Queue.Queue(maxsize=max_out_threads*2)
node_port = {}
node_status = {}
node_updated = {}

with open("%s/nodes" % home_dir, "r") as f:
    for line in f:
        node = line.strip()
        node_port[node] = udp_port
        node_updated[node] = int(time.time())

num_forward = min(max_nodes_forward, len(node_port) - 1) # number of hosts to forward statuses

class Status:
    def __init__(self):
        self.node = socket.gethostname()
        self.port = int(udp_port)
        self.timestamp = int(time.time())
        self.diskspaceused = os.popen("df -Ph . | tail -1 | awk '{print $3}'").read().strip()
        self.diskspaceavail = os.popen("df -Ph . | tail -1 | awk '{print $4}'").read().strip()
        self.uptime = os.popen("uptime | awk -F, '{sub(\".*up \",x,$1);print $1}'").read().strip()
        self.load_averages = os.popen("uptime | awk '{print $(NF-2)\" \"$(NF-1)\" \"$(NF-0)}'").read()
        self.queue_in = queue_in.qsize()
        self.queue_out = queue_out.qsize()

class StatusMonitorRequestHandler(SimpleHTTPServer.SimpleHTTPRequestHandler): # a handler that regenerates index.html before serving
    def do_GET(self):
        os.chdir(home_dir)
        with open("%s/index.html" % home_dir, "w") as f:
            f.write("<html><body><table border=\"1\">")
            f.write("<p>Status Monitor at <b>%s</b> (Local Time: %s)</p>" % (socket.gethostname(), datetime.datetime.strptime(time.ctime(time.time()), "%a %b %d %H:%M:%S %Y")))
            f.write("<tr><td></td>")
            f.write("<td><b>Node</b></td>")
            f.write("<td><b>Updated</b></td>")
            f.write("<td><b>Uptime</b></td>")
            f.write("<td><b>Disk Space<br>Used</b></td>")
            f.write("<td><b>Disk Space<br>Available</b></td>")
            f.write("<td><b>Average Load<br>(1m, 5m, 10m)</td>")
            f.write("<td><b>Queue<br>(In/Out)</td>")
            f.write("</tr>")
            index = 1
            rev_domains = self.reversed_domains(node_status.keys())
            for key in sorted(rev_domains):
                node = rev_domains[key]
                f.write("<tr>")
                f.write("<td><b>%s</b></td>" % index)
                f.write("<td bgcolor=\"#%s\"><a href=\"http://%s:8000\">%s</a></td>" % (self.hex_color(node_updated[node]), node, node))
                f.write("<td>%s</td>" % datetime.datetime.strptime(time.ctime(node_updated[node]), "%a %b %d %H:%M:%S %Y"))
                try:
                    f.write("<td>%s</td>" % node_status[node].uptime)
                    f.write("<td>%s</td>" % node_status[node].diskspaceused)
                    f.write("<td>%s</td>" % node_status[node].diskspaceavail)
                    f.write("<td>%s</td>" % node_status[node].load_averages)
                    f.write("<td>%s/%s</td>" % (node_status[node].queue_in,node_status[node].queue_out))
                except Exception, e:
                    logging.error("Error printing %s %s" % (node, node_status[node].timestamp))
                    logging.error(str(e))
                f.write("</tr>")
                index += 1
            f.write("</table></body></html>")
        return SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET(self)

    def hex_color(self, time_of_last_update):
        time_since_last_update = int(time.time()) - time_of_last_update
        if time_since_last_update > status_interval * 4:
            return "ff0000"
        elif time_since_last_update > status_interval * 2:
            return "ffff00"
        return "00ff00"

    def reversed_domains(self, nodes):
        result = {}
        for node in nodes:
            segments = node.split(".")
            segments.reverse()
            result[".".join(segments)] = node
        return result

def run_webserver():
    SocketServer.TCPServer.allow_reuse_address = True
    SocketServer.TCPServer(("", tcp_port), StatusMonitorRequestHandler).serve_forever()

def random_available_nodes():
    nodes = filter(lambda x: x != socket.gethostname() and int(time.time()) - node_updated[x] < status_interval * 2, list(node_port.keys()))
    return random.sample(nodes, min(num_forward, len(nodes)))

def send_udp(data, nodes):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("", 0))
        for node in nodes:
            sock.sendto(data, (node, node_port[node]))
    except Exception, e:
        logging.error("Error sending udp to %s %s" % (node, node_port[node]))
        logging.error(str(e))
    finally:
        sock.close()

def send_my_status():
    threading.Timer(status_interval, send_my_status).start()
    nodes = random_available_nodes()
    if len(nodes) == 0: # send status to all known nodes if not getting updates
        nodes = nodes.keys()
        random.shuffle(nodes)
    send_udp(pickle.dumps(Status()), nodes)

def send():
    while True:
        data = queue_out.get()
        send_udp(data, random_available_nodes())
        queue_out.task_done()

def previously_received(status):
    return status.node in node_status and status.timestamp <= node_status[status.node].timestamp

def process():
    while True:
        data = queue_in.get(block=True)
        try:
            status = pickle.loads(data)
            if isinstance(status, Status) and not previously_received(status):
                node_port[status.node] = status.port # in case a node starts listening on a new port
                node_status[status.node] = status
                node_updated[status.node] = int(time.time())
                if not queue_out.full():
                    queue_out.put(data)
        except Exception, e:
            logging.error("Error processing %s" % data)
            logging.error(str(e))
        queue_in.task_done()

def listen():
    global udp_port
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("", udp_port if socket.gethostname() in node_port else 0))
    udp_port = sock.getsockname()[1]
    logging.debug("Listening on port %s" % udp_port)

    while True:
        data, addr = sock.recvfrom(1024)
        queue_in.put(data)

    sock.close()

def start_threads():
    t_webserver = threading.Thread(target=run_webserver)
    t_webserver.daemon = True
    t_webserver.start()
    for i in range(max_in_threads):
        t_process = threading.Thread(target=process)
        t_process.daemon = True
        t_process.start()
    for i in range(max_out_threads):
        t_send = threading.Thread(target=send)
        t_send.daemon = True
        t_send.start()

start_threads()
send_my_status()
listen()
