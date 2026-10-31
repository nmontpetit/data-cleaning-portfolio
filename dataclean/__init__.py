"""data-cleaner package — declarative, auditable CSV cleaning."""

from .cleaner import AuditEntry, ColumnRule, DataCleaner, DEFAULT_RULES, clean_csv

__all__ = ["AuditEntry", "ColumnRule", "DataCleaner", "DEFAULT_RULES", "clean_csv"]
__version__ = "0.2.0"
