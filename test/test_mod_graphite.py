#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Copyright (C) 2009-2010:
# Sébastien Coavoux, sebastien.coavoux@savoirfairelinux.com
# Philippe Pepos Petitclerc, philippe.pepos-petitclerc@savoirfairelinux.com
#
# This file is part of Shinken.
#
# Shinken is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Shinken is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with Shinken. If not, see <http://www.gnu.org/licenses/>.

import time
import socket
from socket import setdefaulttimeout
import select
import struct
import cPickle
import pytest
from shinken_test import *


# Default socket timeout duration
setdefaulttimeout(3.0)


class TestModGraphite(ShinkenTest):
    def do_load_modules(self):
        self.modules_manager.load_and_init()
        self.log.log("I correctly loaded the modules: [%s]" %
                     (','.join([inst.get_name() for inst in self.modules_manager.instances])))

    def setUp(self):
        self.setup_with_file('etc/shinken_1r_1h_1s.cfg')
        self.testid = str(os.getpid() + random.randint(1, 1000))

        modconf = Module({
            'module_name': 'Graphite-Perfdata',
            'module_type': 'graphite_perfdata',
            'port': '12345',
            'host': '127.0.0.1',
            'tick_limit': '300',
            'ignore_latency_limit': '10'
        })
        module = modulesctx.get_module('graphite')
        self.graphite_broker = module.get_instance(modconf)

        # Raise initial status broks
        self.sched.conf.skip_initial_broks = False
        self.sched.brokers['Default-Broker'] = {'broks': [], 'has_full_broks': False}
        self.sched.fill_initial_broks('Default-Broker')
        for b in self.sched.brokers['Default-Broker']['broks']:
            b.prepare()
            # print("Initial brok: %s / %s" % (b.type, b.data))
        self.update_broker()

        self.nagios_path = None
        self.livestatus_path = None
        self.nagios_config = None

        # add use_aggressive_host_checking so we can mix exit codes 1 and 2
        # but still get DOWN state
        host = self.sched.hosts.find_by_name("test_host_0")
        host.__class__.use_aggressive_host_checking = 1

        self.sock_serv = socket.socket()
        self.sock_serv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock_serv.bind(("127.0.0.1", 12345))
        self.sock_serv.listen(1)
        self.graphite_broker.init()
        self.conn_serv, _ = self.sock_serv.accept()

    def update_broker(self, dodeepcopy=False):
        """Overloads the Shinken update_broker method because it does not handle
        the broks list as a list but as a dict !"""
        for brok in self.sched.brokers['Default-Broker']['broks']:
            if dodeepcopy:
                brok = copy.deepcopy(brok)
            brok.prepare()
            # print("Managing a brok, type: %s" % brok.type)
            self.graphite_broker.manage_brok(brok)
        self.sched.brokers['Default-Broker']['broks'] = []

    def tearDown(self):
        if os.path.exists('var/shinken.log'):
            os.remove('var/shinken.log')
        if os.path.exists('var/retention.dat'):
            os.remove('var/retention.dat')
        if os.path.exists('var/status.dat'):
            os.remove('var/status.dat')
        self.conn_serv.close()
        self.sock_serv.close()

    def unpack_data(self, output):
        data = []
        while len(output) > 0:
            sizep = struct.unpack("!L", output[:4])[0]
            data.append(cPickle.loads(output[4:4+sizep]))
            output = output[4+sizep:]
        return data

    def test_big_chunks(self):
        self.print_header()

        host = self.sched.hosts.find_by_name("test_host_0")
        host.checks_in_progress = []
        host.act_depend_of = []  # ignore the router
        svc = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "test_ok_0")

        # To make tests quicker we make notifications send very quickly
        svc.notification_interval = 0.001

        svc.checks_in_progress = []
        svc.act_depend_of = []  # no hostchecks on critical checkresults

        # Get the Pending => UP lines
        self.scheduler_loop(1, [[host, 0, 'UP | rta=0.1']], do_sleep=True, sleep_time=0.1)
        self.scheduler_loop(1, [[svc, 0, 'OK | time=1s;3;4;5;6']], do_sleep=True, sleep_time=0.1)
        self.scheduler_loop(1, [[svc, 0, 'OK | val=1k;4;5;6;7']], do_sleep=True, sleep_time=0.1)
        self.update_broker()
        # todo: what is it?
        # self.graphite_broker.chunk_size = 1
        # todo: why?
        # self.graphite_broker.hook_tick("DUMMY")
        try:
            output = self.conn_serv.recv(8192)
        except socket.timeout:
            self.assertFalse
        # Unpack only for pickle
        # data = self.unpack_data(output)
        lines = output.split('\n')
        print("data: %s" % lines)
        # 2 items with metrics and 3 lf !
        self.assertTrue(len(lines) == 7)
        for data in lines:
            if not data:
                continue
            data = data.split(' ')
            print(data)
            assert data[0] in ['test_host_0.rta', 'test_host_0.test_ok_0.time', 'test_host_0.test_ok_0.val']
            # 0 is host.service.metric
            # 1 is value
            # 2 is timestamp
            self.assertTrue(len(data) == 3)

    def test_ignore_latency_limit(self):
        self.print_header()

        host = self.sched.hosts.find_by_name("test_host_0")
        host.checks_in_progress = []
        host.act_depend_of = []  # ignore the router
        svc = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "test_ok_0")

        # To make tests quicker we make notifications send very quickly
        svc.notification_interval = 0.001

        svc.checks_in_progress = []
        svc.act_depend_of = []  # no parent host checks on critical check results

        # Get the Pending => UP lines
        self.scheduler_loop(1, [[host, 0, 'UP']], do_sleep=True, sleep_time=0.1)
        self.scheduler_loop(1, [[svc, 0, 'OK | time=1s;3;4;5;6']], do_sleep=True, sleep_time=0.1)
        broks = [
            b for b in self.sched.brokers['Default-Broker']['broks'] if b.type == 'service_check_result'
        ]
        self.assertTrue(len(broks) == 1)
        broks[0].prepare()
        broks[0].data['latency'] = 5  # Hack to fake latency
        last = broks[0].data['last_chk']
        self.update_broker()
        # todo: why?
        # self.graphite_broker.hook_tick("DUMMY")
        try:
            output = self.conn_serv.recv(8192)
        except socket.timeout:
            self.assertFalse
        output = output.split('\n')
        lines = [l for l in output if l]
        print("data lines: %s" % lines)
        data = lines[0].split(' ')
        # 0 is host.service.metric
        # 1 is value
        # 2 is timestamp
        self.assertTrue(int(data[2]) == last - 5)

