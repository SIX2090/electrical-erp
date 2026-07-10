from pathlib import Path
from datetime import datetime
import csv
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG = ROOT / "release" / "trial_run" / "trial_run_issue_log.csv"

VALID_YES_NO = {"是", "否"}
VALID_STATUS = {"未处理", "处理中", "已处理", "暂缓"}
VALID_ROLES = {"销售/项目", "计划/采购", "仓库", "生产", "售后", "财务", "管理员"}
VALID_STAGES = {"销售", "BOM", "采购", "委外", "仓库", "生产", "发货", "售后", "财务", "成本"}

REQUIRED_FIELDS = [
    "编号",
    "发现时间",
    "岗位",
    "账号",
    "页面",
    "项目号",
    "柜号",
    "问题描述",
    "是否阻断",
    "责任归口",
    "处理状态",
]


def blank(value):
    return not (value or "").strip()


def check_datetime(value, field, errors, row_no):
    if blank(value):
        return
    try:
        datetime.strptime(value.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        errors.append(f"第{row_no}行 {field}: 时间格式应为 YYYY-MM-DD HH:MM")


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_LOG
    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig")))
    errors = []
    warnings = []
    open_blockers = 0
    seen_ids = set()

    for index, row in enumerate(rows, start=2):
        if all(blank(value) for value in row.values()):
            continue
        issue_id = (row.get("编号") or "").strip()
        if issue_id in seen_ids:
            errors.append(f"第{index}行 编号: 重复编号 {issue_id}")
        if issue_id:
            seen_ids.add(issue_id)
        for field in REQUIRED_FIELDS:
            if blank(row.get(field)):
                errors.append(f"第{index}行 {field}: 必填未填写")
        check_datetime(row.get("发现时间"), "发现时间", errors, index)
        check_datetime(row.get("关闭时间"), "关闭时间", errors, index)

        role = (row.get("岗位") or "").strip()
        if role and role not in VALID_ROLES:
            errors.append(f"第{index}行 岗位: 不在允许范围")
        yes_no = (row.get("是否阻断") or "").strip()
        if yes_no and yes_no not in VALID_YES_NO:
            errors.append(f"第{index}行 是否阻断: 只能填写 是 或 否")
        stage = (row.get("阻断环节") or "").strip()
        if stage and stage not in VALID_STAGES:
            errors.append(f"第{index}行 阻断环节: 不在允许范围")
        status = (row.get("处理状态") or "").strip()
        if status and status not in VALID_STATUS:
            errors.append(f"第{index}行 处理状态: 不在允许范围")
        if yes_no == "是" and blank(stage):
            errors.append(f"第{index}行 阻断环节: 阻断问题必须填写")
        if status == "已处理" and blank(row.get("处理结果")):
            errors.append(f"第{index}行 处理结果: 已处理问题必须填写处理结果")
        if status == "已处理" and blank(row.get("关闭时间")):
            warnings.append(f"第{index}行 关闭时间: 已处理问题建议填写关闭时间")
        if yes_no == "是" and status != "已处理":
            open_blockers += 1

    print(f"issue_log={path}")
    print(f"rows={len(rows)} errors={len(errors)} warnings={len(warnings)} open_blockers={open_blockers}")
    for item in errors:
        print(f"error | {item}")
    for item in warnings:
        print(f"warning | {item}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
