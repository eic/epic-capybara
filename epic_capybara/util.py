import os
from pathlib import Path
from itertools import chain, cycle, dropwhile, starmap, tee


def get_cache_dir():
    if "XDG_CACHE_HOME" in os.environ:
        return os.environ["XDG_CACHE_HOME"] / "epic-capybara"
    elif "HOME" in os.environ:
        return Path(os.environ["HOME"]) / ".cache" / "epic-capybara"
    elif "TMPDIR" in os.environ:
        return Path(os.environ["TMPDIR"]) / "epic-capybara"
    else:
        raise RuntimeError("Unable to fine a suitable cache location")


def integer_axis_range(x_min, x_max):
    """Returns the width of a histogram axis with one unit-width bin per integer value from x_min to x_max (inclusive).

    The width is computed with Python integers, so that it does not wrap around when the values span (nearly) the full range of a fixed-width integer type, e.g. a valid index of 0 next to an invalid-index sentinel of 0xFFFFFFFF.

    >>> integer_axis_range(0, 9)
    10
    >>> import numpy as np
    >>> integer_axis_range(np.uint32(0), np.uint32(0xFFFFFFFF))
    4294967296
    >>> integer_axis_range(np.int32(-2**31), np.int32(2**31 - 1))
    4294967296
    >>> integer_axis_range(np.uint64(0), np.uint64(2**64 - 1))
    18446744073709551616
    """
    return int(x_max) - int(x_min) + 1


def skip_common_prefix(iters: list):
    """Given a list of iterators, skips values until at least one iterator differs from the others. Returns the remaining iterators.

    >>> [list(iter) for iter in skip_common_prefix(["hello"])]
    [['h', 'e', 'l', 'l', 'o']]
    >>> [list(iter) for iter in skip_common_prefix(["hello", "world!"])]
    [['h', 'e', 'l', 'l', 'o'], ['w', 'o', 'r', 'l', 'd', '!']]
    >>> [list(iter) for iter in skip_common_prefix([[3, 2, 1], [1, 2, 3, 4]])]
    [[3, 2, 1], [1, 2, 3, 4]]
    >>> [list(iter) for iter in skip_common_prefix([[1, 2, 3], [1, 2, 3, 4]])]
    [[], [4]]
    """
    # ensure that we have iterators, so that we can chain unconsumed tail in the end
    iters = list(map(iter, iters))
    if len(iters) == 0:
        raise ValueError("iters must not be empty")
    elif len(iters) == 1:
        tuple_iters = [zip(*iters)]
    else:
        tuple_iters = tee(
            dropwhile(lambda vals: all(val == vals[0] for val in vals), zip(*iters)),
            len(iters),
        )
    return list(starmap(
        lambda ix, tuple_iter: chain(map(lambda t: t[ix], tuple_iter), iters[ix]),
        enumerate(tuple_iters)
    ))
