### Per Piece Payroll

Per Piece production, salary booking, JV posting, payment JV posting, and reporting.

### What this app installs

- Custom DocTypes: `Per Piece Salary`, `Per Piece`
- Per Piece Salary fields:
  - `item_group` (Link: `Item Group`)
  - `employee` (Link: `Employee`)
- Per Piece child table fields:
  - `process_size` (Data, auto-loaded from `Item.custom_prd_process_and_sizes`)
- Item tables used:
  - `custom_prd_process_and_sizes` (`PRD Process and Sizes`) with `process_type`, `process_size`, `rate`
- Desk form and web page:
  - child `Product` loads only from selected `Item Group`
  - child rows can auto-load all `Item + Process Type + Process Size + Rate` combinations from the selected `Item Group`
- API Server Scripts:
  - `get_per_piece_salary_report`
  - `create_per_piece_salary_entry`
  - `create_per_piece_salary_jv`
  - `cancel_per_piece_salary_jv`
  - `create_per_piece_salary_payment_jv`
  - `cancel_per_piece_salary_payment_jv`
- Client Script: `Per Piece Salary Update Child`
- Reports:
  - `Per Piece Salary Report`
  - `Per Piece Query Report Simple`
- Web Page: `per-piece-report`
- Print Format: `Per Piece Print`
- Custom HTML Block: `Advances`

### Installation (GitHub, `site1.local`)

Get app from GitHub (ERPNEXT-PAKISTAN repo):

```bash
bench get-app https://github.com/ERPNEXT-PAKISTAN/Per-Piece-Salary.git --branch main
bench --site site1.local install-app per_piece_payroll
bench --site site1.local migrate
bench --site site1.local clear-cache
bench --site site1.local clear-website-cache
bench restart
```

Optional safe re-apply:

```bash
bench --site site1.local execute per_piece_payroll.api.apply_per_piece_payroll_setup
```

### Update on Existing Client Server (Single Correct Command Set)

If app is already installed, do not run `bench get-app` again.
Use this exact sequence (works for benches where remote is either `origin` or `upstream`):

```bash
# set your values
BENCH_PATH=/home/frappe/frappe-bench
SITE=site1.local

cd "$BENCH_PATH" || exit 1

# 0) backup before update
bench --site "$SITE" backup --with-files

# 1) pull latest code
git -C apps/per_piece_payroll remote -v
git -C apps/per_piece_payroll pull origin main || git -C apps/per_piece_payroll pull upstream main
git -C apps/per_piece_payroll log -1 --oneline

# 2) apply schema + fixtures + app setup
bench --site "$SITE" migrate

# 3) force app setup once (ensures legacy UI scripts/web page are cleaned if present)
bench --site "$SITE" execute per_piece_payroll.per_piece_setup.apply

# 4) cache/build/restart
bench --site "$SITE" clear-cache
bench --site "$SITE" clear-website-cache
bench build --app per_piece_payroll
bench restart
```

If `bench restart` is not available on your hosting platform, restart processes from your hosting panel/container supervisor.

Where to run:

- Run all commands on the **client server terminal** (SSH), not on your local VS Code machine.
- Run from bench root: `cd /home/frappe/frappe-bench` (or your actual bench path).
- Replace `site1.local` with your real site name.

If you want to scan all installed apps to find who is recreating legacy UI scripts:

```bash
cd /home/frappe/frappe-bench

# Search all apps for legacy script IDs
grep -RInE "create_per_piece_salary_entry|create_per_piece_salary_jv|create_per_piece_salary_payment_jv|cancel_per_piece_salary_jv|cancel_per_piece_salary_payment_jv|get_per_piece_salary_report|Per Piece Salary Auto Load|Per Piece Salary Update Child" apps

# Search fixture declarations that import Server/Client Script
grep -RInE "\"dt\"[[:space:]]*:[[:space:]]*\"Server Script\"|\"dt\"[[:space:]]*:[[:space:]]*\"Client Script\"|\"doctype\"[[:space:]]*:[[:space:]]*\"Server Script\"|\"doctype\"[[:space:]]*:[[:space:]]*\"Client Script\"" apps
```

Optional (`rg` / ripgrep): faster search tool used in some commands.

```bash
# Ubuntu/Debian
sudo apt update
sudo apt install -y ripgrep

# verify
rg --version
```

Quick check after update:

```bash
bench --site "$SITE" console
```

