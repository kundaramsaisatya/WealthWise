from excel_extractor import extract_excel

file_path = "sample.xlsx"

data = extract_excel(file_path)

for sheet, rows in data.items():
    print(f"\nSheet: {sheet}")
    print(f"Total rows: {len(rows)}")
    print(rows[:3])