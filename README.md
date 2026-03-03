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

### Installation on another server (start to end)

1. Copy app folder to target bench:

```bash
cd /home/frappe/frappe-bench/apps
rsync -a /path/from/source/per_piece_payroll ./per_piece_payroll
```

2. Install python package in bench env:

```bash
cd /home/frappe/frappe-bench
./env/bin/pip install -e apps/per_piece_payroll --no-build-isolation
```

3. Add app to bench apps list:

```bash
bench --site <your-site> list-apps
```

4. Install app on site:

```bash
bench --site <your-site> install-app per_piece_payroll
bench --site <your-site> migrate
```

5. (Optional) Re-apply setup safely:

```bash
bench --site <your-site> execute per_piece_payroll.api.apply_per_piece_payroll_setup
```

### Notes

- App expects `erpnext` and `hrms` to be installed.
- If `Item.custom_process_type` already exists as `Link`, setup auto-converts it to `Select` to avoid install failure.

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
