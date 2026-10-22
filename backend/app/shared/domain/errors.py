class ApplicationError(Exception):
    code = "invalid_operation"


class NotFound(ApplicationError):
    code = "not_found"


class Forbidden(ApplicationError):
    code = "forbidden"


class Unauthorized(ApplicationError):
    code = "unauthorized"


class Conflict(ApplicationError):
    code = "conflict"


class Unavailable(ApplicationError):
    code = "unavailable"


class InvalidInput(ApplicationError):
    code = "invalid_input"


class TooLarge(ApplicationError):
    code = "too_large"
