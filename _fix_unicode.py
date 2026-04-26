"""
Fix: replace all Unicode non-ASCII characters in load_cbi_bonds.py
with safe ASCII equivalents so the command works on Windows cp1252.
"""
import re

path = r"c:\Users\sharu\OneDrive\Sharun\sharun\Web Application\GreenLens\data_ingestion\management\commands\load_cbi_bonds.py"

with open(path, encoding="utf-8") as f:
    text = f.read()

# Replace specific Unicode characters with ASCII
replacements = {
    "\u2500": "-",    # ─  (box horizontal)
    "\u2502": "|",    # │  (box vertical)
    "\u2514": "+",    # └  (box corner)
    "\u2518": "+",    # ┘  (box corner)
    "\u250c": "+",    # ┌  (box corner)
    "\u2510": "+",    # ┐  (box corner)
    "\u251c": "+",    # ├  (box T)
    "\u2524": "+",    # ┤  (box T)
    "\u252c": "+",    # ┬  (box T)
    "\u2534": "+",    # ┴  (box T)
    "\u253c": "+",    # ┼  (box cross)
    "\u2014": "--",   # —  (em dash)
    "\u2013": "-",    # –  (en dash)
    "\u2192": "->",   # →  (arrow)
    "\u2190": "<-",   # ←  (arrow)
    "\u00e9": "e",    # é  (e with accent)
    "\u00ee": "i",    # î
    "\u00f4": "o",    # ô
    "\u00e8": "e",    # è
    "\u00ea": "e",    # ê
    "\u00e0": "a",    # à
    "\u00e2": "a",    # â
    "\u00fc": "u",    # ü
    "\u00f6": "o",    # ö
    "\u00e4": "a",    # ä
    "\u00fb": "u",    # û
    "\u00e7": "c",    # ç
    "\ufffd": "?",    # replacement character
}

for uni_char, ascii_replacement in replacements.items():
    text = text.replace(uni_char, ascii_replacement)

# Verify no non-ASCII chars remain
remaining = [(i, c, ord(c)) for i, c in enumerate(text) if ord(c) > 127]
if remaining:
    print(f"WARNING: {len(remaining)} non-ASCII chars still remain:")
    for pos, char, code in remaining[:20]:
        # Find line number
        line_num = text[:pos].count('\n') + 1
        print(f"  Line {line_num}: U+{code:04X} ({repr(char)})")
else:
    print("All non-ASCII characters replaced successfully.")

with open(path, "w", encoding="utf-8") as f:
    f.write(text)

print(f"File saved: {path}")

# Quick verification - try encoding with cp1252 (Windows default)
try:
    text.encode("cp1252")
    print("Verification: File is safe to use on Windows (cp1252 compatible).")
except UnicodeEncodeError as e:
    print(f"WARNING: Still has cp1252-incompatible chars: {e}")