class TestModGraphiteConfiguration(ShinkenTest):
    def do_load_modules(self):
        self.modules_manager.load_and_init()
        self.log.log("I correctly loaded the modules: [%s]" %
                     (','.join([inst.get_name() for inst in self.modules_manager.instances])))

    def setUp(self):
        self.setup_with_file('etc/shinken_1r_1h_1s.cfg')
        self.testid = str(os.getpid() + random.randint(1, 1000))

        self.sched.conf.skip_initial_broks = False
        self.sched.brokers['Default-Broker'] = {'broks': [], 'has_full_broks': False}

        # modconf = Module({
        #     'module_name': 'Graphite-Perfdata',
        #     'module_type': 'graphite_perfdata',
        #     'port': '12345',
        #     'host': '127.0.0.1',
        #     'tick_limit': '300',
        #     'ignore_latency_limit': '10'
        # })
        # module = modulesctx.get_module('graphite')
        # self.graphite_broker = module.get_instance(modconf)
        #
        # # Raise initial status broks
        # self.sched.conf.skip_initial_broks = False
        # self.sched.brokers['Default-Broker'] = {'broks': [], 'has_full_broks': False}
        # self.sched.fill_initial_broks('Default-Broker')
        # for b in self.sched.brokers['Default-Broker']['broks']:
        #     b.prepare()
        #     # print("Initial brok: %s / %s" % (b.type, b.data))
        # self.update_broker()
        #
        self.nagios_path = None
        self.livestatus_path = None
        self.nagios_config = None

        # add use_aggressive_host_checking so we can mix exit codes 1 and 2
        # but still get DOWN state
        host = self.sched.hosts.find_by_name("test_host_0")
        host.__class__.use_aggressive_host_checking = 1

        self.sock_serv = None
        self.conn_serv = None

    def update_broker(self, dodeepcopy=False):
        """Overloads the Shinken update_broker method because it does not handle
        the broks list as a list but as a dict !"""
        for brok in self.sched.brokers['Default-Broker']['broks']:
            if dodeepcopy:
                brok = copy.deepcopy(brok)
            brok.prepare()
            # print("Managing a brok, type: %s" % brok.type)
            self.graphite_broker.manage_brok(brok)
        self.sched.brokers['Default-Broker']['broks'] = []

    def tearDown(self):
        if os.path.exists('var/shinken.log'):
            os.remove('var/shinken.log')
        if os.path.exists('var/retention.dat'):
            os.remove('var/retention.dat')
        if os.path.exists('var/status.dat'):
            os.remove('var/status.dat')
        if self.conn_serv:
            self.conn_serv.close()
        if self.sock_serv:
            self.sock_serv.close()

    def _configure_and_raise_metrics(self, mod_conf, initial=True, expected=1):
        # All default parameters
        modconf = Module(mod_conf)
        module = modulesctx.get_module('graphite')
        self.graphite_broker = module.get_instance(modconf)

        if self.sock_serv:
            self.sock_serv.close()
        self.sock_serv = socket.socket()
        self.sock_serv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock_serv.bind((mod_conf['host'], int(mod_conf['port'])))
        self.sock_serv.listen(1)

        self.graphite_broker.init()

        if self.conn_serv:
            self.conn_serv.close()
        self.conn_serv, _ = self.sock_serv.accept()

        host = self.sched.hosts.find_by_name("test_host_0")
        host.checks_in_progress = []
        host.act_depend_of = []  # ignore the router
        host.customs['_GRAPHITE_PRE'] = "host_pre"
        host.customs['_GRAPHITE_GROUP'] = "host_group"

        svc = self.sched.services.find_srv_by_name_and_hostname("test_host_0", "test_ok_0")
        svc.notification_interval = 0.001
        svc.checks_in_progress = []
        svc.act_depend_of = []
        svc.customs['_GRAPHITE_POST'] = "svc_post"

        if initial:
            # Raise initial status broks
            self.sched.conf.skip_initial_broks = False
            self.sched.brokers['Default-Broker'] = {'broks': [], 'has_full_broks': False}
            self.sched.fill_initial_broks('Default-Broker')
            for b in self.sched.brokers['Default-Broker']['broks']:
                b.prepare()
                # print("Initial brok: %s / %s" % (b.type, b.data))
            self.update_broker()

        # Raise some host/service check results
        self.scheduler_loop(1, [[host, 0, 'UP | rta=0.1']], do_sleep=True, sleep_time=0.1)
        self.scheduler_loop(1, [[svc, 0, 'OK | time=1s;3;4;5;6']], do_sleep=True, sleep_time=0.1)
        self.scheduler_loop(1, [[svc, 0, 'OK | val=1k;4;5;6;7']], do_sleep=True, sleep_time=0.1)
        self.update_broker()

        time.sleep(0.1)

        # Simulate the metrics reception by Graphite
        output = ''
        try:
            output = self.conn_serv.recv(8192)
        except socket.timeout:
            if not expected:
                return
            self.assertFalse

        output = output.split('\n')
        lines = [l for l in output if l]
        print("data lines: (%d lines) - %s\nexpecting %d lines" % (len(lines), lines, expected))
        self.assertTrue(len(lines) == expected)

        for data in lines:
            if not data:
                continue
            data = data.split(' ')
            print(data)
            # 0 is host.service.metric
            # 1 is value
            # 2 is timestamp
            self.assertTrue(len(data) == 3)

    def test_unknown(self):
        """Unknown host/service"""
        self.print_header()

        # All default parameters
        # No initial status broks - host and service will be unknown
        self._configure_and_raise_metrics({
            'module_name': 'Graphite-Perfdata',
            'module_type': 'graphite_perfdata',
            'host': '127.0.0.1',
            'port': '12345',
            'cache_max_length': 1000,
            'cache_commit_volume': 100,
            'graphite_data_source': 'shinken',
            'hostcheck': '__HOST__',
            'filter': [],
            'ignore_latency_limit': '15',
            'send_warning': False,
            'send_critical': False,
            'send_min': False,
            'send_max': False
        }, initial=False, expected=0)

    def test_configuration1(self):
        """Default configuration"""
        self.print_header()

        # All default parameters
        self._configure_and_raise_metrics({
            'module_name': 'Graphite-Perfdata',
            'module_type': 'graphite_perfdata',
            'port': '12345',
            'host': '127.0.0.1',
            'cache_max_length': 1000,
            'cache_commit_volume': 100,
            'graphite_data_source': 'shinken',
            'hostcheck': '__HOST__',
            'filter': '',
            'ignore_latency_limit': '15',
            'send_warning': False,
            'send_critical': False,
            'send_min': False,
            'send_max': False
        }, expected=3)

    def test_configuration2(self):
        """Send warning, critical, ..."""
        self.print_header()

        # All default parameters + send extra metrics
        self._configure_and_raise_metrics({
            'module_name': 'Graphite-Perfdata',
            'module_type': 'graphite_perfdata',
            'port': '12345',
            'host': '127.0.0.1',
            'cache_max_length': 1000,
            'cache_commit_volume': 100,
            'graphite_data_source': 'shinken',
            'hostcheck': '__HOST__',
            'filter': '',
            'ignore_latency_limit': '15',
            # Here!
            'send_warning': True,
            'send_critical': True,
            'send_min': True,
            'send_max': True
        }, expected=11)

        self.assertTrue(self.graphite_broker.send_warning)
        self.assertTrue(self.graphite_broker.send_critical)
        self.assertTrue(self.graphite_broker.send_min)
        self.assertTrue(self.graphite_broker.send_max)

    def test_configuration3(self):
        """Filter some services"""
        self.print_header()

        # All default parameters + filter
        self._configure_and_raise_metrics({
            'module_name': 'Graphite-Perfdata',
            'module_type': 'graphite_perfdata',
            'host': '127.0.0.1',
            'port': '12345',
            'cache_max_length': 1000,
            'cache_commit_volume': 100,
            'graphite_data_source': 'shinken',
            'hostcheck': '__HOST__',
            # Here!
            'filter': ['cpu:1m,5m', 'mem:3z', 'disk'],
            'ignore_latency_limit': '15',
            'send_warning': False,
            'send_critical': False,
            'send_min': False,
            'send_max': False
        }, expected=3)

        assert self.graphite_broker.filtered_metrics == {'cpu': ['1m', '5m'], 'mem': ['3z']}

    # @pytest.mark.skip("Not yet...")
    def test_cache(self):
        """Filter some services"""
        self.print_header()

        # All default parameters
        self._configure_and_raise_metrics({
            'module_name': 'Graphite-Perfdata',
            'module_type': 'graphite_perfdata',
            'port': '12345',
            'host': '127.0.0.1',
            'cache_max_length': 1000,
            'cache_commit_volume': 100,
            'graphite_data_source': 'shinken',
            'hostcheck': '__HOST__',
            'filter': '',
            'ignore_latency_limit': '15',
            'send_warning': False,
            'send_critical': False,
            'send_min': False,
            'send_max': False
        }, expected=3)

        # Sent packets: [
        # 'host_pre.host_group.test_host_0.__HOST__.shinken.rta 0.1 1578335088',
        # 'host_pre.host_group.test_host_0.shinken.test_ok_0.svc_post.time 1 1578335088',
        # 'host_pre.host_group.test_host_0.shinken.test_ok_0.svc_post.val 1 1578335088']
        # self.graphite_broker.cache = []
        # Simulate some packets in the cache
        self.graphite_broker.cache.append('host_pre.host_group.test_host_0.__HOST__.shinken.rta 0.1 1578335088\n')
        self.graphite_broker.cache.append('host_pre.host_group.test_host_0.shinken.test_ok_0.svc_post.time 1 1578335088\n')
        self.graphite_broker.cache.append('host_pre.host_group.test_host_0.shinken.test_ok_0.svc_post.val 1 1578335088\n')

        # Raise a new check results to provoke sending and cache management
        host = self.sched.hosts.find_by_name("test_host_0")
        host.checks_in_progress = []
        host.act_depend_of = []  # ignore the router
        self.scheduler_loop(1, [[host, 0, 'UP | rta=0.1']], do_sleep=True, sleep_time=0.1)
        self.update_broker()

        # Simulate the metrics reception by Graphite
        output = ''
        try:
            output = self.conn_serv.recv(8192)
        except socket.timeout:
            if not expected:
                return
            self.assertFalse

        output = output.split('\n')
        lines = [l for l in output if l]
        print("data lines: (%d lines) - %s\nexpecting %d lines" % (len(lines), lines, 4))
        self.assertTrue(len(lines) == 4)

