import os
import zipfile
from PyPDF2 import PdfReader, PdfWriter, PdfMerger
from PyPDF2.generic import IndirectObject
import shutil
import streamlit as st

def extract_zip_to_temp_folder(zip_path, temp_folder):
    """Extract a zip file to a temporary folder."""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(temp_folder)

def preserve_fields_and_merge_pdfs(first_pdf_path, second_pdf_path, output_pdf_path):
    """
    Merge two PDFs while preserving all field properties and values.
    """
    try:
        # Read the PDFs
        first_pdf = PdfReader(first_pdf_path)
        second_pdf = PdfReader(second_pdf_path)
        
        # Store complete field definitions from first PDF
        first_fields = {}
        for field in first_pdf.pages[0].get('/Annots', []):
            if isinstance(field, IndirectObject):
                field = field.get_object()
            if field.get('/T'):
                # Store complete field properties
                first_fields[field.get('/T')] = {
                    '/T': field.get('/T'),
                    '/V': field.get('/V'),
                    '/FT': field.get('/FT'),
                    '/Ff': field.get('/Ff'),
                    '/AP': field.get('/AP'),
                    '/AS': field.get('/AS'),
                    '/DA': field.get('/DA'),  # Default Appearance
                    '/F': field.get('/F'),    # Flags
                    '/Q': field.get('/Q'),    # Quadding (alignment)
                    '/Rect': field.get('/Rect')  # Position and size
                }

        # Store complete field definitions from second PDF
        second_fields = {}
        for field in second_pdf.pages[0].get('/Annots', []):
            if isinstance(field, IndirectObject):
                field = field.get_object()
            if field.get('/T'):
                # Store complete field properties
                second_fields[field.get('/T')] = {
                    '/T': field.get('/T'),
                    '/V': field.get('/V'),
                    '/FT': field.get('/FT'),
                    '/Ff': field.get('/Ff'),
                    '/AP': field.get('/AP'),
                    '/AS': field.get('/AS'),
                    '/DA': field.get('/DA'),
                    '/F': field.get('/F'),
                    '/Q': field.get('/Q'),
                    '/Rect': field.get('/Rect')
                }

        # Log field information for debugging
        st.write(f"Fields found in first PDF: {list(first_fields.keys())}")
        st.write(f"Fields found in second PDF: {list(second_fields.keys())}")

        # Merge PDFs
        merger = PdfMerger()
        merger.append(first_pdf_path)
        merger.append(second_pdf_path)
        merger.write(output_pdf_path)
        merger.close()

        # Reload merged PDF and reinsert form fields
        merged_pdf = PdfReader(output_pdf_path)
        writer = PdfWriter()

        # Process each page
        for page_num, page in enumerate(merged_pdf.pages):
            annotations = page.get('/Annots', [])
            for annotation in annotations:
                if isinstance(annotation, IndirectObject):
                    annotation = annotation.get_object()
                field_name = annotation.get('/T')
                
                # Update fields based on which PDF they came from
                if page_num == 0 and field_name in first_fields:
                    field_props = first_fields[field_name]
                    # Update all field properties
                    for key, value in field_props.items():
                        if value is not None:
                            annotation[key] = value
                elif page_num == 1 and field_name in second_fields:
                    field_props = second_fields[field_name]
                    # Update all field properties
                    for key, value in field_props.items():
                        if value is not None:
                            annotation[key] = value

                # Ensure field is editable
                if annotation.get('/Ff') is None:
                    annotation['/Ff'] = 0  # Set default flags if none exist

            writer.add_page(page)

        # Set form properties in the writer
        writer._root_object.update({
            '/AcroForm': merged_pdf.get_form_text_fields(),
            '/NeedAppearances': True
        })

        # Save the updated PDF
        with open(output_pdf_path, "wb") as f:
            writer.write(f)

        return output_pdf_path

    except Exception as e:
        st.error(f"Error preserving fields while merging: {str(e)}")
        raise RuntimeError(f"Error preserving fields while merging: {e}")

