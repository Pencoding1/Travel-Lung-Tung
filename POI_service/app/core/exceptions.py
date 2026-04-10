class DomainValidationException(Exception):
    def __init__(self, message="Domain Validation rules are violated."):
        self.message = message
        super().__init__(self.message)

class ResourceNotFoundException(Exception):
    def __init__(self, message="The manipulated resource is not found."):
        self.message = message
        super().__init__(self.message)
