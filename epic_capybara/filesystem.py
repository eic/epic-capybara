import hashlib
from pathlib import Path


def hashdir(path):
    digest = hashlib.md5()

    def recurse(cur_path, digest=None):
        paths = cur_path.iterdir()
        for file_ in sorted([p for p in paths if p.is_file()]):
            digest.update(str(file_.relative_to(path)).encode())
            with open(file_, "rb") as fp:
                digest.update(fp.read())

        paths = cur_path.iterdir()
        for dir_ in sorted([p for p in paths if p.is_dir()]):
            recurse(dir_, digest)

    recurse(path, digest)

    return digest.hexdigest()
