from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
import yt_dlp
import os
from pathlib import Path
import asyncio
import humanize
from datetime import datetime

app = FastAPI()

# 配置模板
templates = Jinja2Templates(directory="templates")

# 视频保存目录
DOWNLOAD_DIR = Path("/tmp/downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

# 为了在 Vercel 上工作，我们需要将下载目录挂载为静态目录
app.mount("/downloads", StaticFiles(directory="/tmp/downloads"), name="downloads")

# 存储下载任务状态
download_tasks = {}

@app.get("/api/health")
async def health_check():
    return {"status": "ok"}

def get_video_info(url):
    """获取视频信息"""
    with yt_dlp.YoutubeDL() as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return {
                "title": info["title"],
                "duration": str(int(info["duration"] // 60)) + ":" + str(int(info["duration"] % 60)),
                "author": info["uploader"],
                "description": info["description"][:200] + "...",
                "thumbnail": info["thumbnail"],
            }
        except Exception as e:
            return {"error": str(e)}

async def download_video(url, video_id):
    """异步下载视频"""
    download_tasks[video_id] = {"status": "downloading", "progress": 0}
    
    def progress_hook(d):
        if d['status'] == 'downloading':
            download_tasks[video_id]["progress"] = int(d.get('downloaded_bytes', 0) / d.get('total_bytes', 1) * 100)
    
    ydl_opts = {
        'format': 'best',
        'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
        'progress_hooks': [progress_hook],
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = await asyncio.to_thread(ydl.download, [url])
            download_tasks[video_id]["status"] = "completed"
            return info
    except Exception as e:
        download_tasks[video_id]["status"] = "error"
        download_tasks[video_id]["error"] = str(e)

@app.get("/")
async def home(request: Request):
    """首页"""
    # 获取已下载视频列表
    videos = []
    for file in DOWNLOAD_DIR.glob("*"):
        if file.is_file():
            stats = file.stat()
            videos.append({
                "name": file.name,
                "size": humanize.naturalsize(stats.st_size),
                "date": datetime.fromtimestamp(stats.st_mtime).strftime("%Y-%m-%d %H:%M"),
                "path": str(file)
            })
    
    return templates.TemplateResponse(
        "index.html", 
        {"request": request, "videos": videos}
    )

from fastapi import Body

@app.post("/download")
async def download(url: str = Body(..., embed=True)):
    """开始下载视频"""
    video_id = str(len(download_tasks))
    info = get_video_info(url)
    if "error" in info:
        return JSONResponse({"error": info["error"]})
    
    # 启动异步下载任务
    asyncio.create_task(download_video(url, video_id))
    
    return {
        "video_id": video_id,
        "info": info
    }
async def download(url: str):
    """开始下载视频"""
    video_id = str(len(download_tasks))
    info = get_video_info(url)
    if "error" in info:
        return JSONResponse({"error": info["error"]})
    
    # 启动异步下载任务
    asyncio.create_task(download_video(url, video_id))
    
    return {
        "video_id": video_id,
        "info": info
    }

@app.get("/status/{video_id}")
async def get_status(video_id: str):
    """获取下载状态"""
    if video_id in download_tasks:
        return download_tasks[video_id]
    return {"status": "not_found"}