```python
frappe.get_all("Server Script", filters={"name": ["in", [
    "get_per_piece_salary_report",
    "create_per_piece_salary_entry",
    "create_per_piece_salary_jv",
    "cancel_per_piece_salary_jv",
    "create_per_piece_salary_payment_jv",
    "cancel_per_piece_salary_payment_jv",
]]}, fields=["name", "disabled"])

frappe.get_all("Client Script", filters={"name": ["in", [
    "Per Piece Salary Auto Load",
    "Per Piece Salary Update Child",
]]}, fields=["name", "enabled"])
```

### Screenshots

![Per Piece 1](docs/images/Per%20Piece1.png)

![Per Piece 2](docs/images/Per%20Piece2.png)

![Per Piece 3](docs/images/Per%20Piece3.png)

![Per Piece 4](docs/images/Per%20Piece4.png)

![Per Piece 5](docs/images/Per%20Piece5.png)

![Per Piece 6](docs/images/Per%20Piece6.png)

![Per Piece 7](docs/images/Per%20Piece7.png)

![Per Piece 8](docs/images/Per%20Piece8.png)

### Notes

- App expects `erpnext` and `hrms` to be installed.
- `appe` is **not** required by `per_piece_payroll`.
- The app now uses `Item.custom_prd_process_and_sizes` as the Item-side source of process, size, and rate.
- In container/cloud setups without `supervisorctl`, `bench get-app` may end with a restart error. This does not always mean app fetch/install failed.
- Historical data protection: submitted or booked/paid `Per Piece Salary` entries are locked by server-side guard logic. App updates (`pull`, `migrate`, `build`) are intended to affect new entries, not change old posted qty/rate/amount rows.

### Troubleshooting (new server)

1. If you see `Could not find DocType: Per Piece` during first install:
   - Pull latest `main` and run:
   ```bash
   bench --site site1.local migrate
   bench --site site1.local execute per_piece_payroll.api.apply_per_piece_payroll_setup
   ```
   - Latest setup includes fallback creation of core DocTypes (`Per Piece`, `Per Piece Salary`) from fixtures.

2. If you see `ModuleNotFoundError: No module named 'per_piece_payroll'`:
   - Reinstall package link in bench env:
   ```bash
   ./env/bin/pip uninstall -y per_piece_payroll || true
   ./env/bin/pip install -e ./apps/per_piece_payroll --no-build-isolation
   ```
   - Then run migrate and restart your platform/container process.

3. If app remote is `upstream` (common with `bench get-app`), use:
   ```bash
   git -C apps/per_piece_payroll pull upstream main
   ```

4. If `bench get-app` fails with `Directory not empty` for `Per-Piece-Salary` -> `per_piece_payroll`:
  - This usually means either:
  ```text
  - the app is already present in apps/per_piece_payroll
  - a failed clone left apps/Per-Piece-Salary behind
  ```
  - For an existing installation, do not use `bench get-app` again. Update like this instead:
  ```bash
  cd /home/frappe/frappe-bench
  git -C apps/per_piece_payroll pull origin main || git -C apps/per_piece_payroll pull upstream main
  bench --site site1.local migrate
  bench --site site1.local clear-cache
  bench --site site1.local clear-website-cache
  bench build --app per_piece_payroll
  bench restart
  ```
  - If this was a failed fresh install and the extra folder exists, remove only the failed clone folder and retry:
  ```bash
  rm -rf /home/frappe/frappe-bench/apps/Per-Piece-Salary
  bench get-app https://github.com/ERPNEXT-PAKISTAN/Per-Piece-Salary.git --branch main
  ```

5. If you want to remove `appe` from a site/bench:
   - First remove it from site installed apps:
   ```bash
   bench --site site1.local remove-from-installed-apps appe
   bench --site site1.local migrate
   bench --site site1.local clear-cache
   bench --site site1.local clear-website-cache
   ```
   - Then remove app from bench:
   ```bash
   bench remove-app appe
   ```
   - If your host blocks `bench restart`, restart services from hosting panel/container supervisor.

### Troubleshooting (existing server data entry)

If a Salary JV or Payment JV was canceled directly from ERPNext `Journal Entry` screen, some old links may remain on `Per Piece` rows until sync runs.

Symptom during Data Entry update:

```text
Save Failed
This entry is already booked/paid and cannot be edited from Data Enter.
```

Immediate fix on server:

```bash
cd /home/frappe/frappe-bench
bench --site site1.local execute per_piece_payroll.api.force_sync_per_piece_status
bench --site site1.local clear-cache
```

Then try update again from web Data Entry.

Permanent fix (code): update app to latest `main` and run migrate. Latest code auto-cleans canceled Salary JV and Payment JV links before Data Entry edit validation.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/per_piece_payroll
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
