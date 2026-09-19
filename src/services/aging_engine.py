"""
Aging calculation engine for AR classification and risk assignment.
"""

from datetime import date
from typing import Optional
from src.schemas.accounting_schema import AgingBucket


def calculate_days_overdue(due_date: date, reference_date: Optional[date] = None) -> int:
    """
    Calculate the number of days an invoice is overdue relative to a reference date.

    Args:
        due_date: Contractual due date of invoice.
        reference_date: Reference date (defaults to today if not provided).

    Returns:
        int: Positive if past due, zero if due today, negative if in the future.
    """
    if reference_date is None:
        reference_date = date.today()
    return (reference_date - due_date).days


def determine_aging_bucket(days_overdue: int) -> AgingBucket:
    """
    Assign an invoice to its corresponding AR aging bucket based on days overdue:
      - <= 0: CURRENT
      - 1 to 14: OVERDUE_7_PLUS (actionable at 7+)
      - 15 to 29: OVERDUE_15_PLUS
      - 30 to 59: OVERDUE_30_PLUS
      - >= 60: OVERDUE_60_PLUS

    Args:
        days_overdue: Number of days past due.

    Returns:
        AgingBucket: Mapped aging bucket enum.
    """
    if days_overdue <= 0:
        return AgingBucket.CURRENT
    elif 1 <= days_overdue <= 14:
        return AgingBucket.OVERDUE_7_PLUS
    elif 15 <= days_overdue <= 29:
        return AgingBucket.OVERDUE_15_PLUS
    elif 30 <= days_overdue <= 59:
        return AgingBucket.OVERDUE_30_PLUS
    else:
        return AgingBucket.OVERDUE_60_PLUS
