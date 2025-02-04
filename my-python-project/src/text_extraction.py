def extract_text_from_pdf(pdf_path):
    """
    Extrahiert Text aus einer PDF-Datei.

    Args:
        pdf_path (str): Der Pfad zur PDF-Datei.

    Returns:
        str: Der extrahierte Text.
    """
    import PyPDF2

    text = ""
    with open(pdf_path, "rb") as file:
        reader = PyPDF2.PdfReader(file)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    return text


def extract_text_from_image(image_path):
    """
    Extrahiert Text aus einem Bild.

    Args:
        image_path (str): Der Pfad zum Bild.

    Returns:
        str: Der extrahierte Text.
    """
    import pytesseract
    from PIL import Image

    image = Image.open(image_path)
    text = pytesseract.image_to_string(image)
    return text