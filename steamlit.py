import streamlit as st
import pandas as pd
from io import BytesIO
import zipfile
import datetime
import pdfrw

class PDFFormFiller:
    def __init__(self):
        self.ANNOT_KEY = '/Annots'
        self.ANNOT_FIELD_KEY = '/T'
        self.ANNOT_FORM_KEY = '/FT'
        self.ANNOT_FORM_TEXT = '/Tx'
        self.ANNOT_FORM_BUTTON = '/Btn'
        self.SUBTYPE_KEY = '/Subtype'
        self.WIDGET_SUBTYPE_KEY = '/Widget'

    def upload_files(self):
        uploaded_excel = st.file_uploader("Upload Excel File", type=["xlsx", "xls"])
        if uploaded_excel:
            try:
                self.excel_data = pd.read_excel(uploaded_excel)
                st.success(f"Excel file uploaded: {uploaded_excel.name}")
            except Exception as e:
                st.error(f"Error reading Excel file: {e}")

        uploaded_pdf = st.file_uploader("Upload PDF Template", type="pdf")
        if uploaded_pdf:
            try:
                self.pdf_template_bytes = uploaded_pdf.read()
                self.pdf_template = pdfrw.PdfReader(BytesIO(self.pdf_template_bytes))
                st.success(f"PDF template uploaded: {uploaded_pdf.name}")
                self.print_pdf_fields()
            except Exception as e:
                st.error(f"Error reading PDF template: {e}")

    def print_pdf_fields(self):
        if self.pdf_template:
            fields = set()
            for page in self.pdf_template.pages:
                if page[self.ANNOT_KEY]:
                    for annotation in page[self.ANNOT_KEY]:
                        if annotation[self.ANNOT_FIELD_KEY]:
                            if annotation[self.SUBTYPE_KEY] == self.WIDGET_SUBTYPE_KEY:
                                key = annotation[self.ANNOT_FIELD_KEY][1:-1]
                                fields.add(key)
            st.write("PDF form fields found:")
            st.write(", ".join(sorted(fields)))

            if self.excel_data is not None:
                st.write("\nExcel columns found:")
                st.write(", ".join(self.excel_data.columns))

    def fill_pdf_form(self, row_data):
        template = pdfrw.PdfReader(BytesIO(self.pdf_template_bytes))
        for page in template.pages:
            if page[self.ANNOT_KEY]:
                for annotation in page[self.ANNOT_KEY]:
                    if annotation[self.ANNOT_FIELD_KEY]:
                        if annotation[self.SUBTYPE_KEY] == self.WIDGET_SUBTYPE_KEY:
                            key = annotation[self.ANNOT_FIELD_KEY][1:-1]
                            if key in row_data:
                                field_value = str(row_data[key])
                                if pd.isna(field_value) or field_value.lower() == 'nan':
                                    field_value = ''

                                if annotation[self.ANNOT_FORM_KEY] == self.ANNOT_FORM_TEXT:
                                    annotation.update(pdfrw.PdfDict(V=field_value, AP=field_value))
                                elif annotation[self.ANNOT_FORM_KEY] == self.ANNOT_FORM_BUTTON:
                                    annotation.update(pdfrw.PdfDict(V=pdfrw.PdfName(field_value), AS=pdfrw.PdfName(field_value)))
                annotation.update(pdfrw.PdfDict(Ff=1))
        template.Root.AcroForm.update(pdfrw.PdfDict(NeedAppearances=pdfrw.PdfObject('true')))
        return template

    def process_all_records(self):
        if self.excel_data is None or self.pdf_template is None:
            st.error("Please upload both Excel file and PDF template.")
            return

        # Ensure the 'Account number' column exists in the Excel file
        if 'Account number' not in self.excel_data.columns:
            st.error("The Excel file must contain a column named 'Account number'.")
            return

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"filled_forms_{timestamp}.zip"

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            successful_count = 0
            failed_count = 0

            for index, row in self.excel_data.iterrows():
                try:
                    # Use 'Account number' as the filename identifier
                    account_number = row['Account number']
                    if pd.isna(account_number):
                        st.warning(f"Missing 'Account number' for row {index + 1}. Skipping.")
                        failed_count += 1
                        continue

                    pdf_filename = f"{account_number}.pdf"
                    filled_pdf = self.fill_pdf_form(row.to_dict())
                    pdf_buffer = BytesIO()
                    pdfrw.PdfWriter().write(pdf_buffer, filled_pdf)
                    pdf_bytes = pdf_buffer.getvalue()
                    zip_file.writestr(pdf_filename, pdf_bytes)
                    successful_count += 1
                    st.write(f"Processed record {index + 1}/{len(self.excel_data)}: {pdf_filename}")
                except Exception as e:
                    failed_count += 1
                    st.error(f"Error processing record {index}: {str(e)}")

        zip_buffer.seek(0)
        zip_content = zip_buffer.getvalue()

        st.download_button(
            label="Download Filled Forms",
            data=zip_content,
            file_name=zip_filename,
            mime='application/zip'
        )

        st.write(f"\nProcessing complete!")
        st.write(f"Successfully processed: {successful_count} records")
        st.write(f"Failed to process: {failed_count} records")

def main():
    st.title("PDF Form Filler")
    filler = PDFFormFiller()
    filler.upload_files()

    if st.button("Process All Records"):
        filler.process_all_records()

if __name__ == "__main__":
    main()
