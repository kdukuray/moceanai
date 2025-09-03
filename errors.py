class AppError(Exception):
    """Base class for exceptions in this app."""

class MissingDataError(AppError):
    """Exception raised when data required for a process is missing"""
    def __init__(self, message, missing_field: str = ""):
        super().__init__(message)
        self.missing_field = missing_field

class FailedGenerationError(AppError):
    """Exception raised when the generation of data fails"""
    def __init__(self, message):
        super().__init__(message)


class FailedParsingError(AppError):
    """Exception raised when parsing data fails"""
    def __init__(self, message):
        super().__init__(message)