_history_provider = None


def set_history_provider(fn):
    """Register a callback that returns conversation summary text."""
    global _history_provider
    _history_provider = fn


def get_history_provider():
    """Retrieve the conversation summary callback."""
    return _history_provider
