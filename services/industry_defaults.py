DEFAULT_UNITS = [
    {"code": "PCS", "name": "件", "category": "count", "conversion_rate": 1, "remark": "元器件、零件常用单位"},
    {"code": "SET", "name": "套", "category": "count", "conversion_rate": 1, "remark": "成套设备、组件常用单位"},
    {"code": "UNIT", "name": "台", "category": "count", "conversion_rate": 1, "remark": "柜体、设备常用单位"},
    {"code": "M", "name": "米", "category": "length", "conversion_rate": 1, "remark": "线缆、母排、型材常用单位"},
    {"code": "KG", "name": "公斤", "category": "weight", "conversion_rate": 1, "remark": "铜排、钢材、铜缆常用单位"},
    {"code": "ROLL", "name": "卷", "category": "count", "conversion_rate": 1, "remark": "导线、热缩管、扎带等卷装材料"},
    {"code": "M2", "name": "平方米", "category": "area", "conversion_rate": 1, "remark": "板材、绝缘材料常用单位"},
    {"code": "PCS_PAIR", "name": "对", "category": "count", "conversion_rate": 1, "remark": "触头、接插件等成对使用的物料"},
]


def seed_default_units(execute_db):
    count = 0
    for unit in DEFAULT_UNITS:
        execute_db(
            """
            INSERT INTO units (code, name, category, conversion_rate, remark)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (code) DO UPDATE SET
                name = EXCLUDED.name,
                category = EXCLUDED.category,
                conversion_rate = EXCLUDED.conversion_rate,
                remark = EXCLUDED.remark
            """,
            (unit["code"], unit["name"], unit["category"], unit["conversion_rate"], unit["remark"]),
        )
        count += 1
    return count
