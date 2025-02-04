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

def get_field_properties(annotation):
    """Extract field properties safely from annotation."""
    if isinstance(annotation, IndirectObject):
        annotation = annotation.get_object()
    
    # Convert field name to PdfObject if it isn't already
    field_name = annotation.get('/T')
    if field_name and not isinstance(field_name, IndirectObject):
        field_name = str(field_name)

    return {
        '/T': field_name,
        '/V': annotation.get('/V'),
        '/FT': annotation.get('/FT'),
        '/Ff': annotation.get('/Ff'),
        '/AP': annotation.get('/AP'),
        '/AS': annotation.get('/AS'),
        '/DA': annotation.get('/DA'),
        '/F': annotation.get('/F'),
        '/Q': annotation.get('/Q'),
        '/Rect': annotation.get('/Rect')
    }

def extract_fields_from_pdf(pdf, debug=False):
    """Extract all fields from a PDF with better detection."""
    fields = {}
    
    # Try multiple methods to find fields
    for page in pdf.pages:
        # Method 1: Direct annotations
        if page.get('/Annots'):
            for annot in page['/Annots']:
                if isinstance(annot, IndirectObject):
                    annot = annot.get_object()
                if annot.get('/T'):
                    field_name = annot['/T']
                    if isinstance(field_name, IndirectObject):
                        field_name = field_name.get_object()
                    field_name = str(field_name)
                    fields[field_name] = get_field_properties(annot)
                    if debug:
                        st.write(f"Found field: {field_name}")
                        st.write(f"Properties: {fields[field_name]}")
        
        # Method 2: AcroForm fields
        if pdf.get_form_text_fields():
            form_fields = pdf.get_form_text_fields()
            for field_name, value in form_fields.items():
                if field_name not in fields:
                    fields[field_name] = {'/T': field_name, '/V': value}
                    if debug:
                        st.write(f"Found AcroForm field: {field_name}")

    return fields

def preserve_fields_and_merge_pdfs(first_pdf_path, second_pdf_path, output_pdf_path):
    """Merge two PDFs while preserving all form fields and their values."""
    try:
        # Read the PDFs
        first_pdf = PdfReader(first_pdf_path)
        second_pdf = PdfReader(second_pdf_path)

        # Extract fields with debug info
        st.write("Analyzing first PDF fields...")
        first_fields = extract_fields_from_pdf(first_pdf, debug=True)
        st.write("\nAnalyzing second PDF fields...")
        second_fields = extract_fields_from_pdf(second_pdf, debug=True)

        # Special handling for problematic fields
        problematic_fields = {
            "Names and status of applicant if other than assessed owner": "Names_and_status",
            "Telephone No": "TelephoneNo",
            "Names_and_status_of_applicant": "Names and status of applicant if other than assessed owner",
            "Telephone_Number": "Telephone No"
        }

        # Check for alternative field names
        for display_name, internal_name in problematic_fields.items():
            if internal_name in first_fields:
                st.write(f"Found problematic field under internal name: {internal_name}")
            if display_name in first_fields:
                st.write(f"Found problematic field under display name: {display_name}")

        # Merge PDFs
        merger = PdfMerger()
        merger.append(first_pdf_path)
        merger.append(second_pdf_path)
        merger.write(output_pdf_path)
        merger.close()

        # Reload merged PDF and reinsert form fields
        merged_pdf = PdfReader(output_pdf_path)
        writer = PdfWriter()

        # Dictionary to store all field values
        all_fields = {}
        all_fields.update(first_fields)
        all_fields.update(second_fields)

        # Process each page
        for page_num, page in enumerate(merged_pdf.pages):
            if page.get('/Annots'):
                annotations = page['/Annots']
                for i, annot in enumerate(annotations):
                    if isinstance(annot, IndirectObject):
                        annot = annot.get_object()
                    
                    field_name = annot.get('/T')
                    if isinstance(field_name, IndirectObject):
                        field_name = field_name.get_object()
                    field_name = str(field_name)

                    # Check both original and alternative field names
                    field_value = None
                    if field_name in all_fields:
                        field_props = all_fields[field_name]
                    elif field_name in problematic_fields:
                        alt_name = problematic_fields[field_name]
                        if alt_name in all_fields:
                            field_props = all_fields[alt_name]
                    elif field_name in [v for v in problematic_fields.values()]:
                        # Check reverse mapping
                        original_name = [k for k, v in problematic_fields.items() if v == field_name][0]
                        if original_name in all_fields:
                            field_props = all_fields[original_name]
                    else:
                        continue

                    # Apply field properties
                    for key, value in field_props.items():
                        if value is not None:
                            annot[key] = value

                    # Ensure field is editable
                    if annot.get('/Ff') is None:
                        annot['/Ff'] = 0

            writer.add_page(page)

        # Ensure form fields are preserved
        writer._root_object.update({
            '/AcroForm': merged_pdf.get_form_text_fields(),
            '/NeedAppearances': True
        })

        # Save the updated PDF
        with open(output_pdf_path, "wb") as f:
            writer.write(f)

        return output_pdf_path

    except Exception as e:
        st.error(f"Error details: {str(e)}")
        raise RuntimeError(f"Error preserving fields while merging: {e}")

def merge_pdfs_by_account(first_zip, second_zip, output_zip):
    """Merge PDFs by matching account numbers from two zip files."""
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

def main():
    """Main Streamlit application."""
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


