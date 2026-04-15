# SPDX-FileCopyrightText: 2023-present Dmitry Kalinkin <dmitry.kalinkin@gmail.com>
#
# SPDX-License-Identifier: MIT
import subprocess
from pathlib import Path

import click


@click.command()
@click.option('--scope', default='epic', show_default=True, help="Rucio scope")
@click.option('--rucio-account', envvar='RUCIO_ACCOUNT', default='eicprod', show_default=True, help="Rucio account name (defaults to RUCIO_ACCOUNT environment variable)")
@click.option('--output-dir', default='.', show_default=True, type=click.Path(file_okay=False), help="Local directory to download files into")
@click.argument('did')
@click.pass_context
def rucio(ctx: click.Context, scope: str, rucio_account: str, output_dir: str, did: str):
    """Download ROOT files from Rucio by scope:DID.

    DID may be a fully qualified name (scope:name) or a bare name; if bare,
    the --scope option is prepended.  The special name component ``latest``
    is resolved by Rucio transparently when the DID refers to a dataset.

    Examples:

    \b
      # Download the latest master baseline for physics benchmarks
      capy rucio epic:benchmarks/physics_benchmarks/baseline/master/latest

    \b
      # Download a specific PR run
      capy rucio benchmarks/physics_benchmarks/pr/42/abc123def456
    """
    if ':' in did:
        full_did = did
    else:
        full_did = f"{scope}:{did}"

    click.secho(f"Downloading {full_did} → {output_dir}", fg='green', err=True)

    try:
        subprocess.check_call(
            ["rucio", "download", full_did, "--dir", output_dir],
            env={**__import__('os').environ, "RUCIO_ACCOUNT": rucio_account},
        )
    except subprocess.CalledProcessError as e:
        click.secho(f"rucio download failed with exit code {e.returncode}", fg="red", err=True)
        ctx.exit(e.returncode)

    # Print the local directory where files landed so callers can capture it
    did_path = full_did.split(':', 1)[1].lstrip('/')
    local_path = Path(output_dir) / did_path
    click.echo(str(local_path))
