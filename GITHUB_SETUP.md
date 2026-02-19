# Push to Private GitHub & Install via pip

This guide covers pushing this plugin to a **private GitHub repo** and installing it in other projects via `pip install`.

---

## 1. Create a private repo on GitHub

1. Go to [GitHub](https://github.com/new).
2. Set **Repository name** (e.g. `superset-data-entry-plugin`).
3. Choose **Private**.
4. Do **not** add a README, .gitignore, or license (this repo already has them).
5. Click **Create repository**.

---

## 2. Push this project to the new repo

From this project directory, run (replace `YOUR_ORG` and `REPO_NAME` with your GitHub org/username and repo name):

```bash
# Add the remote
git remote add origin https://github.com/YOUR_ORG/REPO_NAME.git

# Or with SSH:
# git remote add origin git@github.com:YOUR_ORG/REPO_NAME.git

# Push (branch is already 'main')
git push -u origin main
```

For a **private repo**, use one of:

- **HTTPS with token:**  
  When prompted for password, use a [Personal Access Token](https://github.com/settings/tokens) (with `repo` scope).
- **SSH:**  
  Ensure your SSH key is added to GitHub; then use the `git@github.com:...` remote and push as above.

---

## 3. Install in other projects via pip

Other projects (e.g. Superset instances) can install this plugin from your private repo.

Use the **same Python environment as Superset**. Always use `--no-deps` so pip does not upgrade Superset’s Flask/SQLAlchemy.

### Option A: HTTPS (private repo with token)

```bash
pip install --no-deps "git+https://USERNAME:TOKEN@github.com/YOUR_ORG/REPO_NAME.git@main"
```

Replace `USERNAME`, `TOKEN`, `YOUR_ORG`, `REPO_NAME`, and `main` (branch or tag) as needed.

### Option B: SSH

```bash
pip install --no-deps "git+ssh://git@github.com/YOUR_ORG/REPO_NAME.git@main"
```

### Option C: Pin to a tag (recommended for production)

```bash
# In this repo, create a tag and push it:
git tag v1.0.0
git push origin v1.0.0

# In the other project:
pip install --no-deps "git+https://USERNAME:TOKEN@github.com/YOUR_ORG/REPO_NAME.git@v1.0.0"
```

After installing, configure Superset and run migrations as described in **README.md** (Configure Superset, Run database migrations).

---

## 4. Maintain and develop in the private repo

- **Branching:** Use branches (e.g. `develop`, feature branches) and merge to `main` when ready.
- **Releases:** Tag versions (e.g. `v1.0.0`) and push tags so other projects can pin to a tag.
- **Updates:** In the consuming project, upgrade with:
  ```bash
  pip install --no-deps --upgrade "git+https://USERNAME:TOKEN@github.com/YOUR_ORG/REPO_NAME.git@main"
  ```
  or use a tag instead of `@main` for a specific version.

---

## 5. Optional: Update package URLs

If you want PyPI metadata (and `pip show`) to point to your repo, edit:

- **setup.py:** `url`, `project_urls` (e.g. replace `99x/superset-data-entry-plugin` with `YOUR_ORG/REPO_NAME`).
- **pyproject.toml:** `[project.urls]` (same replacement).

This does not affect `pip install` from Git; it only affects displayed links and metadata.
