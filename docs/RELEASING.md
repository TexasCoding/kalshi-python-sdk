# Releasing

Releases are published to PyPI automatically by `.github/workflows/release.yml`
when a `v*` tag is pushed.

## One-time PyPI setup (must happen before the first tag push)

The workflow uses **PyPI trusted publishing** (OIDC) — no API token is stored
in GitHub Secrets. This must be configured on PyPI's side once, then it works
for every subsequent release.

1. Create the PyPI project (first publish only):
   - Go to https://pypi.org/manage/account/publishing/
   - Sign in as the account that owns `kalshi-sdk`
   - Under **Add a new pending publisher**, fill in:
     - **PyPI Project Name**: `kalshi-sdk`
     - **Owner**: `TexasCoding`
     - **Repository name**: `kalshi-python-sdk`
     - **Workflow name**: `release.yml`
     - **Environment name**: `pypi`

2. Create the `pypi` environment in GitHub:
   - Repo Settings → Environments → New environment → name it `pypi`
   - (Optional but recommended) Add a required reviewer so a human approves
     each publish before the workflow uploads to PyPI.

After step 1, the **first** publish via the workflow registers the project
with the trusted publisher. From then on, any subsequent `v*` tag pushed
from this repo can publish without further configuration.

## Cutting a release

1. Bump `version` in `pyproject.toml` and `__version__` in `kalshi/__init__.py`.
   The `## <version>` heading in `CHANGELOG.md` must use the same version (the
   workflow extracts the section by that heading for the release body).
2. Add a section to `CHANGELOG.md` for the new version. The release workflow
   extracts the section between `## <version>` and the next `## ` heading
   and uses it as the GitHub Release body, so write it for that audience.
3. Commit on `main`.
4. Tag and push:

   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

5. The workflow will:
   - Verify the git tag matches `pyproject.toml` version (build fails if they drift).
   - Build sdist + wheel with `uv build`.
   - Run `twine check` on the artifacts.
   - Upload to PyPI via OIDC trusted publisher (gated by the `pypi` environment
     reviewer if configured).
   - Create a GitHub Release with the CHANGELOG section as the body and the
     wheel + sdist attached.

Tags containing a `-` (e.g. `v1.0.0-rc1`) are marked as `prerelease` on
GitHub automatically.

## If something goes wrong

- **Tag mismatch**: bump pyproject version to match the tag, force-push the
  fixed commit if the tag hasn't published yet, or delete the tag and re-tag.
- **PyPI rejects the upload**: artifact already uploaded for that version.
  Bump to the next patch and re-tag — PyPI versions are immutable.
- **Workflow blocked at the `pypi` environment**: a required reviewer needs
  to approve in the GitHub Actions UI.
