# SPDX-FileCopyrightText: 2023-present Dmitry Kalinkin <dmitry.kalinkin@gmail.com>
#
# SPDX-License-Identifier: MIT
import click
from github import Auth, Github, GithubException


@click.command()
@click.option('--token', envvar="GITHUB_TOKEN", required=True, help="GitHub access token (defaults to GITHUB_TOKEN environment variable)")
@click.option('--owner', required=True, help="Owner of the GitHub repository")
@click.option('--repo', required=True, help="Name of the GitHub repository")
@click.option('--pr', 'pr_number', type=int, required=True, help="Pull request number")
@click.option('--url', required=True, help="Dashboard URL to link in the comment")
@click.option('--title', default="Benchmark Comparison", help="Section title for the comment")
@click.pass_context
def comment(ctx: click.Context, token: str, owner: str, repo: str, pr_number: int, url: str, title: str):
    """Post a GitHub PR comment with a benchmark dashboard link."""
    gh = Github(auth=Auth.Token(token))

    try:
        repository = gh.get_user(owner).get_repo(repo)
    except GithubException as e:
        click.secho(f"Repository {owner}/{repo} is not accessible", fg="red", err=True)
        click.secho(str(e), err=True)
        ctx.exit(1)

    try:
        pull = repository.get_pull(pr_number)
    except GithubException as e:
        click.secho(f"Pull request #{pr_number} is not accessible", fg="red", err=True)
        click.secho(str(e), err=True)
        ctx.exit(1)

    body = f"## {title}\n\n[View interactive Bokeh dashboard]({url})\n"
    pull.create_issue_comment(body)
    click.echo(f"Posted comment to {owner}/{repo}#{pr_number}")
