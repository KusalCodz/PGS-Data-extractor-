import os
import re
import pdfplumber
import pandas as pd

# =====================================================
# Folder containing PDFs
# =====================================================

pdf_folder = r"D:\PGS Analysis"

# =====================================================
# Store all extracted rows
# =====================================================

all_rows = []

# =====================================================
# Process every PDF
# =====================================================

for filename in os.listdir(pdf_folder):

    if not filename.lower().endswith(".pdf"):
        continue

    pdf_path = os.path.join(pdf_folder, filename)

    print(f"Processing {filename}")

    try:

        # --------------------------------------------
        # Read complete text
        # --------------------------------------------

        text = ""

        with pdfplumber.open(pdf_path) as pdf:

            for page in pdf.pages:

                page_text = page.extract_text()

                if page_text:
                    text += page_text + "\n"

        # --------------------------------------------
        # Metadata
        # --------------------------------------------

        patient_name = None
        lab_id = None
        dob = None

        m = re.search(
            r"Patient Name:\s*(.*?)\s+Lab ID:",
            text,
            re.DOTALL,
        )

        if m:
            patient_name = m.group(1).strip()

        m = re.search(
            r"Lab ID:\s*([A-Za-z0-9]+)",
            text,
        )

        if m:
            lab_id = m.group(1).strip()

        m = re.search(
            r"Date of Birth:\s*(\d{2}/\d{2}/\d{4})",
            text,
        )

        if m:
            dob = m.group(1)

        # --------------------------------------------
        # Extract table
        # --------------------------------------------

        lines = text.splitlines()

        inside_table = False

        for line in lines:

            line = line.strip()

            # Start of table

            if line == "Results":
                inside_table = True
                continue

            if not inside_table:
                continue

            # Skip header

            if line.startswith("Embryo ID"):
                continue

            # End of table

            if (
                line.startswith("Comments")
                or line.startswith("Interpretation")
                or line.startswith("Page")
                or line == ""
            ):
                break

            # ----------------------------------------
            # Expect last token = Yes/No
            # ----------------------------------------

            if not (
                line.endswith("Yes")
                or line.endswith("No")
            ):
                continue

            try:

                left, transfer = line.rsplit(" ", 1)

                left, gender = left.rsplit(" ", 1)

                # first two tokens = embryo ID

                tokens = left.split()

                if len(tokens) < 3:
                    continue

                embryo_id = " ".join(tokens[:2])

                result = " ".join(tokens[2:])

                all_rows.append({

                    "PDF": filename,

                    "Patient Name": patient_name,

                    "Lab ID": lab_id,

                    "Date of Birth": dob,

                    "Embryo ID": embryo_id,

                    "Result": result,

                    "Gender": gender,

                    "Recommended for Transfer": transfer,

                })

            except Exception:

                print("Could not parse:", line)

    except Exception as e:

        print(f"Error processing {filename}")

        print(e)

# =====================================================
# Create dataframe
# =====================================================

df = pd.DataFrame(all_rows)

print(df)

# =====================================================
# Save
# =====================================================

output_file = os.path.join(pdf_folder, "PGS_Results.csv")

df.to_csv(output_file, index=False)

print("\nDone!")

print(output_file)