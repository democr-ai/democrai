from typing import Any, Dict, Type, TypeVar, Optional, Callable, cast

T = TypeVar("T")


class Container:
    """
    A lightweight Dependency Injection Container.
    """

    def __init__(self):
        self._services: Dict[Type[T], Any] = {}
        self._factories: Dict[Type[T], Callable[[], T]] = {}

    def register(self, interface: Type[T], instance: T):
        """Register a singleton instance for an interface."""
        self._services[interface] = instance

    def register_factory(self, interface: Type[T], factory: Callable[[], T]):
        """Register a factory for an interface."""
        self._factories[interface] = cast(Any, factory)

    def resolve(self, interface: Type[T]) -> T:
        """Resolve an instance for the given interface."""
        if interface in self._services:
            return self._services[interface]
        if interface in self._factories:
            # For now, factories also behave like singletons (creation on first access could be cached if needed)
            # But simple factories return new instances usually.
            # Let's keep it simple: factory returns new instance.
            return self._factories[interface]()
        raise KeyError(f"Service {interface} not registered")

    def get(self, interface: Type[T]) -> Optional[T]:
        """Resolve an instance or return None if not found."""
        try:
            return self.resolve(interface)
        except KeyError:
            return None
