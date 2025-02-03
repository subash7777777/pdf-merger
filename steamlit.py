import os
import zipfile
from PyPDF2 import PdfReader, PdfWriter, PdfMerger
import shutil
import streamlit as st

def extract_zip_to_temp_folder(zip_path, temp_folder):
    """Extract a zip file to a temporary folder."""
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall(temp_folder)

def preserve_fields_and_merge_pdfs(first_pdf_path, second_pdf_path, output_pdf_path):
    """
    Merge two PDFs while preserving specific fields.
    """
    try:
        # Read the first PDF
        first_pdf = PdfReader(first_pdf_path)
        first_fields = {}

        # Extract fields from the first PDF
        for page in first_pdf.pages:
            annotations = page.get('/Annots', [])
            for annotation in annotations:
                if isinstance(annotation, IndirectObject):
                    annotation = annotation.get_object()  # Dereference IndirectObject
                if annotation.get('/T') and annotation.get('/V'):
                    first_fields[annotation.get('/T')] = annotation.get('/V')

        # Read the second PDF
        second_pdf = PdfReader(second_pdf_path)
        second_fields = {}

        # Extract fields from the second PDF
        for page in second_pdf.pages:
            annotations = page.get('/Annots', [])
            for annotation in annotations:
                if isinstance(annotation, IndirectObject):
                    annotation = annotation.get_object()  # Dereference IndirectObject
                if annotation.get('/T') and annotation.get('/V'):
                    second_fields[annotation.get('/T')] = annotation.get('/V')

        # Merge PDFs
        merger = PdfMerger()
        merger.append(first_pdf_path)
        merger.append(second_pdf_path)
        merger.write(output_pdf_path)
        merger.close()

        # Reload merged PDF and reinsert form fields
        merged_pdf = PdfReader(output_pdf_path)
        writer = PdfWriter()

        for page in merged_pdf.pages:
            annotations = page.get('/Annots', [])
            for annotation in annotations:
                if isinstance(annotation, IndirectObject):
                    annotation = annotation.get_object()  # Dereference IndirectObject
                field_name = annotation.get('/T')
                if field_name in first_fields:
                    annotation.update({'/V': first_fields[field_name]})
                elif field_name in second_fields:
                    annotation.update({'/V': second_fields[field_name]})
            writer.add_page(page)

        # Save the updated PDF
        with open(output_pdf_path, "wb") as f:
            writer.write(f)

        return output_pdf_path

    except Exception as e:
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
        first_pdfs = {os.path.splitext(f)[0]: os.path.join(first_temp_folder, f) for f in os.listdir(first_temp_folder) if f.endswith('.pdf')}
        second_pdfs = {os.path.splitext(f)[0]: os.path.join(second_temp_folder, f) for f in os.listdir(second_temp_folder) if f.endswith('.pdf')}

        # Create the output zip file
        with zipfile.ZipFile(output_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for account, first_pdf_path in first_pdfs.items():
                if account in second_pdfs:
                    second_pdf_path = second_pdfs[account]

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
                        st.error(f"Error merging files for account {account}: {e}")

        return output_zip

    finally:
        # Clean up temporary folders
        shutil.rmtree(first_temp_folder, ignore_errors=True)
        shutil.rmtree(second_temp_folder, ignore_errors=True)

# Streamlit App
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
                st.download_button(label="Download Merged Zip File", data=f, file_name="merged_pdfs.zip", mime="application/zip")
        except Exception as e:
            st.error(f"An error occurred: {e}")
        finally:
            # Cleanup temporary files
            if os.path.exists(first_zip_path):
                os.remove(first_zip_path)
            if os.path.exists(second_zip_path):
                os.remove(second_zip_path)
            if os.path.exists(output_zip_path):
                os.remove(output_zip_path)
