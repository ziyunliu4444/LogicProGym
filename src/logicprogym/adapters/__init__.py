"""Adapter exports; defer loading device libraries until an adapter is requested."""

from importlib import import_module

from logicprogym.adapters.base import AdapterCapabilities, LogicProAdapter


def __getattr__(name):
    """Preserve public imports without eagerly loading device libraries."""
    if name in {'LogicAdapter', 'LogicMidiAdapter', 'LogicMidiRoute'}:
        module = 'logic'
    elif name == 'LogicHybridAdapter':
        module = 'logic_hybrid'
    elif name in __all__ and name not in {'AdapterCapabilities', 'LogicProAdapter'}:
        module = 'logic_mackie'
    else:
        raise AttributeError(f'module {__name__!r} has no attribute {name!r}')
    value = getattr(import_module(f'{__name__}.{module}'), name)
    globals()[name] = value
    return value

__all__ = [
    "AdapterCapabilities",
    "LogicProAdapter",
    "LogicAdapter",
    "LogicHybridAdapter",
    "LogicMidiAdapter",
    "LogicMidiRoute",
    "LogicMackieBridge",
    "LogicMackieAdapter",
    "LogicMackieProfile",
    "LogicMackieService",
    "LogicMackieTrack",
    "MackieControllerPool",
    "MackieParameterAddress",
    "MackieRelativeAction",
]
