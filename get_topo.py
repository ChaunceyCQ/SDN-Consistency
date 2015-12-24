# Copyright (C) 2011 Nippon Telegraph and Telephone Corporation.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet

from ryu.topology import event
from ryu.topology.api import get_all_switch, get_all_link, get_switch, get_link
from ryu.lib import dpid as dpid_lib
from ryu.controller import dpset
import copy
from threading import Lock

UP = 1
DOWN = 0


class GetTopo(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(GetTopo, self).__init__(*args, **kwargs)
        # USed for learning switch functioning
        self.mac_to_port = {}
        # Holds the topology data and structure
        self.topo_shape = TopoStructure()

    # The state transition: HANDSHAKE -> CONFIG -> MAIN
    #
    # HANDSHAKE: if it receives HELLO message with the valid OFP version,
    # sends Features Request message, and moves to CONFIG.
    #
    # CONFIG: it receives Features Reply message and moves to MAIN
    #
    # MAIN: it does nothing. Applications are expected to register their
    # own handlers.
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        msg = ev.msg
        self.logger.info('OFPSwitchFeatures received: '
                         '\n\tdatapath_id=0x%016x n_buffers=%d '
                         '\n\tn_tables=%d auxiliary_id=%d '
                         '\n\tcapabilities=0x%08x',
                         msg.datapath_id, msg.n_buffers,msg.n_tables,
                         msg.auxiliary_id, msg.capabilities)
        
        #datapath_id=1
        datapath_id = msg.datapath_id
        #datapath=<ryu.controller.controller.Datapath object at 0x7faaba6a2050>
        datapath = ev.msg.datapath

        self.topo_shape.topo_switches[datapath_id]=[datapath]


    ###################################################################################
    """
    The event EventSwitchEnter will trigger the activation of get_topology_data().
    """
    @set_ev_cls(event.EventSwitchEnter)
    def handler_switch_enter(self, ev):
        self.topo_shape.topo_raw_switches = copy.copy(get_switch(self, None))
        self.topo_shape.topo_raw_links = copy.copy(get_link(self, None))

        self.topo_shape.print_links("EventSwitchEnter")
        self.topo_shape.print_switches("EventSwitchEnter")

        self.topo_shape.convert_raw_switch_to_list()
        print self.topo_shape.topo_switches
        self.topo_shape.convert_raw_links_to_list()
        #[((2, 3), (3, 2)), ((2, 2), (1, 2)), ((1, 2), (2, 2))]
        print self.topo_shape.topo_links

    @set_ev_cls(event.EventSwitchLeave, [MAIN_DISPATCHER, CONFIG_DISPATCHER, DEAD_DISPATCHER])
    def handler_switch_leave(self, ev):
        self.logger.info("Not tracking Switches, switch leaved.")

    """
    This function determines the links and switches currently in the topology
    """
    def get_topology_data(self):
        # Call get_switch() to get the list of objects Switch.
        self.topo_shape.topo_raw_switches = copy.copy(get_all_switch(self))

        # Call get_link() to get the list of objects Link.
        self.topo_shape.topo_raw_links = copy.copy(get_all_link(self))

        self.topo_shape.print_links("get_topology_data")
        self.topo_shape.print_switches("get_topology_data")

    ###################################################################################
    """
    EventOFPPortStatus: An event class for switch port status notification.
    The bellow handles the event.
    """
    @set_ev_cls(dpset.EventPortModify, MAIN_DISPATCHER)
    def port_modify_handler(self, ev):
        self.topo_shape.lock.acquire()
        dp = ev.dp
        port_attr = ev.port
        dp_str = dpid_lib.dpid_to_str(dp.id)
        self.logger.info("\t ***switch dpid=%s"
                         "\n \t port_no=%d hw_addr=%s name=%s config=0x%08x "
                         "\n \t state=0x%08x curr=0x%08x advertised=0x%08x "
                         "\n \t supported=0x%08x peer=0x%08x curr_speed=%d max_speed=%d" %
                         (dp_str, port_attr.port_no, port_attr.hw_addr,
                          port_attr.name, port_attr.config,
                          port_attr.state, port_attr.curr, port_attr.advertised,
                          port_attr.supported, port_attr.peer, port_attr.curr_speed,
                          port_attr.max_speed))
        if port_attr.state == 1:
            tmp_list = []
            removed_link = self.topo_shape.link_with_src_port(port_attr.port_no, dp.id)
            for i, link in enumerate(self.topo_shape.topo_raw_links):
                if link.src.dpid == dp.id and link.src.port_no == port_attr.port_no:
                    print "\t Removing link " + str(link) + " with index " + str(i)
                    #del self.topo_shape.topo_raw_links[i]
                elif link.dst.dpid == dp.id and link.dst.port_no == port_attr.port_no:
                    print "\t Removing link " + str(link) + " with index " + str(i)
                    #del self.topo_shape.topo_raw_links[i]
                else:
                    tmp_list.append(link)

            self.topo_shape.topo_raw_links = copy.copy(tmp_list)
            #self.topo_shape.print_links("Link Down")
            
            print "link Down"
            self.topo_shape.convert_raw_switch_to_list()
            print self.topo_shape.topo_switches
            self.topo_shape.convert_raw_links_to_list()
            #[((2, 3), (3, 2)), ((2, 2), (1, 2)), ((1, 2), (2, 2))]
            print self.topo_shape.topo_links

        #     print "\t Considering the removed Link " + str(removed_link)
        #     if removed_link is not None:
        #         shortest_path_hubs, shortest_path_node = self.topo_shape.find_shortest_path(removed_link.src.dpid)
        #         print("\t\tNew shortest_path_hubs: {0}\n\t\tNew shortest_path_node: {1}".format(shortest_path_hubs, shortest_path_node))
        elif port_attr.state == 0:
            self.topo_shape.topo_raw_links = copy.copy(get_link(self,None))
            #self.topo_shape.print_links("Link Up")
            
            print "Link Up"
            self.topo_shape.convert_raw_switch_to_list()
            print self.topo_shape.topo_switches
            self.topo_shape.convert_raw_links_to_list()
            #[((2, 3), (3, 2)), ((2, 2), (1, 2)), ((1, 2), (2, 2))]
            print self.topo_shape.topo_links

        self.topo_shape.lock.release()

        ###################################################################################
        ###################################################################################


"""
This class holds the list of links and switches in the topology and it provides some useful functions
"""
class TopoStructure():
    def __init__(self, *args, **kwargs):
        self.topo_raw_switches = []
        self.topo_raw_links = []
        self.topo_switches={}
        self.topo_links = []
        self.lock = Lock()

    def print_links(self, func_str=None):
        # Convert the raw link to list so that it is printed easily
        print(" \t" + str(func_str) + ": Current Links:")
        for l in self.topo_raw_links:
            print (" \t\t" + str(l))

    def print_switches(self, func_str=None):
        print(" \t" + str(func_str) + ": Current Switches:")
        for s in self.topo_raw_switches:
            print (" \t\t" + str(s))

    def switches_count(self):
        return len(self.topo_raw_switches)

    def convert_raw_links_to_list(self):
        # Build a  list with all the links [((srcNode,port), (dstNode, port))].
        # The list is easier for printing.
        self.topo_links = [((link.src.dpid, link.src.port_no),
                            (link.dst.dpid, link.dst.port_no))
                           for link in self.topo_raw_links]

    def convert_raw_switch_to_list(self):
        # Build a list with all the switches ([switches])
        #self.topo_switches = [(switch.dp.id, UP) for switch in self.topo_raw_switches]
        for switch in self.topo_raw_switches:
            # print switch.dp.id
            # print self.topo_switches[switch.dp.id]
            if len(self.topo_switches[switch.dp.id]) == 1:
                self.topo_switches[switch.dp.id].append(UP)

    """
    Adds the link to list of raw links
    """
    def bring_up_link(self, link):
        self.topo_raw_links.append(link)

    """
    Check if a link with specific nodes exists.
    """
    def check_link(self, sdpid, sport, ddpid, dport):
        for i, link in self.topo_raw_links:
            if ((sdpid, sport), (ddpid, dport)) == (
                    (link.src.dpid, link.src.port_no), (link.dst.dpid, link.dst.port_no)):
                return True
        return False

    """
    Find a path between src and dst based on the shorted path info which is stored on shortest_path_node
    """
    def find_path_from_topo(self,src_dpid, dst_dpid, shortest_path_node):
        path = []
        now_node = dst_dpid
        last_node = None
        while now_node != src_dpid:
            last_node = shortest_path_node.pop(now_node, None)
            if last_node != None:
                l = self.link_from_src_to_dst(now_node, last_node)
                if l is None:
                    print("Link between {0} and {1} was not found in topo.".format(now_node, last_node))
                else:
                    path.append(l)
                    now_node = last_node
            else:
                print "Path could not be found"
        return path
    """
    Finds the dpids of destinations where the links' source is s_dpid
    """
    def find_dst_with_src(self, s_dpid):
        d = []
        for l in self.topo_raw_links:
            if l.src.dpid == s_dpid:
                d.append(l.dst.dpid)
        return d

    """
    Finds the list of link objects where links' src dpid is s_dpid
    """
    def find_links_with_src(self, s_dpid):
        d_links = []
        for l in self.topo_raw_links:
            if l.src.dpid == s_dpid:
                d_links.append(l)
        return d_links

    """
    Returns a link object that has in_dpid and in_port as either source or destination dpid and port.
    """
    def link_with_src_dst_port(self, in_port, in_dpid):
        for l in self.topo_raw_links:
            if (l.src.dpid == in_dpid and l.src.port_no == in_port) or (
                            l.dst.dpid == in_dpid and l.src.port_no == in_port):
                return l
        return None
    """
    Returns a link object from src with dpid s to dest with dpid d.
    """
    def link_from_src_to_dst(self, s, d):
        for l in self.topo_raw_links:
            if l.src.dpid == s and l.dst.dpid == d:
                return l
        return None
    """
    Returns a link object that has in_dpid and in_port as either source dpid and port.
    """
    def link_with_src_port(self, in_port, in_dpid):
        for l in self.topo_raw_links:
            if (l.src.dpid == in_dpid and l.src.port_no == in_port) or (l.dst.dpid == in_dpid and l.src.port_no == in_port):
                return l
        return None

    ########## Functions related to Spanning Tree Algorithm ##########
    def find_root_switch(self):
        pass
