from collections.abc import Callable

from app.providers.schemas import ProviderRequest, ProviderResponse


ProviderHandler = Callable[[ProviderRequest], ProviderResponse]


class ProviderRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, ProviderHandler] = {}

    def register(self, name: str, handler: ProviderHandler) -> None:
        if name in self._handlers:
            raise ValueError(f"provider already registered: {name}")
        self._handlers[name] = handler

    def invoke(self, name: str, request: ProviderRequest) -> ProviderResponse:
        handler = self._handlers.get(name)
        if handler is None:
            raise KeyError(f"provider not registered: {name}")
        response = handler(request)
        if response.provider_name != name:
            raise ValueError(
                f"provider response name mismatch: expected {name}, got {response.provider_name}"
            )
        if response.provider_mode != request.provider_mode:
            raise ValueError(
                "provider response mode mismatch: "
                f"expected {request.provider_mode}, got {response.provider_mode}"
            )
        return response

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._handlers))
