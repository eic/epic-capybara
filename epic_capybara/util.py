from itertools import chain, cycle, dropwhile, starmap, tee


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
