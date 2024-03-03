from packaging import version

__version__ = "5.0.0"


def version_major() -> int:
    """
    Returns:
        int: major version
    """
    return version.parse(__version__).major
