from __future__ import annotations

from per_piece_payroll.per_piece_setup import apply


def after_install() -> None:
    apply()


def after_migrate() -> None:
    apply()
