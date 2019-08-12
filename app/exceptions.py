class NetworkNameAlreadyExists(Exception):
    def __init__(self, message):
        self.message = message
    #def __str__(self):
        #return repr(self.message)

class ClassInSession(Exception):
    def __init__(self, start_time, end_time, message):
        self.start_time = start_time
        self.end_time = end_time
        self.message = "There is a class currently in session from %s to %s. You will be able to login after the class has ended." % (self.start_time, self.end_time)
