class IntentedNotImplementedException(Exception):
    def __init__(self, message="This method intentionally un-implemented, to use this method correctly, write a subclass and re-implement it"):
        self.message = message
        super().__init__(self.message)

