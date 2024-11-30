import click
from github import Auth, Github, GithubException

from ..github import download_artifact


@click.command()
@click.option('--artifact-name', default="rec_dis_18x275_minQ2=1000_craterlake_18x275.edm4eic.root")
@click.option('--token', envvar="GITHUB_TOKEN", required=True, help="GitHub access token (defaults to GITHUB_TOKEN environment variable)")
@click.option('--owner', default="eic", help="Owner of the target repository")
@click.option('--repo', default="EICrecon", help="Name of the target repository")
@click.argument('pr_number', type=int)
@click.pass_context
def pr(ctx: click.Context, artifact_name: str, owner: str, pr_number: int, repo: str, token: str):
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
    other_repo_message = ""
    if pr.head.repo != repo:
       other_repo_message = click.style(f"{pr.head.repo.owner.login}/{pr.head.repo.name}", italic=True) + "/"
    click.echo(f"PR head: {other_repo_message}{click.style(pr.head.ref, bold=True)}@{pr.head.sha}, targets {click.style(pr.base.ref, bold=True)}@{pr.base.sha}", err=True)

    workflow_head = None
    workflow_base = None
    messages = []

    def item_show_func(workflow):
       workflow_id = str(workflow.id) if hasattr(workflow, "id") else "?"
       head_found = "no" if workflow_head is None else "yes"
       base_found = "no" if workflow_base is None else "yes"
       return f"{workflow_id} head:{head_found} base:{base_found}"

    with click.progressbar(
            repo.get_workflow_runs(),
            label="Loading workflows",
            item_show_func=item_show_func,
    ) as workflows_bar:
        for workflow in workflows_bar:
            # workflow.head_commit.sha is not available, so we take the latest
            # TODO check if PR is the latest by parsing log files?
            if workflow.head_repository == pr.head.repo and workflow.head_branch == pr.head.ref and workflow_head is None:
                if workflow.get_artifacts().totalCount == 0:
                    messages.append(dict(message=f"Skipping workflow {workflow.html_url} on {workflow.head_branch} with no artifacts", fg="red", err=True))
                    continue
                workflow_head = workflow
            if workflow.head_repository == repo and workflow.head_branch == pr.base.ref and workflow_base is None:
                if workflow.get_artifacts().totalCount == 0:
                    messages.append(dict(message=f"Skipping workflow {workflow.html_url} on {workflow.head_branch} with no artifacts", fg="red", err=True))
                    continue
                workflow_base = workflow
            if workflow_head is not None and workflow_base is not None:
                break

    if workflow_head is None:
        click.secho("No completed workflow found for head branch", fg="red")
        ctx.exit(1)
    if workflow_base is None:
        click.secho("No completed workflow found for base branch", fg="red")
        ctx.exit(1)

    for message in messages:
        click.secho(**message)

    click.echo(f"PR base workflow: {workflow_base.html_url}")
    click.echo(f"PR head workflow: {workflow_head.html_url}")

    click.echo(download_artifact(workflow_base, artifact_name, token=token, click=click))
    click.echo(download_artifact(workflow_head, artifact_name, token=token, click=click))


@click.command()
@click.option('--artifact-name', default="rec_dis_18x275_minQ2=1000_craterlake_18x275.edm4eic.root")
@click.option('--token', envvar="GITHUB_TOKEN", required=True, help="GitHub access token (defaults to GITHUB_TOKEN environment variable)")
@click.option('--owner', default="eic", help="Owner of the target repository")
@click.option('--repo', default="EICrecon", help="Name of the target repository")
@click.argument('ref', type=str)
@click.pass_context
def rev(ctx: click.Context, artifact_name: str, owner: str, ref: str, repo: str, token: str):
    gh = Github(auth=Auth.Token(token))
    repo = gh.get_user(owner).get_repo(repo)

    rev = repo.get_commit(ref)

    def item_show_func(workflow):
       workflow_id = str(workflow.id) if hasattr(workflow, "id") else "?"
       head_found = "no" if workflow_head is None else "yes"
       return f"{workflow_id} head:{head_found}"

    workflow_head = None
    messages = []

    with click.progressbar(
            repo.get_workflow_runs(),
            label="Loading workflows",
            item_show_func=item_show_func,
    ) as workflows_bar:
        for workflow in workflows_bar:
            # workflow.head_commit.sha is not available, so we take the latest
            # TODO check if PR is the latest by parsing log files?
            if workflow.head_repository == repo and workflow.head_sha == rev.sha and workflow_head is None:
                if workflow.get_artifacts().totalCount == 0:
                    messages.append(dict(message=f"Skipping workflow {workflow.html_url} on {workflow.head_branch} with no artifacts", fg="red", err=True))
                    continue
                workflow_head = workflow
            if workflow_head is not None:
                break

    if workflow_head is None:
        click.secho("No completed workflow found for head branch", fg="red")
        ctx.exit(1)

    for message in messages:
        click.secho(**message)

    click.echo(f"PR head workflow: {workflow_head.html_url}")

    click.echo(download_artifact(workflow_head, artifact_name, token=token, click=click))


class ForwardGroup(click.Group):
    def resolve_command(self, ctx, args):
        try:
            cmd_name, cmd, args = super().resolve_command(ctx, args)
        except click.exceptions.UsageError as e:
            click.secho(f"Invoking `capy' without subcommand is deprecated. Use `capy pr'.", fg="yellow", err=True)
            args = ["pr"] + args
            cmd_name, cmd, args = super().resolve_command(ctx, args)
        return cmd_name, cmd, args

@click.group(cls=ForwardGroup, context_settings={'help_option_names': ['-h', '--help']})
@click.option('--artifact-name', default="rec_dis_18x275_minQ2=1000_craterlake_18x275.edm4eic.root")
@click.option('--token', envvar="GITHUB_TOKEN", required=True, help="GitHub access token (defaults to GITHUB_TOKEN environment variable)")
@click.option('--owner', default="eic", help="Owner of the target repository")
@click.option('--repo', default="EICrecon", help="Name of the target repository")
def capy(**kwargs):
    pass


capy.add_command(pr)
capy.add_command(rev)
