import os, uuid, shutil
from fastapi import Form, File, UploadFile, Depends
from typing import Optional, Dict, Any

def delete_file(filename):
    if os.path.exists(filename):
            os.remove(filename)
    return print(f'File "{filename}" deleted.')        

def upload_file(file: UploadFile, upload_dir: str) -> str:

    filename = f"{uuid.uuid4().hex}_{file.filename}"
    filepath = os.path.join(upload_dir, filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return filepath
