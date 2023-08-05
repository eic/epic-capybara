import click
import requests
from github import Auth, Github, GithubException

from ..github import download_artifact

@click.command()
@click.option('--token', default=None, help="GitHub access token (defaults to GITHUB_TOKEN environment variable)")
@click.option('--owner', default="eic", help="Owner of the target repository")
@click.option('--repo', default="EICrecon", help="Name of the target repository")
@click.option('--artifact-name', default="rec_dis_18x275_minQ2=1000_brycecanyon.edm4eic.root")
@click.argument('pr_number', type=int)
@click.pass_context
def capy(ctx: click.Context, artifact_name: str, owner: str, pr_number: int, repo: str, token: str):
    if token is None:
        import os
        if "GITHUB_TOKEN" in os.environ:
            token = os.environ["GITHUB_TOKEN"]
        else:
            click.secho(f"Need to provide a --token parameter or set GITHUB_TOKEN environment variable", fg='red', err=True)
            ctx.exit(1)
    gh = Github(auth=Auth.Token(token))
    repo = gh.get_user(owner).get_repo(repo)

    click.secho(f'Fetching metadata for #{pr_number}...', fg='green', err=True)
    try:
        pr = repo.get_pull(pr_number)
    except GithubException as e:
        click.secho("Pull Request is not accessible", fg="red", err=True)
        click.secho(e)
        ctx.exit(1)
    click.echo(f"Title: {pr.title}", err=True)
    click.echo(f"PR head: {click.style(pr.head.ref, bold=True)}@{pr.head.sha}, targets {click.style(pr.base.ref, bold=True)}@{pr.base.sha}", err=True)

    workflow_head = None
    workflow_base = None
    messages = []

    with click.progressbar(
            repo.get_workflow_runs(),
            label="Loading workflows",
            item_show_func=lambda workflow: str(workflow.id) if hasattr(workflow, "id") else None,
    ) as workflows_bar:
        for workflow in workflows_bar:
            # workflow.head_commit.sha is not available, so we take the latest
            # TODO check if PR is the latest by parsing log files?
            if workflow.head_branch == pr.head.ref and workflow_head is None:
                if workflow.get_artifacts().totalCount == 0:
                    messages.append(dict(message=f"Skipping workflow {workflow.html_url} on {workflow.head_branch} with no artifacts", fg="red", err=True))
                    continue
                workflow_head = workflow
            if workflow.head_branch == pr.base.ref and workflow_base is None:
                if workflow.get_artifacts().totalCount == 0:
                    messages.append(dict(message=f"Skipping workflow {workflow.html_url} on {workflow.head_branch} with no artifacts", fg="red", err=True))
                    continue
                workflow_base = workflow
            if workflow_head is not None and workflow_base is not None:
                break

    for message in messages:
        click.secho(**message)

    click.echo(f"PR base workflow: {workflow_base.html_url}")
    click.echo(f"PR head workflow: {workflow_head.html_url}")

    click.echo(download_artifact(workflow_base, artifact_name, token=token, click=click))
    click.echo(download_artifact(workflow_head, artifact_name, token=token, click=click))
