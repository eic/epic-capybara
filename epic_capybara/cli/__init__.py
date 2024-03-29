# SPDX-FileCopyrightText: 2023-present Dmitry Kalinkin <dmitry.kalinkin@gmail.com>
#
# SPDX-License-Identifier: MIT
import click

from ..__about__ import __version__
from .capy import capy
from .bara import bara
from .cate import cate

@click.group(context_settings={'help_option_names': ['-h', '--help']}, invoke_without_command=False)
@click.version_option(version=__version__, prog_name='capybara')
@click.pass_context
def capybara(ctx: click.Context):
    pass

capybara.add_command(capy)
capybara.add_command(bara)
capybara.add_command(cate)
