from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
import yt_dlp
from youtubesearchpython import VideosSearch
import os
import re
from typing import Optional, List, Dict
from pydantic import BaseModel

app = FastAPI(title="YouTube API", description="Full-featured YouTube API for music bots")

class TrackDetails(BaseModel):
    title: str
    link: str
    vidid: str
    duration_min: str
    thumb: str

class FormatInfo(BaseModel):
    format: str
    filesize: Optional[int]
    format_id: str
    ext: str
    format_note: Optional[str]
    yturl: str

@app.get("/stream_url", summary="Get direct stream URL")
async def get_stream_url(url: str, video: bool = False):
    """
    Get direct audio/video stream URL from YouTube
    - video=False: Returns audio stream
    - video=True: Returns video stream
    """
    ydl_opts = {
        "quiet": True,
        "format": "bestaudio/best" if not video else "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {"stream_url": info["url"]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/video_details", summary="Get video details")
async def get_video_details(url: str):
    """
    Extract video details (title, duration, thumbnail, video ID)
    """
    try:
        results = VideosSearch(url, limit=1)
        video = (await results.next())["result"][0]
        return {
            "title": video["title"],
            "duration": video["duration"],
            "thumbnail": video["thumbnails"][0]["url"].split("?")[0],
            "video_id": video["id"],
            "link": video["link"]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/track_details", response_model=TrackDetails, summary="Get complete track details")
async def get_track_details(url: str):
    """
    Get complete track details including title, link, video ID, duration and thumbnail
    """
    try:
        results = VideosSearch(url, limit=1)
        video = (await results.next())["result"][0]
        return TrackDetails(
            title=video["title"],
            link=video["link"],
            vidid=video["id"],
            duration_min=video["duration"],
            thumb=video["thumbnails"][0]["url"].split("?")[0]
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/formats", response_model=List[FormatInfo], summary="Get available formats")
async def get_formats(url: str):
    """
    Get all available audio/video formats for a YouTube link
    """
    ytdl_opts = {"quiet": True}
    try:
        with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
            formats_available = []
            r = ydl.extract_info(url, download=False)
            for format in r["formats"]:
                try:
                    if not "dash" in str(format["format"]).lower():
                        formats_available.append(FormatInfo(
                            format=format.get("format", ""),
                            filesize=format.get("filesize"),
                            format_id=format.get("format_id", ""),
                            ext=format.get("ext", ""),
                            format_note=format.get("format_note"),
                            yturl=url
                        ))
                except:
                    continue
            return formats_available
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/playlist", summary="Extract playlist items")
async def get_playlist(url: str, limit: int = 10):
    """
    Extract video IDs from a YouTube playlist
    """
    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "playlistend": limit
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return {"videos": [entry["id"] for entry in info["entries"]]}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/download/audio", summary="Download best audio quality")
async def download_audio(url: str):
    """
    Download the best available audio quality
    """
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "quiet": True,
        "noplaylist": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }]
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info).replace(".webm", ".mp3").replace(".m4a", ".mp3")
            return FileResponse(file_path, media_type="audio/mpeg", filename=os.path.basename(file_path))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/download/video", summary="Download best video quality")
async def download_video(url: str):
    """
    Download the best available video quality (720p or lower)
    """
    ydl_opts = {
        "format": "(bestvideo[height<=?720][ext=mp4])+(bestaudio[ext=m4a])/best[ext=mp4]",
        "outtmpl": "downloads/%(id)s.%(ext)s",
        "quiet": True,
        "noplaylist": True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            return FileResponse(file_path, media_type="video/mp4", filename=os.path.basename(file_path))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/download/custom", summary="Download in custom format")
async def download_custom(url: str, format_id: str, title: str):
    """
    Download in a specific format using format ID
    """
    ydl_opts = {
        "format": format_id,
        "outtmpl": f"downloads/{title}.%(ext)s",
        "quiet": True,
        "noplaylist": True
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            file_path = ydl.prepare_filename(info)
            return FileResponse(file_path, filename=os.path.basename(file_path))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/search", summary="Search YouTube videos")
async def search_youtube(query: str, limit: int = 10):
    """
    Search YouTube and return top results
    """
    try:
        results = VideosSearch(query, limit=limit)
        videos = (await results.next())["result"]
        return [{
            "title": video["title"],
            "link": video["link"],
            "thumbnail": video["thumbnails"][0]["url"].split("?")[0],
            "duration": video["duration"],
            "video_id": video["id"]
        } for video in videos]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/slider_result", summary="Get specific search result")
async def get_slider_result(query: str, index: int = 0):
    """
    Get the Nth result from a YouTube search
    """
    try:
        results = VideosSearch(query, limit=index+1)
        videos = (await results.next())["result"]
        if index >= len(videos):
            raise HTTPException(status_code=404, detail="Index out of range")
        video = videos[index]
        return {
            "title": video["title"],
            "duration": video["duration"],
            "thumbnail": video["thumbnails"][0]["url"].split("?")[0],
            "video_id": video["id"],
            "link": video["link"]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    if not os.path.exists("downloads"):
        os.makedirs("downloads")
    uvicorn.run(app, host="0.0.0.0", port=8000)
