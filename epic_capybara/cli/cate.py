import shutil
import subprocess
from github import Auth, Github, GithubException
from pathlib import Path

import click
from urllib.parse import urlparse

from ..filesystem import hashdir
from ..util import get_cache_dir


@click.command()
@click.option('--token', envvar="GITHUB_TOKEN", required=True, help="GitHub access token (defaults to GITHUB_TOKEN environment variable)")
@click.option('--owner', help="Owner of the target repository (token owner by default)")
@click.option('--repo', default="capybara-reports", help="Name of the target repository")
@click.argument('report-dir', type=click.Path(exists=True, file_okay=False, dir_okay=True))
@click.pass_context
def cate(ctx: click.Context, owner: str, repo: str, report_dir: str, token: str):
    gh = Github(auth=Auth.Token(token))

    if owner is not None:
        user = gh.get_user(owner)
    else:
        user = gh.get_user()

    try:
        repo = user.get_repo(repo)
    except GithubException:
        click.secho(f"Repository {user.login}/{repo.name} is not available. Attempting to create...", fg="yellow", err=True)
        repo = user.create_repo(repo)

    report_dir = Path(report_dir)

    prefix = hashdir(report_dir)

    clone_url = urlparse(repo.clone_url)
    # Add authentication information
    clone_url = clone_url._replace(
        netloc=f"{user.login}:{token}@{clone_url.netloc}",
    )
    local_repo = get_cache_dir() / user.login / repo.name

    if not local_repo.exists():
        subprocess.check_output(["git", "clone", clone_url.geturl(), str(local_repo)])
    else:
        subprocess.check_output(["git", "-C", str(local_repo), "pull"])
    shutil.copytree(report_dir, local_repo / prefix)
    subprocess.check_output(["git", "-C", str(local_repo), "add", prefix])
    subprocess.check_output(["git", "-C", str(local_repo), "commit", "-m", f"Adding {prefix}/"])
    subprocess.check_output(["git", "-C", str(local_repo), "push"])

    try:
        file = repo.get_contents(".nojekyll")
    except GithubException.UnknownObjectException:
        # file does not exist
        repo.create_file(
            ".nojekyll",
            f"Adding .nojekyll", # commit message
            "",
            branch="gh-pages",
        )

    click.echo(f"https://{user.login}.github.io/{repo.name}/{prefix}/")
