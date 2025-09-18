import cv2
import numpy as np
from PIL import Image
import pytesseract
from pytesseract import Output
from .config import LANGS, TESS_CONFIG

def preprocess(pil_img: Image.Image) -> Image.Image:
    img = np.array(pil_img)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    gray = cv2.fastNlMeansDenoising(gray, h=15)
    bw = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 31, 15)
    kernel = np.ones((1,1), np.uint8)
    bw = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)
    return Image.fromarray(bw)

def ocr_with_boxes(pil_img: Image.Image):
    cfg = f"{TESS_CONFIG} -l {LANGS}"
    df = pytesseract.image_to_data(pil_img, output_type=Output.DATAFRAME, config=cfg)
    text = pytesseract.image_to_string(pil_img, config=cfg)
    return {"df": df, "text": text}
