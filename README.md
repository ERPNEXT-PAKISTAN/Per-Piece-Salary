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

### Update on Existing Client Server

If app is already installed, use:

```bash
cd /home/frappe/frappe-bench

# 1) Pull latest app code from GitHub
git -C apps/per_piece_payroll remote -v
git -C apps/per_piece_payroll pull origin main || git -C apps/per_piece_payroll pull upstream main

# 2) Verify latest features exist in code (for servers without rg)
grep -nE "pp-po-number|pp-entry-no|pp-search-any|simple_month_amount" apps/per_piece_payroll/per_piece_payroll/per_piece_setup.py

# 3) Apply to your site
bench --site site1.local migrate
bench --site site1.local execute per_piece_payroll.api.apply_per_piece_payroll_setup
bench --site site1.local clear-cache
bench --site site1.local clear-website-cache

# 4) Rebuild and restart
bench build --app per_piece_payroll
bench restart
```

If `bench restart` is not available on your hosting platform, restart services from your platform panel/container instead.

### Update Other Server from GitHub (Quick Copy)

Use this on any other ERPNext server where app is already installed:

```bash
cd /home/frappe/frappe-bench
git -C apps/per_piece_payroll remote -v
git -C apps/per_piece_payroll pull origin main || git -C apps/per_piece_payroll pull upstream main
grep -nE "pp-po-number|pp-entry-no|pp-search-any|simple_month_amount" apps/per_piece_payroll/per_piece_payroll/per_piece_setup.py
bench --site site1.local migrate
bench --site site1.local execute per_piece_payroll.api.apply_per_piece_payroll_setup
bench --site site1.local clear-cache
bench --site site1.local clear-website-cache
bench build --app per_piece_payroll
bench restart
```

Example:

```bash
bench --site site1.local migrate
bench --site site1.local execute per_piece_payroll.api.apply_per_piece_payroll_setup
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

4. If you want to remove `appe` from a site/bench:
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
