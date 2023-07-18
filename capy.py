import io
import json
from zipfile import ZipFile
from pathlib import Path

import requests
from github import Github

gh = Github("<insert your token here>")

repo = gh.get_user("eic").get_repo("EICrecon")

def dl_latest_artifact(branch="main"):
    for workflow in repo.get_workflow_runs():
        if workflow.head_branch != branch:
            continue

        #print(workflow.head_branch, workflow.head_sha, workflow.created_at, workflow.raw_data["name"], workflow.html_url)

        outdir = Path(workflow.created_at.isoformat().replace(":", "-") + "_" + workflow.head_sha)
        outpath = outdir / "rec_dis_18x275_minQ2=1000_brycecanyon.edm4eic.root"
        if outpath.exists():
            return outpath
        if not outpath.parent.exists():
            outdir.mkdir()

        flags_artifacts = [a for a in workflow.get_artifacts() if a.name=="rec_dis_18x275_minQ2=1000_brycecanyon.edm4eic.root"]
        #print(flags_artifacts)
        if not flags_artifacts:
            continue
        flags_artifact, = flags_artifacts
        r = requests.get(flags_artifact.archive_download_url, headers={"Authorization": f"token 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"})
        z = ZipFile(io.BytesIO(r.content))
        #print(z.namelist())
        with z.open("rec_dis_18x275_minQ2=1000_brycecanyon.edm4eic.root") as fp_zip:
            with open(outpath, "wb") as fp_out:
                fp_out.write(fp_zip.read())

        return outpath 

#print(dl_latest_artifact())
print(dl_latest_artifact("pr/calo_alg_use_collections"))
#print(dl_latest_artifact("truth-seeding-without-vertex-knowledge"))
#print(dl_latest_artifact("generated-particles-generator-status-equal-one"))
#print(dl_latest_artifact("pr/calo_alg_use_collections"))
#print(dl_latest_artifact("ckf_realseeds"))
#print(dl_latest_artifact("ckf_realseeds_podio_track_params_only"))
