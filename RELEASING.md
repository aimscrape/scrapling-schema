# Releasing to PyPI

This repo is set up to publish releases automatically via **GitHub Actions + PyPI Trusted Publishing (OIDC)**.
That means you can publish to PyPI **without** storing a long-lived PyPI API token in GitHub secrets.

## 1) One-time setup (recommended): PyPI Trusted Publisher

### On PyPI

1. Create the project on PyPI (first publish can be done via manual upload; see below), or reserve the name if you already own it.
2. Go to the project settings on PyPI and add a **Trusted Publisher**:
   - Provider: GitHub
   - Owner: `aimscrape`
   - Repository: `scrapling-schema`
   - Workflow: `.github/workflows/publish.yml`
   - Environment: `pypi` (recommended)

### On GitHub

1. In the GitHub repo settings, create an **Environment** named `pypi`.
2. (Optional but recommended) Add required reviewers for the `pypi` environment to protect releases.

## 2) Release flow (automatic publish)

### Option A: use the helper script (recommended)

From the repo root:

```bash
bin/publish patch --push --release
```

This will:
- require a clean working tree (`git status` must be empty)
- update `CHANGELOG.md` by moving `## [Unreleased]` notes into the new version section
  - by default this **fails** if `## [Unreleased]` is empty (to keep release notes detailed)
  - escape hatches: `--allow-empty-changelog` (adds "No notable changes.") or `--no-changelog` (not recommended)
- bump `pyproject.toml` version (patch/minor/major)
- run tests (and build by default)
- commit the version bump
- create an annotated tag `vX.Y.Z`
- push `main` + tag to GitHub
- create a GitHub Release (requires `gh` CLI)

If you want to validate the release on TestPyPI first (no web UI):

```bash
bin/publish patch --push --test
```

To gate the PyPI release behind a successful TestPyPI upload:

```bash
bin/publish patch --push --test --release
```

You can customize the release commit message:

```bash
bin/publish patch -m "chore(release): %s" --push --release
```

If you want to update the changelog manually (without releasing), use:

```bash
bin/changelog check
bin/changelog release X.Y.Z --date YYYY-MM-DD
```

### Option B: do it manually

1. Bump the version in `pyproject.toml`:
   - `[project].version = "x.y.z"`
2. Commit and push to `main`.
3. Create and push a git tag that matches the version (this is enforced in CI):

   ```bash
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```

4. Create a GitHub Release for that tag (or publish it directly in the UI).

When the GitHub Release is **published**, GitHub Actions runs `.github/workflows/publish.yml`:
- builds sdist/wheel
- verifies tag `vX.Y.Z` matches `pyproject.toml` version `X.Y.Z`
- publishes to PyPI

## 3) TestPyPI (dry run)

You can run the publish workflow manually:

- GitHub → Actions → “Publish to PyPI” → Run workflow
- Choose `testpypi`

This will upload to TestPyPI (useful to validate metadata/rendering).

Note: TestPyPI also supports Trusted Publishing. If you want OIDC-based uploads
to TestPyPI, add a Trusted Publisher entry there as well (same repo/workflow),
and optionally create a GitHub environment named `testpypi`.

## 4) Manual publish (fallback)

If you don’t want to use Trusted Publishing, you can publish from your machine:

```bash
python -m pip install -U build twine
python -m build
python -m twine upload dist/*
```

Notes:
- You’ll need a PyPI API token for your account/project.
- Prefer using `__token__` as username and the token as password (Twine supports this).
