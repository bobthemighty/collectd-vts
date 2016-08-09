import collectd
import urllib2
import json
import pprint

from collections import namedtuple

nginx_conf = namedtuple('nginx_conf', ['uptime', 'connections'])
server_conf = namedtuple('server_conf', ['requests', 'responses'])


class NginxMonitor(object):

    def __init__(self):
        self.nginxcfg = nginx_conf(False, [])
        self.servers = dict()

    def configure(self, a):
        for child in a.children:
            if child.key == "nginx":
                self.handle_nginx_block(child)
            elif child.key == "stats_uri":
                self.stats_uri = child.values[0]
            elif child.key == "server":
                self.handle_server_block(child)

    def handle_nginx_block(self, nginx):
        uptime = False
        connections = []

        for k in nginx.children:
            if k.key == "uptime":
                uptime = k.values[0]
            elif k.key == "connections":
                connections = k.values
        self.nginxcfg = nginx_conf(uptime, connections)

    def handle_server_block(self, server):
        zones = []
        requests = False
        responses = []

        for k in server.children:
            if k.key == "zones":
                zones = k.values
            elif k.key == "requests":
                requests = k.values[0]
            elif k.key == "responses":
                responses = k.values

        for zone in zones:
            self.servers[zone] = server_conf(requests, responses)

    def init(self):
        pass

    def report_uptime(self, data):
        uptime_ms = data["nowMsec"] - data["loadMsec"]
        val = collectd.Values(plugin='nginx_server')
        val.type = 'gauge'
        val.type_instance = 'uptime_ms'
        val.plugin_instance = 'nginx@hostname'
        val.values = [uptime_ms]
        val.dispatch()

    def report_connections(self, data):
        conns = data["connections"]
        for gauge in ["active", "reading", "writing", "waiting"]:
            if gauge in self.nginxcfg.connections:
                collectd.Values(plugin='nginx',
                                type='gauge',
                                type_instance='connections_'+gauge,
                                values=[conns[gauge]]).dispatch()
        for ctr in ["accepted", "handled", "requests"]:
            if ctr in self.nginxcfg.connections:
                collectd.Values(plugin='nginx',
                                type='counter',
                                type_instance='connections_'+ctr,
                                values=[conns[ctr]]).dispatch()

    def report_stats(self, zone, cfg, data):
        if cfg.requests:
            collectd.Values(plugin='nginx_server',
                            type='counter',
                            type_instance='requests',
                            plugin_instance=zone,
                            values=[data["requestCounter"]]
                            ).dispatch()

        for res in cfg.responses:
            collectd.Values(plugin='nginx_server',
                            type='counter',
                            type_instance='response_'+str(res),
                            plugin_instance=zone,
                            values=[data["responses"][res]]
                            ).dispatch()

    def report_upstreams(self, data):
        for upstream in data["upstreamZones"]:

            zone = data["upstreamZones"][upstream]
	    for server in zone:
		    name = server["server"]
		    collectd.Values(plugin='nginx_upstream',
			            type='gauge',
				    type_instance='responseMs',
				    plugin_instance=name,
				    values=[server["responseMsec"]]
				    ).dispatch()		
	            for ctr in ["inBytes", "outBytes", "usedSize"]:
			collectd.info("foo")
			if ctr in server:
		                collectd.Values(plugin='nginx_upstream',
	                                type='counter',
	                                type_instance=ctr,
	                                plugin_instance=name,
	                                values=[server[ctr]]
	                                ).dispatch()
	
	            for res in server["responses"]:
			collectd.info("bar")
	                collectd.Values(plugin='nginx_upstream',
	                                type='counter',
	                                type_instance='response_'+res,
	                                plugin_instance=name,
	                                values=[server["responses"][res]]
	                                ).dispatch()
	
	            for flag in ["down", "backup"]:
			collectd.info("baz")
	                val = server[flag]
	                collectd.Values(plugin='nginx_upstream',
	                                type='gauge',
	                                type_instance=flag,
	                                plugin_instance=name,
	                                values=[1 if val else 0]
	                                ).dispatch()

    def read(self):
        response = urllib2.urlopen(self.stats_uri)
        data = json.load(response)
        for zone in self.servers:
            try:
                self.report_stats(
                    zone,
                    self.servers[zone],
                    data["serverZones"][zone])
            except KeyError:
                pass
        self.report_upstreams(data)
        if self.nginxcfg.uptime:
            self.report_uptime(data)
        self.report_connections(data)


monitor = NginxMonitor()

collectd.register_config(monitor.configure)
# collectd.register_init(monitor.init)
collectd.register_read(monitor.read)
