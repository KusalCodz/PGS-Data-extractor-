"""
parse_pgt_results.py
--------------------
Reads an input CSV that contains a 'results' column with PGT-A result strings
and appends one binary column per chromosomal event (1 = present, 0 = absent).

Usage:
    python parse_pgt_results.py input.csv output.csv

The script expects the input CSV to have a column named 'results' (case-insensitive).
All other columns are preserved as-is.
"""

import sys
import re
import pandas as pd

# ---------------------------------------------------------------------------
# Column definitions
# ---------------------------------------------------------------------------

AUTOSOMES = list(range(1, 23))          # 1–22
SEX_CHROMS = ["X", "Y"]

WHOLE_COLS = []
for c in AUTOSOMES:
    WHOLE_COLS += [f"{c}_monosomy", f"{c}_trisomy"]

ARM_COLS = []
for c in AUTOSOMES:
    for arm in ("p", "q"):
        for direction in ("gain", "loss"):
            ARM_COLS.append(f"{c}{arm}_{direction}")

MOSAIC_COLS = []
for c in AUTOSOMES:
    MOSAIC_COLS += [f"{c}mosaic_gain", f"{c}mosaic_loss"]

EXTRA_COLS = ["sex_of_embryo"]

ALL_COLS = WHOLE_COLS + ARM_COLS + MOSAIC_COLS + EXTRA_COLS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_mosaic(token: str) -> bool:
    return bool(re.search(r'\bmos(aic)?\b', token, re.IGNORECASE))


def _parse_chrom(raw: str):
    """
    Convert a raw chromosome string such as '22', 'Xq', '5p', '9q-partial'
    into (chrom_number_or_letter, arm_or_None).

    Returns (chrom, arm) where chrom is an int 1-22 or a string 'X'/'Y',
    and arm is 'p', 'q', or None (whole chromosome).
    """
    raw = raw.strip()

    # Strip qualifiers like '-partial', '(partial)', '(distal)', '(proximal)',
    # '(terminal)', 'segmental', '(segmental)', etc.
    raw = re.sub(
        r'[\s\-]*(partial|distal|proximal|terminal|segmental)', '', raw, flags=re.IGNORECASE
    )
    raw = raw.strip("() ")

    # Match optional leading sign (+/-), optional chromosome number/letter, optional arm
    m = re.match(r'^[+\-]?(\d+|X|Y)([pq])?', raw, re.IGNORECASE)
    if not m:
        return None, None

    chrom_raw = m.group(1)
    arm = m.group(2).lower() if m.group(2) else None

    try:
        chrom = int(chrom_raw)
    except ValueError:
        chrom = chrom_raw.upper()   # 'X' or 'Y'

    return chrom, arm


def _set(row: dict, col: str, value=1):
    if col in row:
        row[col] = value


