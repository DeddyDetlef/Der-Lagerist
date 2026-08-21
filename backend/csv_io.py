import csv
import io
from typing import List, Dict, Any

CSV_COLUMNS = ['code', 'name', 'category', 'description', 'location', 'quantity', 'unit']


def export_csv(items: List[Dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS, extrasaction='ignore')
    writer.writeheader()
    for item in items:
        row = {k: item.get(k, '') for k in CSV_COLUMNS}
        writer.writerow(row)
    return output.getvalue()


async def import_csv(db, content: str) -> List[Dict[str, Any]]:
    from .database import upsert_item

    reader = csv.DictReader(io.StringIO(content))
    imported = []
    for row in reader:
        code = row.get('code', '').strip()
        if not code:
            continue
        data = {k: row.get(k, '') for k in CSV_COLUMNS[1:]}
        try:
            data['quantity'] = float(data['quantity']) if data['quantity'] else 0
        except ValueError:
            data['quantity'] = 0
        result = await upsert_item(db, code, data)
        if result:
            imported.append(result)
    return imported
