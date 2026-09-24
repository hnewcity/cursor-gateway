"""Request errors shared by translation helpers without circular imports."""


class RequestError(Exception):
    def __init__(
        self, message: str, *, status: int = 400, param: str | None = None, code: str | None = None
    ) -> None:
        super().__init__(message)
        self.status, self.param, self.code = status, param, code
