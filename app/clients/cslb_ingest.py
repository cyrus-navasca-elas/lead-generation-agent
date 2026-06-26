from __future__ import annotations

import csv
import re
import sqlite3
from datetime import date, datetime
from pathlib import Path

from app.core.logging import get_logger

log = get_logger(__name__)

# The CSV header has a parenthesized column name and free-form spacing; lock
# the canonical Python-side mapping here.
CSV_COLUMNS = [
    "LicenseNo",
    "LastUpdate",
    "BusinessName",
    "BUS-NAME-2",
    "FullBusinessName",
    "MailingAddress",
    "City",
    "State",
    "County",
    "ZIPCode",
    "country",
    "BusinessPhone",
    "BusinessType",
    "IssueDate",
    "ReissueDate",
    "ExpirationDate",
    "InactivationDate",
    "ReactivationDate",
    "PendingSuspension",
    "PendingClassRemoval",
    "PendingClassReplace",
    "PrimaryStatus",
    "SecondaryStatus",
    "Classifications(s)",
    "AsbestosReg",
    "WorkersCompCoverageType",
    "WCInsuranceCompany",
    "WCPolicyNumber",
    "WCEffectiveDate",
    "WCExpirationDate",
    "WCCancellationDate",
    "WCSuspendDate",
    "CBSuretyCompany",
    "CBNumber",
    "CBEffectiveDate",
    "CBCancellationDate",
    "CBAmount",
    "WBSuretyCompany",
    "WBNumber",
    "WBEffectiveDate",
    "WBCancellationDate",
    "WBAmount",
    "DBSuretyCompany",
    "DBNumber",
    "DBEffectiveDate",
    "DBCancellationDate",
    "DBAmount",
    "DateRequired",
    "DiscpCaseRegion",
    "DBBondReason",
    "DBCaseNo",
    "NAME-TP-2",
]


SQL_COLUMNS = [
    "license_no",
    "last_update",
    "business_name",
    "business_name_2",
    "full_business_name",
    "mailing_address",
    "city",
    "state",
    "county",
    "zip_code",
    "country",
    "business_phone",
    "business_type",
    "issue_date",
    "reissue_date",
    "expiration_date",
    "inactivation_date",
    "reactivation_date",
    "pending_suspension",
    "pending_class_removal",
    "pending_class_replace",
    "primary_status",
    "secondary_status",
    "classifications_raw",
    "asbestos_reg",
    "wc_coverage_type",
    "wc_insurance_company",
    "wc_policy_number",
    "wc_effective_date",
    "wc_expiration_date",
    "wc_cancellation_date",
    "wc_suspend_date",
    "cb_surety_company",
    "cb_number",
    "cb_effective_date",
    "cb_cancellation_date",
    "cb_amount",
    "wb_surety_company",
    "wb_number",
    "wb_effective_date",
    "wb_cancellation_date",
    "wb_amount",
    "db_surety_company",
    "db_number",
    "db_effective_date",
    "db_cancellation_date",
    "db_amount",
    "date_required",
    "discp_case_region",
    "db_bond_reason",
    "db_case_no",
    "name_tp_2",
    "classifications_norm",
]

DATE_COLUMNS = {
    "last_update",
    "issue_date",
    "reissue_date",
    "expiration_date",
    "inactivation_date",
    "reactivation_date",
    "wc_effective_date",
    "wc_expiration_date",
    "wc_cancellation_date",
    "wc_suspend_date",
    "cb_effective_date",
    "cb_cancellation_date",
    "wb_effective_date",
    "wb_cancellation_date",
    "db_effective_date",
    "db_cancellation_date",
    "date_required",
}

INT_COLUMNS = {"cb_amount", "wb_amount", "db_amount"}


