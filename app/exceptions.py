class NetworkNameAlreadyExists(Exception):
    def __init__(self, message, network_name):
        self.network_name = network_name
        self.message = 'ERROR: A network named "%s" already exists. Please use another name.' % self.network_name

class ClassInSession(Exception):
    def __init__(self, start_time, end_time, message):
        self.start_time = start_time
        self.end_time = end_time
        self.message = "There is a class currently in session from %s to %s. You will be able to login after the class has ended." % (self.start_time, self.end_time)