def merge_pdfs_by_account(first_zip, second_zip, output_zip):
    """Merge PDFs by matching account names and create a single zip file with merged PDFs."""
    first_temp_folder = "first_temp"
    second_temp_folder = "second_temp"
    os.makedirs(first_temp_folder, exist_ok=True)
    os.makedirs(second_temp_folder, exist_ok=True)

    try:
        # Extract zip files
        extract_zip_to_temp_folder(first_zip, first_temp_folder)
        extract_zip_to_temp_folder(second_zip, second_temp_folder)

        # Get lists of PDFs from both folders
        first_pdfs = {os.path.splitext(f)[0]: os.path.join(first_temp_folder, f) 
                     for f in os.listdir(first_temp_folder) if f.endswith('.pdf')}
        second_pdfs = {os.path.splitext(f)[0]: os.path.join(second_temp_folder, f) 
                      for f in os.listdir(second_temp_folder) if f.endswith('.pdf')}

        processed_count = 0
        total_count = len(first_pdfs)
        
        # Create progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()

        # Create the output zip file
        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for account, first_pdf_path in first_pdfs.items():
                if account in second_pdfs:
                    second_pdf_path = second_pdfs[account]

                    # Update progress
                    processed_count += 1
                    progress = processed_count / total_count
                    progress_bar.progress(progress)
                    status_text.text(f"Processing: {processed_count}/{total_count}")

                    # Validate PDFs
                    if os.path.getsize(first_pdf_path) == 0 or os.path.getsize(second_pdf_path) == 0:
                        st.warning(f"Skipping empty file for account: {account}")
                        continue

                    try:
                        # Define merged output file name
                        merged_pdf_path = f"{account}.pdf"
                        preserve_fields_and_merge_pdfs(first_pdf_path, second_pdf_path, merged_pdf_path)

                        # Add to the zip file
                        zipf.write(merged_pdf_path, arcname=os.path.basename(merged_pdf_path))

                        # Remove the temporary merged file
                        os.remove(merged_pdf_path)
                    except Exception as e:
                        st.error(f"Error merging files for account {account}: {str(e)}")

        return output_zip

    finally:
        # Clean up temporary folders
        shutil.rmtree(first_temp_folder, ignore_errors=True)
        shutil.rmtree(second_temp_folder, ignore_errors=True)

# Streamlit App
def main():
    st.title("PDF Merger App")
    st.write("Upload two zip files containing PDFs with matching account numbers. The app will merge the PDFs and return a zip file containing the results.")

    # File upload
    first_zip_file = st.file_uploader("Upload the first zip file containing PDFs", type=["zip"])
    second_zip_file = st.file_uploader("Upload the second zip file containing PDFs", type=["zip"])

    if first_zip_file and second_zip_file:
        if st.button("Merge PDFs"):
            # Save the uploaded files temporarily
            first_zip_path = "first_uploaded.zip"
            second_zip_path = "second_uploaded.zip"
            
            try:
                with open(first_zip_path, "wb") as f:
                    f.write(first_zip_file.read())
                with open(second_zip_path, "wb") as f:
                    f.write(second_zip_file.read())

                # Output zip file name
                output_zip_path = "merged_pdfs.zip"

                # Merge PDFs
                try:
                    merge_pdfs_by_account(first_zip_path, second_zip_path, output_zip_path)
                    st.success("PDFs have been merged successfully!")

                    # Provide download link
                    with open(output_zip_path, "rb") as f:
                        st.download_button(
                            label="Download Merged Zip File",
                            data=f,
                            file_name="merged_pdfs.zip",
                            mime="application/zip"
                        )
                except Exception as e:
                    st.error(f"An error occurred during merging: {str(e)}")
            finally:
                # Cleanup temporary files
                for file_path in [first_zip_path, second_zip_path, output_zip_path]:
                    if os.path.exists(file_path):
                        os.remove(file_path)

if __name__ == "__main__":
    main()