def ensure_db(csv_path: Path, db_path: Path, *, force: bool = False) -> int:
    """Build/refresh the SQLite database from the CSLB CSV.

    Returns the row count present in the database after the call. The DB is
    rebuilt when (a) it doesn't exist, (b) the CSV is newer, or (c) force=True.
    """
    csv_path = Path(csv_path).resolve()
    db_path = Path(db_path).resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if not csv_path.exists():
        log.warning("cslb_ingest.no_csv", path=str(csv_path))
        if db_path.exists():
            return _row_count(db_path)
        # Create an empty DB so the rest of the system can still boot.
        _init_schema(db_path)
        return 0

    if (
        not force
        and db_path.exists()
        and db_path.stat().st_mtime >= csv_path.stat().st_mtime
    ):
        return _row_count(db_path)

    log.info("cslb_ingest.start", csv=str(csv_path), db=str(db_path))
    _init_schema(db_path)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("DELETE FROM licenses")

        placeholders = ",".join(["?"] * len(SQL_COLUMNS))
        insert_sql = (
            f"INSERT INTO licenses ({','.join(SQL_COLUMNS)}) "
            f"VALUES ({placeholders})"
        )

        rows_buffer: list[tuple] = []
        BATCH = 5000
        count = 0
        with csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.reader(f)
            header = next(reader)
            if len(header) != len(CSV_COLUMNS):
                log.warning(
                    "cslb_ingest.header_mismatch",
                    expected=len(CSV_COLUMNS),
                    actual=len(header),
                )
            for raw in reader:
                row = _normalize_row(raw)
                rows_buffer.append(row)
                count += 1
                if len(rows_buffer) >= BATCH:
                    conn.executemany(insert_sql, rows_buffer)
                    rows_buffer.clear()
            if rows_buffer:
                conn.executemany(insert_sql, rows_buffer)

        conn.commit()
        _create_indexes(conn)
        conn.commit()
        log.info("cslb_ingest.done", rows=count)
        return count
    finally:
        conn.close()


def _init_schema(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    try:
        col_defs = []
        for col in SQL_COLUMNS:
            if col in INT_COLUMNS:
                col_defs.append(f"{col} INTEGER")
            else:
                col_defs.append(f"{col} TEXT")
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS licenses ({', '.join(col_defs)})"
        )
        conn.commit()
    finally:
        conn.close()


def _create_indexes(conn: sqlite3.Connection) -> None:
    indexes = [
        ("idx_status", "primary_status"),
        ("idx_county", "county"),
        ("idx_btype", "business_type"),
        ("idx_classifications", "classifications_norm"),
        ("idx_expiration", "expiration_date"),
        ("idx_cb_amount", "cb_amount"),
    ]
    for name, col in indexes:
        conn.execute(f"CREATE INDEX IF NOT EXISTS {name} ON licenses({col})")


def _normalize_row(raw: list[str]) -> tuple:
    # Pad/truncate to the canonical width so downstream indexing is safe.
    if len(raw) < len(CSV_COLUMNS):
        raw = raw + [""] * (len(CSV_COLUMNS) - len(raw))
    elif len(raw) > len(CSV_COLUMNS):
        raw = raw[: len(CSV_COLUMNS)]

    values: list = []
    for col_name, value in zip(SQL_COLUMNS, raw, strict=False):
        cleaned = value.strip() if value else ""
        if col_name in DATE_COLUMNS:
            values.append(_to_iso_date(cleaned))
        elif col_name in INT_COLUMNS:
            values.append(_to_int(cleaned))
        else:
            values.append(cleaned or None)

    # classifications_norm is computed from classifications_raw.
    raw_classes = values[SQL_COLUMNS.index("classifications_raw")] or ""
    values.append(normalize_classifications(raw_classes))
    return tuple(values)


def _to_iso_date(value: str) -> str | None:
    if not value:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _to_int(value: str) -> int | None:
    if not value:
        return None
    cleaned = re.sub(r"[,$\s]", "", value)
    try:
        return int(float(cleaned))
    except (ValueError, TypeError):
        return None


def normalize_classifications(raw: str) -> str:
    """Convert ' C10| C36| HAZ' → '|C10|C36|HAZ|'.

    Strips spaces, removes hyphens (so 'C-10' and 'C10' are equivalent),
    uppercases. Surrounded with delimiters so LIKE '%|C10|%' is a safe
    word-boundary match.
    """
    parts = [p.strip().upper().replace("-", "") for p in raw.split("|") if p.strip()]
    if not parts:
        return ""
    return "|" + "|".join(parts) + "|"


def _row_count(db_path: Path) -> int:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("SELECT COUNT(*) FROM licenses")
        return int(cur.fetchone()[0])
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


def parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
