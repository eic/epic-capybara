# SPDX-FileCopyrightText: 2023-present Dmitry Kalinkin <dmitry.kalinkin@gmail.com>
#
# SPDX-License-Identifier: MIT
import sys

if __name__ == '__main__':
    from .cli import capybara

    sys.exit(capybara())
