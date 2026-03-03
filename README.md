### Per Piece Payroll

Per Piece production, salary booking, JV posting, payment JV posting, and reporting.

### What this app installs

- Custom DocTypes: `Per Piece Salary`, `Per Piece`
- Item fields:
  - `custom_process_type` (Select: Cutting, Stitching, Quilting, Packing)
  - `custom_rate_per_piece` (Float)
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

### Notes

- App expects `erpnext` and `hrms` to be installed.
- If `Item.custom_process_type` already exists as `Link`, setup auto-converts it to `Select` to avoid install failure.
- In container/cloud setups without `supervisorctl`, `bench get-app` may end with a restart error. This does not always mean app fetch/install failed.

### Troubleshooting (new server)

1. If you see `Could not find DocType: Per Piece` during first install:
   - Pull latest `main` and run:
   ```bash
   bench --site <your-site> migrate
   bench --site <your-site> execute per_piece_payroll.api.apply_per_piece_payroll_setup
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
