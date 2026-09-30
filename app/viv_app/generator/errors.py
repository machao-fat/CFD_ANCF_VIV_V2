class GenerationError(ValueError):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


def blocked(detail: str):
    raise GenerationError("GENERATION_BLOCKED_BY_UNKNOWN_CONTRACT", detail)
