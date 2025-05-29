from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive']
SERVICE_ACCOUNT_FILE = 'credentials.json'  # path to your service account JSON

def get_drive_service():
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return build('drive', 'v3', credentials=credentials)

def upload_file_to_drive(file_path, file_name, folder_id=None):
    service = get_drive_service()
    file_metadata = {'name': file_name}
    if folder_id:
        file_metadata['parents'] = [folder_id]

    media = MediaFileUpload(file_path, resumable=True)
    uploaded_file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
    return uploaded_file.get('webViewLink')  # Return shareable link
