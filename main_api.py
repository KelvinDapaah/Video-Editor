from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import yt_dlp
import os
import uuid
import shutil

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = "downloads"
if not os.path.exists(DOWNLOAD_DIR):
    os.makedirs(DOWNLOAD_DIR)

def cleanup_file(file_path: str):
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception as e:
        print(f"Error cleaning up file {file_path}: {e}")

@app.get("/")
async def root():
    return {"message": "Pinterest Downloader API is running!"}

@app.get("/download")
async def download_video(url: str, background_tasks: BackgroundTasks):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")

    request_id = str(uuid.uuid4())
    output_template = os.path.join(DOWNLOAD_DIR, f"{request_id}.%(ext)s")

    ydl_opts = {
        'format': 'bestvideo+bestaudio/best',
        'merge_output_format': 'mp4',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            background_tasks.add_task(cleanup_file, filename)
            return FileResponse(
                path=filename,
                filename=f"{info.get('title', 'video')}.mp4",
                media_type='video/mp4'
            )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
