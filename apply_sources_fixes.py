"""Áp dụng 4 sửa lỗi cơ chế vào code (tương đương source_fixes.patch, nhưng không phụ thuộc CRLF/LF).

Chạy từ thư mục gốc repo:   python apply_source_fixes.py
- Chạy lại nhiều lần an toàn (đã áp rồi thì bỏ qua).
- Nếu một mẫu không khớp (file local khác bản GitHub) -> dừng và báo rõ, KHÔNG ghi file dở dang.
"""
import re
import sys
from pathlib import Path

CALC = Path("python/calculations")


def read(p):
    return p.read_text(encoding="utf-8")


def must_replace(text, old, new, label):
    if old not in text:
        sys.exit(f"[DỪNG] Không tìm thấy mẫu: {label}. File local khác bản dự kiến, hãy gửi lại đoạn code đó.")
    return text.replace(old, new, 1)


def must_sub(text, pattern, repl, label, min_count=1):
    text, n = re.subn(pattern, repl, text)
    if n < min_count:
        sys.exit(f"[DỪNG] Mẫu regex chỉ khớp {n} lần (cần >= {min_count}): {label}")
    return text, n


results = {}

# ---------------- type_calc.py ----------------
p = CALC / "type_calc.py"
s = read(p)
if "def normalize_ability_name" in s:
    print("type_calc.py: đã áp dụng trước đó, bỏ qua")
else:
    s = must_replace(s, '    "well-baked-body": ["fire"],\n    "wind-rider": ["flying"]\n}',
                     '    "well-baked-body": ["fire"]\n}', "wind-rider")
    s = must_replace(s, "# BASE TYPE LOOKUP", '''def normalize_ability_name(ability):
    """'Flash Fire' / 'flash fire' / 'flash_fire' -> 'flash-fire' (slug dùng trong các bảng bên trên)."""
    return str(ability or "").strip().lower().replace(" ", "-").replace("_", "-")


# BASE TYPE LOOKUP''', "BASE TYPE LOOKUP marker")
    a, b = s.find("def get_actual_move_type"), s.find("# SCRAPPY")
    if a < 0 or b < a:
        sys.exit("[DỪNG] Không xác định được hàm get_actual_move_type")
    s = s[:a] + '''def get_actual_move_type(attacker,move):
    move_type = (
        move["type"]
        .lower()
    )
    ability = normalize_ability_name(attacker["ability"])

    # Normalize đổi MỌI move thành Normal
    if ability == "normalize":
        return "normal"

    # -ate abilities chỉ đổi move vốn là Normal
    if (move_type == "normal"
        and
        ability in OFFENSIVE_TYPE_OVERRIDE):
        return OFFENSIVE_TYPE_OVERRIDE[ability]
    return move_type

''' + s[b:]
    s, n = must_sub(s, r'(attacker|defender)\["ability"\]\s*\.lower\(\)', r'normalize_ability_name(\1["ability"])',
                    "đọc ability trong type_calc", min_count=4)
    results[p] = s
    print(f"type_calc.py: chuẩn hóa {n} chỗ đọc ability")

# ---------------- type_v2.py ----------------
p = CALC / "type_v2.py"
s = read(p)
if "normalize_ability_name" in s:
    print("type_v2.py: đã áp dụng trước đó, bỏ qua")
else:
    a = s.find("# =====================================================\n# DEFENSIVE ABILITIES")
    b = s.find("OFFENSIVE_TYPE_OVERRIDE")
    b = s.find("}\n", b) + 2 if b >= 0 else -1
    if a < 0 or b < a:
        sys.exit("[DỪNG] Không xác định được khối hằng số ability trong type_v2.py")
    s = s[:a] + '''from python.calculations.type_calc import (
    DEFENSIVE_ABILITY_IMMUNITIES,
    DEFENSIVE_ABILITY_RESISTANCES,
    OFFENSIVE_TYPE_OVERRIDE,
    normalize_ability_name,
)
''' + s[b:]
    s, n1 = must_sub(s, r'ability = \(\s*defender\s*\.get\("ability", ""\)\s*\.lower\(\)\s*\)',
                     'ability = normalize_ability_name(defender.get("ability", ""))', "defender ability trong type_v2")
    s, n2 = must_sub(s, r'ability = \(\s*pokemon\s*\.get\(\s*"ability",\s*""\s*\)\s*\.lower\(\)\s*\)',
                     'ability = normalize_ability_name(pokemon.get("ability", ""))', "pokemon ability trong type_v2")
    results[p] = s
    print("type_v2.py: dùng chung hằng số + chuẩn hóa tên ability")

# ---------------- damage_calc_v2.py ----------------
p = CALC / "damage_calc_v2.py"
s = read(p)
if "get_actual_move_type" in s:
    print("damage_calc_v2.py: đã áp dụng trước đó, bỏ qua")
else:
    s = must_sub(s, r"from python\.calculations\.type_calc import \(\s*calculate_type_multiplier\s*\)",
                 "from python.calculations.type_calc import (\n    calculate_type_multiplier,\n    get_actual_move_type\n)",
                 "import type_calc trong damage_calc_v2")[0]
    s = must_sub(s, r"stab_modifier = get_stab_modifier\(\s*attacker,\s*move\s*\)",
                 'stab_modifier = get_stab_modifier(\n        attacker,\n        {**move, "type": get_actual_move_type(attacker, move)}\n    )',
                 "lời gọi get_stab_modifier")[0]
    results[p] = s
    print("damage_calc_v2.py: STAB theo hệ move sau khi ability đổi hệ")

# ---------------- team_synergy.py ----------------
p = CALC / "team_synergy.py"
s = read(p)
if "from python.calculations.role_label" in s:
    print("team_synergy.py: đã áp dụng trước đó, bỏ qua")
else:
    results[p] = must_replace(s, "from calculations.role_label import", "from python.calculations.role_label import", "import role_label")
    print("team_synergy.py: sửa prefix import")

# Chỉ ghi file khi TẤT CẢ mẫu đã khớp
for path, text in results.items():
    path.write_text(text, encoding="utf-8")
print("Xong." if results else "Không có gì để thay đổi.")