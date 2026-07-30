import cv2
import numpy as np
import math
from insightface.app import FaceAnalysis
from PIL import Image, ImageOps

app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
app.prepare(ctx_id=-1, det_size=(1280, 1280))

photo_path_str = "/Users/tilakneema/Desktop/Rag_Sample/IMG-20211028-WA0043.jpg"

pil_img = Image.open(photo_path_str)
pil_img.load()
pil_img = ImageOps.exif_transpose(pil_img)
if pil_img.mode != 'RGB':
    pil_img = pil_img.convert('RGB')

orig_w, orig_h = pil_img.size
scale_factor = 1.0
MAX_DIM = 1280

if max(orig_w, orig_h) > MAX_DIM:
    scale_factor = max(orig_w, orig_h) / float(MAX_DIM)
    try:
        resampling = Image.Resampling.LANCZOS
    except AttributeError:
        resampling = Image.LANCZOS
    pil_img.thumbnail((MAX_DIM, MAX_DIM), resampling)

img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
faces = app.get(img)

print(f"Num faces: {len(faces)}")

def _compute_laplacian_variance(img_bgr, bbox):
    h, w = img_bgr.shape[:2]
    x1, y1 = max(0, int(bbox[0])), max(0, int(bbox[1]))
    x2, y2 = min(w, int(bbox[2])), min(h, int(bbox[3]))
    if x2 <= x1 or y2 <= y1:
        return 0.0
    crop = img_bgr[y1:y2, x1:x2]
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    return cv2.Laplacian(gray, cv2.CV_64F).var()

def _compute_roll_angle(kps):
    if kps is None or len(kps) < 2: return 0.0
    edy, edx = kps[1][1] - kps[0][1], kps[1][0] - kps[0][0]
    return abs(math.degrees(math.atan2(edy, edx)))


for i, face in enumerate(faces):
    scaled_bbox = face.bbox.astype(float)
    bbox = scaled_bbox * scale_factor
    face_w, face_h = bbox[2]-bbox[0], bbox[3]-bbox[1]
    
    det_score = getattr(face, 'det_score', 1.0)
    lap_var = _compute_laplacian_variance(img, scaled_bbox)
    roll = _compute_roll_angle(getattr(face, 'kps', None))
    
    print(f"Face {i}: WxH: {face_w:.1f}x{face_h:.1f}, score: {det_score:.3f}, sharp: {lap_var:.1f}, roll: {roll:.1f}")
