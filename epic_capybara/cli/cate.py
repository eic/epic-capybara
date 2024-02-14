from pathlib import Path

import click
from github import Auth, Github, GithubException

from ..filesystem import hashdir


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
        try:
            repo = user.get_repo(repo)
        except GithubException:
            click.secho(f"Repository {owner}/{repo} is not available.", fg="red", err=True)
            repo = user.create_repo(repo)
    else:
        user = gh.get_user()
        try:
            repo = user.get_repo(repo)
        except GithubException:
            click.secho(f"Repository {user.login}/{repo} is not available. Attempting to create...", fg="yellow", err=True)
            repo = user.create_repo(repo)

    report_dir = Path(report_dir)

    prefix = hashdir(report_dir)

    def recurse_upload(cur_path):
        paths = cur_path.iterdir()
        for file_ in sorted([p for p in paths if p.is_file()]):
            relpath = file_.relative_to(report_dir)
            with open(file_, "rb") as fp:
                contents = fp.read()
            target_path = f"{prefix}/{relpath}"
            click.secho(f"Uploading {target_path}", fg="green", err=True)
            repo.create_file(
                target_path,
                f"Adding {target_path}", # commit message
                contents.decode(),
                branch="gh-pages",
            )

        paths = cur_path.iterdir()
        for dir_ in sorted([p for p in paths if p.is_dir()]):
            recurse_upload(dir_)

    recurse_upload(report_dir)

    try:
        file = repo.get_contents(".nojekyll")
    except github.GithubException.UnknownObjectException:
        # file does not exist
        repo.create_file(
            ".nojekyll",
            f"Adding .nojekyll", # commit message
            "",
            branch="gh-pages",
        )

    click.echo(f"https://{user.login}.github.io/{repo.name}/{prefix}/")
