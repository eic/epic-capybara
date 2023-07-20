# SPDX-FileCopyrightText: 2023-present Dmitry Kalinkin <dmitry.kalinkin@gmail.com>
#
# SPDX-License-Identifier: MIT
import click

from .__about__ import __version__


@cli.command()
@click.argument('pr_number')
def fetchpr(pr_number):
    click.echo(f"fetch pr {pr_number}")


@click.group(context_settings={'help_option_names': ['-h', '--help']}, invoke_without_command=True)
@click.version_option(version=__version__, prog_name='capybara')
@click.pass_context
def capybara(ctx: click.Context):
    click.echo('Hello world!')
