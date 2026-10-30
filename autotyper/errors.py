"""Errors shared by all input backends."""


class InputBackendError(RuntimeError):
    """The platform input backend cannot start or cannot send input."""