def parse_result(result_str: str) -> dict:
    """
    Parse a single result string and return a dict mapping column → value.
    All columns default to 0; only detected events are set to 1.
    sex_of_embryo is set to XX, XY, XO, XXY, etc. when detectable.
    """
    row = {col: 0 for col in ALL_COLS}
    row["sex_of_embryo"] = ""

    if not isinstance(result_str, str):
        return row

    text = result_str.strip()

    # Early exits for non-informative results
    if re.match(
        r'^(Normal|Insufficient\s+data|Inconclusive|Indeterminate|Chaotic|chaotic)',
        text, re.IGNORECASE
    ):
        # Still try to detect sex from "Normal (low confidence)" etc. — unlikely but harmless
        pass

    # -----------------------------------------------------------------------
    # Sex chromosome calls
    # -----------------------------------------------------------------------
    sex_patterns = [
        (r'\bXO\b', 'XO'),
        (r'\bXXY\b', 'XXY'),
        (r'\bXYY\b', 'XYY'),
        (r'\bXX\s*/\s*XY\b', 'XX/XY mosaic'),
        (r'\bXY\s*/\s*XO\b', 'XY/XO mosaic'),
        (r'\bXO\s*/\s*XY\b', 'XO/XY mosaic'),
        (r'\bXX\b', 'XX'),
        (r'\bXY\b', 'XY'),
    ]
    for pattern, label in sex_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            row["sex_of_embryo"] = label
            break

    # -----------------------------------------------------------------------
    # Only parse chromosomal aberrations if the result is Abnormal
    # -----------------------------------------------------------------------
    if not re.search(r'\bAbnormal\b', text, re.IGNORECASE):
        return row

    # Remove the leading "Abnormal:" prefix and qualifiers like "low confidence"
    body = re.sub(r'^Abnormal\s*:\s*', '', text, flags=re.IGNORECASE)
    body = re.sub(r'\(low\s+confidence\)', '', body, flags=re.IGNORECASE)
    body = re.sub(r'low\s+confidence', '', body, flags=re.IGNORECASE)

    # Handle special named abnormalities
    if re.search(r'\bchaotic\b', body, re.IGNORECASE):
        return row  # chaotic – no specific chromosome columns to fill
    if re.search(r'\bhyperdiploid\b', body, re.IGNORECASE):
        return row

    # Isochromosome: e.g. "Isochromosome 1p", "Isochromosome 5 (+5p, -5q)"
    iso_match = re.search(r'[Ii]sochromosome\s+(\d+)([pq])?', body)
    if iso_match:
        c = int(iso_match.group(1))
        arm = iso_match.group(2)
        if arm:
            gain_col = f"{c}{arm}_gain"
            loss_col = f"{c}{'q' if arm == 'p' else 'p'}_loss"
            _set(row, gain_col)
            _set(row, loss_col)
        # Don't return – there may be additional aberrations listed after

    # -----------------------------------------------------------------------
    # Detect "Both Mosaic" / "All Mosaic" qualifiers that apply to all items
    # e.g. "-11, +20 (Both Mosaic)"  ->  all items in this result are mosaic
    # -----------------------------------------------------------------------
    global_mosaic = bool(re.search(r'\b(both|all)\s+mos(aic)?\b', body, re.IGNORECASE))

    # -----------------------------------------------------------------------
    # Tokenise: split on comma, then parse each token
    # -----------------------------------------------------------------------
    # First, normalise spacing around commas
    body = re.sub(r'\s*,\s*', ',', body)

    # Split into tokens on commas (but not inside parentheses)
    tokens = re.split(r',(?![^(]*\))', body)

    for tok in tokens:
        tok = tok.strip()
        if not tok:
            continue

        mosaic = global_mosaic or _is_mosaic(tok)

        # Find all chromosome references in this token
        # e.g. "+22", "-5q", "+Xq", "-3q(partial)", "XO", "XX/XY"
        chrom_refs = re.findall(
            r'([+\-])(\d+|X|Y)([pq])?(?:\s*[\(\-](?:partial|distal|proximal|terminal|segmental)[^,)]*\))?',
            tok, re.IGNORECASE
        )

        for sign, chrom_raw, arm_raw in chrom_refs:
            gain = sign == '+'

            try:
                chrom = int(chrom_raw)
            except ValueError:
                chrom = chrom_raw.upper()

            arm = arm_raw.lower() if arm_raw else None

            if isinstance(chrom, str):
                # Sex chromosome gain/loss — captured in sex_of_embryo only
                # e.g. +X, -X, +Xq, -Xq, +Y
                # Already handled above; skip column filling
                continue

            if not (1 <= chrom <= 22):
                continue

            if mosaic:
                # Fill mosaic columns
                if gain:
                    _set(row, f"{chrom}mosaic_gain")
                else:
                    _set(row, f"{chrom}mosaic_loss")
            elif arm:
                # Segmental arm event
                direction = "gain" if gain else "loss"
                _set(row, f"{chrom}{arm}_{direction}")
            else:
                # Whole chromosome
                if gain:
                    _set(row, f"{chrom}_trisomy")
                else:
                    _set(row, f"{chrom}_monosomy")

    return row


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        print("Usage: python parse_pgt_results.py input.csv output.csv")
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2]

    df = pd.read_csv(input_path)

    # Locate the results column (case-insensitive)
    result_col = None
    for col in df.columns:
        if col.strip().lower() == "results":
            result_col = col
            break

    if result_col is None:
        raise ValueError(
            f"No 'results' column found. Available columns: {list(df.columns)}"
        )

    print(f"Found results column: '{result_col}' | Rows: {len(df)}")

    # Parse each result
    parsed_rows = df[result_col].apply(parse_result)
    parsed_df = pd.DataFrame(list(parsed_rows))

    # Concatenate original columns + new columns
    out_df = pd.concat([df.reset_index(drop=True), parsed_df], axis=1)

    out_df.to_csv(output_path, index=False)
    print(f"Done. Output written to: {output_path}")

    # Quick summary
    total = len(out_df)
    for col in ALL_COLS:
        n = out_df[col].sum() if col != "sex_of_embryo" else (out_df[col] != "").sum()
        if n > 0:
            print(f"  {col}: {n}/{total}")


if __name__ == "__main__":
    main()