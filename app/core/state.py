class RuntimeState:
    def __init__(self):
        self.shapes = {}
        self.stop_times = {}
        self.stops = {}
        self.routes = {}
        self.trips = {}
        self.route_shapes = {}
        self.subtrechos = []
        self.subtrecho_index = {}
        self.subtrecho_times_by_shape = {}
        self.vehicles = {}


# instância global
rt = RuntimeState()
