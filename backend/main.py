import os
import re
import shutil
import uuid
from pathlib import Path
from base64 import b64decode
from fastapi import FastAPI, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

app = FastAPI()

# Enable CORS (modify origins for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories and templates
BASE_DIR = Path(__file__).resolve().parent
uploads_dir = BASE_DIR / "uploads"
uploads_dir.mkdir(exist_ok=True)
template_dir = BASE_DIR / "template"

# Mount static and uploads for serving files
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")

templates = Jinja2Templates(directory=str(template_dir))

# Google Drive API setup
SERVICE_ACCOUNT_FILE = 'credentials.json'
SCOPES = ['https://www.googleapis.com/auth/drive.file']
KIRAYEDAR_PARENT_FOLDER_ID = '1eWEBaNktPxVLkWLrT3AZT_ax1CHBha6Q'

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
drive_service = build('drive', 'v3', credentials=credentials)


def get_or_create_folder(name: str, parent_id: str) -> str:
    query = f"mimeType='application/vnd.google-apps.folder' and name='{name}' and '{parent_id}' in parents and trashed = false"
    results = drive_service.files().list(q=query, fields="files(id, name)").execute()
    items = results.get("files", [])
    if items:
        return items[0]["id"]
    file_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id]
    }
    folder = drive_service.files().create(body=file_metadata, fields="id").execute()
    return folder["id"]


def upload_to_drive(filepath, filename, parent_folder_id):
    file_metadata = {
        "name": filename,
        "parents": [parent_folder_id]
    }
    media = MediaFileUpload(filepath, resumable=True)
    file = drive_service.files().create(
        body=file_metadata,
        media_body=media,
        fields="id"
    ).execute()
    file_id = file.get("id")
    return f"https://drive.google.com/uc?id={file_id}"  # direct link for image


@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/generate-pdf/", response_class=HTMLResponse)
async def generate_pdf(
    request: Request,
    name: str = Form(...),
    father_name: str = Form(...),
    address: str = Form(...),
    aadhaar: str = Form(...),
    aadhaar_front: UploadFile = File(...),
    aadhaar_back: UploadFile = File(...),
    pan: str = Form(...),
    pan_card: UploadFile = File(...),
    mobile: str = Form(...),
    signature: UploadFile = File(...),
    selfieImage: str = Form(...)
):
    try:
        # Create a safe folder name for Google Drive and local temp files
        safe_name = name.replace(" ", "_") + "_" + str(uuid.uuid4())[:8]
        user_folder_id = get_or_create_folder(safe_name, KIRAYEDAR_PARENT_FOLDER_ID)

        def save_and_upload(uploadfile, label):
            path = uploads_dir / f"{safe_name}_{label}{Path(uploadfile.filename).suffix}"
            with open(path, "wb") as f:
                shutil.copyfileobj(uploadfile.file, f)
            url = upload_to_drive(path, path.name, user_folder_id)
            return url, path

        files_info = {}
        file_paths = []

        files_info["aadhaar_front_url"], af_path = save_and_upload(aadhaar_front, "aadhaar_front")
        files_info["aadhaar_back_url"], ab_path = save_and_upload(aadhaar_back, "aadhaar_back")
        files_info["pan_card_url"], pan_path = save_and_upload(pan_card, "pan_card")
        # signature ko upload nahi karenge, sirf local me save karenge
        sig_path = uploads_dir / f"{safe_name}_signature{Path(signature.filename).suffix}"
        with open(sig_path, "wb") as f:
            shutil.copyfileobj(signature.file, f)
        # selfie base64 to file and upload
        selfie_data = re.sub('^data:image/.+;base64,', '', selfieImage)
        selfie_bytes = b64decode(selfie_data)
        selfie_path = uploads_dir / f"{safe_name}_selfie.png"
        with open(selfie_path, "wb") as f:
            f.write(selfie_bytes)
        selfie_url = upload_to_drive(selfie_path, selfie_path.name, user_folder_id)
        file_paths.extend([af_path, ab_path, pan_path, selfie_path])

        # Clean up all except signature (jo local se serve hoga)
        for p in file_paths:
            if p.exists():
                os.remove(p)

        # Signature url local server ka hoga
        signature_url = f"/uploads/{sig_path.name}"

        # Render contract_display.html with URLs and data
        return templates.TemplateResponse("contract_display.html", {
            "request": request,
            "name": name,
            "father_name": father_name,
            "address": address,
            "aadhaar": aadhaar,
            "pan": pan,
            "mobile": mobile,
            "aadhaar_front_url": files_info["aadhaar_front_url"],
            "aadhaar_back_url": files_info["aadhaar_back_url"],
            "pan_card_url": files_info["pan_card_url"],
            "signature_url": signature_url,
            "selfie_url": selfie_url
        })

    except Exception as e:
        return templates.TemplateResponse("contract_display.html", {
            "request": request,
            "error": str(e)
        })
