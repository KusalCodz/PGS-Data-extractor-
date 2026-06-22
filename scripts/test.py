import pdfplumber
import pandas as pd
import os
import re
import json

# -----------------------------
# CONFIG
# -----------------------------
INPUT_FOLDER = r"D:\PGS Analysis"
OUTPUT_CSV = "combined_output.csv"
OUTPUT_JSON = "combined_output.json"


# -----------------------------
# CLEAN TEXT
# -----------------------------
def clean_text(text):
    if not text:
        return None
    return re.sub(r"\s+", " ", text).strip()

# -----------------------------
# EXISTING TABLE EXTRACTION (UNCHANGED LOGIC)
# -----------------------------
def extract_tables_from_pdf(pdf_path):
    rows = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables()

            for table in tables:
                if not table:
                    continue

                header = [clean_text(h) for h in table[0]]

                for row in table[1:]:
                    if not row:
                        continue

                    row_dict = dict(zip(header, row))
                    rows.append(row_dict)

    return rows

# -----------------------------
# NEW: COMMON DETAILS EXTRACTION (DOB, Clinic, etc.)
# -----------------------------
def extract_common_details(pdf_path):
    details = {
        "Patient Name": None,
        "Birth Date": None,
        "IVF Clinic": None,
        "Referred By": None,
        "Specimen Type": None,
        "Sample Received": None,
        "Date Reported": None,
        "Date Biopsied": None
    }

    patterns = {
        "Patient Name": r"(Patient Name|Name)\s*[:\-]\s*(.+)",
        "Birth Date": r"(Date of Birth|DOB|Birth Date)\s*[:\-]\s*(.+)",
        "IVF Clinic": r"(IVF Clinic|Clinic)\s*[:\-]\s*(.+)",
        "Referred By": r"(Referred By|Ref By)\s*[:\-]\s*(.+)",
        "Specimen Type": r"(Specimen Type)\s*[:\-]\s*(.+)",
        "Sample Received": r"(Sample Received)\s*[:\-]\s*(.+)",
        "Date Reported": r"(Date Reported)\s*[:\-]\s*(.+)",
        "Date Biopsied": r"(Date Biopsied)\s*[:\-]\s*(.+)"
    }

    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""

        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += "\n" + text

    for key, pattern in patterns.items():
        match = re.search(pattern, full_text, re.IGNORECASE)
        if match:
            details[key] = clean_text(match.group(2))

    return details

# -----------------------------
# MERGE TABLE + METADATA
# -----------------------------
def merge_data(table_rows, common_details, source_file):
    merged = []

    for row in table_rows:
        new_row = {"Source File": source_file}

        # add table data
        for k, v in row.items():
            new_row[k] = v

        # add common metadata (same for all rows in file)
        for k, v in common_details.items():
            new_row[k] = v

        merged.append(new_row)

    return merged

# -----------------------------
# PROCESS SINGLE FILE
# -----------------------------
def process_pdf(pdf_path):
    table_rows = extract_tables_from_pdf(pdf_path)
    common_details = extract_common_details(pdf_path)

    return merge_data(table_rows, common_details, os.path.basename(pdf_path))

# -----------------------------
# PROCESS FOLDER
# -----------------------------
def process_folder(folder_path):
    all_data = []

    pdf_files = [f for f in os.listdir(folder_path) if f.lower().endswith(".pdf")]

    print(f"Found {len(pdf_files)} PDFs")

    for pdf_file in pdf_files:
        path = os.path.join(folder_path, pdf_file)

        print(f"Processing: {pdf_file}")

        try:
            data = process_pdf(path)
            all_data.extend(data)

        except Exception as e:
            print(f"Error in {pdf_file}: {e}")

    return all_data

# -----------------------------
# MAIN
# -----------------------------
def main():
    data = process_folder(INPUT_FOLDER)

    df = pd.DataFrame(data)

    df.to_csv(OUTPUT_CSV, index=False)

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print("\nDONE")
    print(f"Total rows: {len(data)}")
    print(f"CSV: {OUTPUT_CSV}")
    print(f"JSON: {OUTPUT_JSON}")

# -----------------------------
# RUN
# -----------------------------
if __name__ == "__main__":
    main()