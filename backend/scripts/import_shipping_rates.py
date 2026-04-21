"""Import LCL해운 + 해운(자가) shipping rate tables.

The upstream "xls" files are actually HTML tables (Excel-compatible
MIME). They look like::

    <tr><td>무게</td><td>일반셀러</td><td>슈퍼셀러</td><td>협력사</td></tr>
    <tr><td>~ 0.50</td><td>47,500</td><td>47,500</td><td>47,500</td></tr>
    ...

Usage::

    cd backend
    .venv/bin/python -m scripts.import_shipping_rates \\
        --lcl  /path/to/LCL해운.xls \\
        --sea  /path/to/해운\\(자가\\).xls
"""
from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal
from pathlib import Path

from bs4 import BeautifulSoup
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.session import SessionLocal
from app.models import InternationalShippingRate


_MONEY_RE = re.compile(r"[^\d]")
_WEIGHT_RE = re.compile(r"([\d.]+)")


def _money(text: str) -> int | None:
    stripped = _MONEY_RE.sub("", text or "")
    return int(stripped) if stripped else None


def _weight(text: str) -> Decimal | None:
    m = _WEIGHT_RE.search(text or "")
    if not m:
        return None
    try:
        return Decimal(m.group(1))
    except Exception:
        return None


def _parse_file(path: Path, method: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        soup = BeautifulSoup(f.read(), "lxml")
    rows: list[dict] = []
    for tbl in soup.find_all("table"):
        for tr in tbl.find_all("tr"):
            cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
            if len(cells) < 4:
                continue
            if cells[0] in ("무게", "LCL해운", "해운(자가장치장)", "해운(자가)"):
                continue
            max_w = _weight(cells[0])
            general = _money(cells[1])
            super_s = _money(cells[2])
            partner = _money(cells[3])
            if max_w is None or general is None or super_s is None or partner is None:
                continue
            rows.append(
                {
                    "method": method,
                    "max_weight_kg": max_w,
                    "general_seller_krw": general,
                    "super_seller_krw": super_s,
                    "partner_krw": partner,
                }
            )
    return rows


def _flush(session, batch: list[dict]) -> int:
    if not batch:
        return 0
    stmt = pg_insert(InternationalShippingRate).values(batch)
    stmt = stmt.on_conflict_do_update(
        constraint="shipping_rate_unique_method_weight",
        set_={
            "general_seller_krw": stmt.excluded.general_seller_krw,
            "super_seller_krw": stmt.excluded.super_seller_krw,
            "partner_krw": stmt.excluded.partner_krw,
        },
    )
    session.execute(stmt)
    return len(batch)


def import_files(lcl: Path, sea: Path) -> dict[str, int]:
    lcl_rows = _parse_file(lcl, "lcl")
    sea_rows = _parse_file(sea, "sea_self")

    session = SessionLocal()
    try:
        total = 0
        for batch in (lcl_rows, sea_rows):
            for i in range(0, len(batch), 500):
                total += _flush(session, batch[i : i + 500])
        session.commit()
    finally:
        session.close()

    return {"lcl_rows": len(lcl_rows), "sea_rows": len(sea_rows), "upserted": total}


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lcl", required=True, type=Path)
    parser.add_argument("--sea", required=True, type=Path)
    args = parser.parse_args(argv)

    for p in (args.lcl, args.sea):
        if not p.exists():
            raise SystemExit(f"file not found: {p}")

    result = import_files(args.lcl, args.sea)
    print(f"LCL rows:     {result['lcl_rows']:,}")
    print(f"Sea rows:     {result['sea_rows']:,}")
    print(f"upserted:     {result['upserted']:,}")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
