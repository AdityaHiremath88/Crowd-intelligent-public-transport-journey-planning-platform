from __future__ import annotations

import argparse
import hashlib
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

import duckdb

from backend_v2.config import DATABASE_PATH, FARE_STAGE_IMPORT_REPORT_PATH, FARE_STAGES_PATH

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "p": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def normalize_route_key(value: str) -> str:
    value = re.sub(r"\broute\s*(?:no\.?\s*)?", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\b(?:dn|dwn)\b", "DOWN", value, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _workbook_parts(archive: zipfile.ZipFile) -> tuple[list[str], str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    targets = {item.attrib["Id"]: item.attrib["Target"] for item in relationships.findall("p:Relationship", NS)}
    for sheet in workbook.findall(".//m:sheet", NS):
        if sheet.attrib.get("name") != "DTC Routes":
            continue
        relationship_id = sheet.attrib[f"{{{NS['r']}}}id"]
        target = targets[relationship_id].lstrip("/")
        sheet_path = target if target.startswith("xl/") else str(PurePosixPath("xl") / target)
        strings: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            shared = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            strings = [
                "".join(part.text or "" for part in item.findall(".//m:t", NS))
                for item in shared.findall("m:si", NS)
            ]
        return strings, sheet_path
    raise ValueError("The workbook does not contain a 'DTC Routes' sheet.")


def _sheet_rows(archive: zipfile.ZipFile, sheet_path: str, strings: list[str]) -> list[dict[str, str]]:
    root = ET.fromstring(archive.read(sheet_path))
    rows: list[dict[str, str]] = []
    for row in root.findall(".//m:sheetData/m:row", NS):
        values: dict[str, str] = {}
        for cell in row.findall("m:c", NS):
            reference = cell.attrib.get("r", "")
            column = re.match(r"[A-Z]+", reference)
            if not column:
                continue
            value = cell.find("m:v", NS)
            text = value.text if value is not None else "".join(
                part.text or "" for part in cell.findall(".//m:t", NS)
            )
            if cell.attrib.get("t") == "s" and text:
                text = strings[int(text)]
            values[column.group()] = text or ""
        rows.append(values)
    return rows


def read_dtc_fare_stage_rows(xlsx_path: Path) -> list[tuple[str, str, int, int | None, str, bool]]:
    """Read the published DTC Routes worksheet without an Excel runtime dependency."""
    with zipfile.ZipFile(xlsx_path) as archive:
        strings, sheet_path = _workbook_parts(archive)
        rows = _sheet_rows(archive, sheet_path, strings)

    result: list[tuple[str, str, int, int | None, str, bool]] = []
    for row_index, row in enumerate(rows):
        for route_col, stage_col, marker_col, stop_col in (
            ("D", "C", "E", "F"),
            ("I", "H", "J", "K"),
        ):
            route_label = (row.get(route_col) or "").strip()
            if not route_label.lower().startswith("route"):
                continue
            route_key = normalize_route_key(route_label)
            direction = "DOWN" if route_key.endswith("down") else "UP" if route_key.endswith("up") else "UNKNOWN"
            stop_order = 0
            for following in rows[row_index + 1 :]:
                if (following.get(route_col) or "").strip().lower().startswith("route"):
                    break
                stop_name = (following.get(stop_col) or "").strip()
                if not stop_name:
                    continue
                marker = (following.get(marker_col) or "").strip().casefold() == "fare stage"
                stage_text = (following.get(stage_col) or "").strip()
                stage_number: int | None = None
                if marker:
                    try:
                        stage_number = int(float(stage_text))
                    except ValueError:
                        stage_number = None
                result.append((route_label, route_key, stop_order, stage_number, stop_name, marker))
                stop_order += 1
    if not result:
        raise ValueError("No route stop rows were found in the DTC Routes worksheet.")
    return result


def import_fare_stages(
    *, xlsx_path: Path = FARE_STAGES_PATH,
    database_path: Path = DATABASE_PATH,
    report_path: Path = FARE_STAGE_IMPORT_REPORT_PATH,
) -> dict:
    xlsx_path = xlsx_path.resolve()
    database_path = database_path.resolve()
    if not xlsx_path.is_file():
        raise FileNotFoundError(f"DTC fare-stage workbook not found: {xlsx_path}")
    if not database_path.is_file():
        raise FileNotFoundError(f"Yuktix v2 database not found: {database_path}; import GTFS first.")
    rows = read_dtc_fare_stage_rows(xlsx_path)

    con = duckdb.connect(str(database_path))
    try:
        route_keys = {
            normalize_route_key(row[0])
            for row in con.execute("SELECT DISTINCT route_short_name FROM routes WHERE route_short_name IS NOT NULL").fetchall()
        }
        matched_keys = {row[1] for row in rows} & route_keys
        con.execute("BEGIN TRANSACTION")
        con.execute("""
            CREATE OR REPLACE TABLE dtc_fare_stage_stops (
                route_label VARCHAR,
                route_key VARCHAR,
                route_direction VARCHAR,
                stop_order INTEGER,
                fare_stage_number INTEGER,
                stop_name VARCHAR,
                is_fare_stage BOOLEAN
            )
        """)
        con.executemany(
            "INSERT INTO dtc_fare_stage_stops VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (label, key, "DOWN" if key.endswith("down") else "UP" if key.endswith("up") else "UNKNOWN",
                 order, stage, name, marker)
                for label, key, order, stage, name, marker in rows
            ],
        )
        con.execute("""
            CREATE OR REPLACE TABLE dtc_fare_stage_import_metadata (
                imported_at TIMESTAMPTZ,
                source_file VARCHAR,
                source_sha256 VARCHAR,
                distinct_route_label_count INTEGER,
                unique_route_key_count INTEGER,
                stop_row_count INTEGER,
                fare_stage_marker_count INTEGER,
                gtfs_route_key_matches INTEGER,
                method_note VARCHAR
            )
        """)
        con.execute("INSERT INTO dtc_fare_stage_import_metadata VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            datetime.now(UTC), xlsx_path.name, _sha256(xlsx_path),
            len({row[0] for row in rows}), len({row[1] for row in rows}),
            len(rows), sum(bool(row[5]) for row in rows),
            len(matched_keys),
            "GTFS route-name matching is a candidate only; stop crosswalk is resolved conservatively at estimate time.",
        ])
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()

    report = {
        "status": "imported",
        "imported_at_utc": datetime.now(UTC).isoformat(),
        "source_file": xlsx_path.name,
        "source_sha256": _sha256(xlsx_path),
        "distinct_route_label_count": len({row[0] for row in rows}),
        "unique_route_key_count": len({row[1] for row in rows}),
        "stop_row_count": len(rows),
        "fare_stage_marker_count": sum(bool(row[5]) for row in rows),
        "gtfs_route_key_matches": len(matched_keys),
        "note": "Workbook provides stage locations, not fares. Fare amounts are estimated from published ordinary/AC distance bands.",
    }
    report_path = report_path.resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Import DTC route fare-stage points into Yuktix v2.")
    parser.add_argument("--xlsx", type=Path, default=FARE_STAGES_PATH)
    parser.add_argument("--database", type=Path, default=DATABASE_PATH)
    parser.add_argument("--report", type=Path, default=FARE_STAGE_IMPORT_REPORT_PATH)
    args = parser.parse_args()
    print(json.dumps(import_fare_stages(xlsx_path=args.xlsx, database_path=args.database, report_path=args.report), indent=2))


if __name__ == "__main__":
    main()
