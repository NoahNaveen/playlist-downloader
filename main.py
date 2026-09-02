import os
import shutil
import uuid
import re
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import yt_dlp

app = FastAPI()

os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

tasks = {}

class PlaylistRequest(BaseModel):
    url: str

# NEW: Analyzes the URL and returns thumbnails & titles instantly
@app.post("/api/analyze")
async def analyze_playlist(request: PlaylistRequest):
    ydl_opts = {
        'extract_flat': True, # Scrapes metadata only, no downloading
        'quiet': True,
        'js_runtimes': {'node': {}},
        'cookiefile': 'cookies.txt',
        'extractor_args': {'youtube': ['player_client=android']}, 
        'sleep_interval': 5,      
        'max_sleep_interval': 10,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=False)
            
            # Handle both single videos and playlists
            videos = info.get('entries', [info])
            playlist_data = []
            
            for v in videos:
                if not v: continue
                # Grab the highest resolution thumbnail available
                thumbs = v.get('thumbnails', [])
                thumb_url = thumbs[-1]['url'] if thumbs else 'https://via.placeholder.com/120x90?text=No+Image'
                
                playlist_data.append({
                    'id': v.get('id'),
                    'title': v.get('title'),
                    'thumbnail': thumb_url
                })
                
            return {"title": info.get('title', 'YouTube Playlist'), "videos": playlist_data}
    except Exception as e:
        return {"error": str(e)}

def download_and_zip(task_id: str, url: str):
    output_dir = f"downloads/{task_id}"
    os.makedirs(output_dir, exist_ok=True)

    def progress_hook(d):
        video_id = d.get('info_dict', {}).get('id', 'unknown')
        
        if d['status'] == 'downloading':
            raw_percent = d.get('_percent_str', '0%')
            # Clean terminal color codes from yt-dlp percentage output
            clean_percent = re.sub(r'\x1b\[[0-9;]*m', '', raw_percent).strip()
            
            # Update the specific video's progress
            tasks[task_id]['progress'][video_id] = clean_percent
            tasks[task_id]['status'] = 'downloading'
            tasks[task_id]['current_file'] = os.path.basename(d.get('filename', 'Unknown Track'))
            
        elif d['status'] == 'finished':
            tasks[task_id]['progress'][video_id] = '100%'

    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}],
        'outtmpl': f'{output_dir}/%(playlist_index)s - %(title)s.%(ext)s',
        'noplaylist': False,
        'ignoreerrors': True,
        'quiet': False, # Make sure this is False so it prints to the cloud logs!
        'progress_hooks': [progress_hook],
        'js_runtimes': {'node': {}},
        'source_address': '0.0.0.0', 
        'cookiefile': 'cookies.txt',
        'extractor_args': {'youtube': ['player_client=android']}, 
        'sleep_interval': 5,      
        'max_sleep_interval': 10,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        if not os.listdir(output_dir):
            tasks[task_id] = {'status': 'failed', 'error': 'No files downloaded.'}
            shutil.rmtree(output_dir)
            return
        
        zip_filename = f"downloads/{task_id}"
        shutil.make_archive(zip_filename, 'zip', output_dir)
        shutil.rmtree(output_dir)
        
        tasks[task_id]['status'] = 'completed'
        tasks[task_id]['zip_path'] = f"{zip_filename}.zip"
    except Exception as e:
        tasks[task_id] = {'status': 'failed', 'error': str(e)}

@app.get("/")
async def serve_frontend():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.post("/api/start-download")
async def start_download(request: PlaylistRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())
    # Initialize the progress dictionary for our UI
    tasks[task_id] = {'status': 'starting', 'current_file': 'Initializing...', 'progress': {}}
    
    background_tasks.add_task(download_and_zip, task_id, request.url)
    return {"task_id": task_id}

@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    return tasks.get(task_id, {"status": "not_found"})

@app.get("/api/download/{task_id}")
async def download_zip(task_id: str):
    file_path = tasks.get(task_id, {}).get("zip_path")
    if file_path and os.path.exists(file_path):
        return FileResponse(file_path, media_type="application/zip", filename="Playlist_Audio.zip")
    return {"error": "File not found"}
