# SDN-Consistency
在simple_switch_13中有    
_CONTEXTS = {
    "GetTopo": get_topo_3_2.GetTopo,
}

def __init__(self, *args, **kwargs):
    super(SimpleSwitch13, self).__init__(*args, **kwargs)
    self.mac_to_port = {}
    self.gettopo=kwargs["GetTopo"]
能够得到get_topo_3_2中得到的网络拓扑数据
