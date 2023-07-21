import io
from pathlib import Path
from zipfile import ZipFile

import requests


def download_artifact(workflow, artifact_name, token=None, click=None):
    artifacts = [artifact for artifact in workflow.get_artifacts() if artifact.name == artifact_name]
    if not artifacts:
        if click is not None:
            click.secho(f"Can not obtain {artifact_name}", fg="red", err=True)
            if workflow.get_artifacts():
                click.secho(f"Available artifacts:", fg="red", err=True)
                for artifact in workflow.get_artifacts():
                    click.echo(artifact.name)
            else:
                click.secho(f"No artifacts available", fg="red", err=True)
        return None

    outdir = Path(workflow.created_at.isoformat().replace(":", "-") + "_" + workflow.head_sha)
    outpath = outdir / artifact_name
    if outpath.exists():
        return outpath

    if not outpath.parent.exists():
        outdir.mkdir()

    artifact, = artifacts
    req = requests.get(artifact.archive_download_url, headers={"Authorization": f"token {token}"} if token else {})
    zfp = ZipFile(io.BytesIO(req.content))
    if artifact_name in zfp.namelist():
        zip_filename = artifact_name
    elif len(zfp.namelist()) == 1:
        zip_filename, = zfp.namelist()
        if click is not None:
            click.secho(f"Can't locate {artifact_name} in the artifact ZIP archive, using {zip_filename} instead", fg="orange", err=True)
    else:
        if click is not None:
            click.secho(f"Can't locate {artifact_name} in the artifact ZIP archive", fg="red", err=True)
        return None
    with zfp.open(zip_filename) as fp_zip:
        with open(outpath, "wb") as fp_out:
            fp_out.write(fp_zip.read())

    return outpath
