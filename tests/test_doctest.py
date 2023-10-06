import doctest

import epic_capybara.util

def test_docstrings():
    doctest_results = doctest.testmod(m=epic_capybara.util)
    assert doctest_results.failed == 0
