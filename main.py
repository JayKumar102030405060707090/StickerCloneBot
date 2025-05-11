import os
import re
import json
import httpx
import redis
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from datetime import timedelta
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import Optional, Union, Dict, List

# Initialize FastAPI app
app = FastAPI(title="YouTube API", description="Ultimate YouTube API with all features", version="1.0")

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# Redis Cache
redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=int(os.getenv("REDIS_DB", 0)),
    decode_responses=True
)

# Simple API Key Check
VALID_API_KEY = "JAYDIP"

def check_api_key(api_key: str):
    """Simple API key validation"""
    if api_key != VALID_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")

# Rate limit error handler
@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "Rate limit exceeded"}
    )

class YouTubeAPI:
    # ... [Keep all the same YouTubeAPI class methods from previous implementation] ...

# API Endpoints with simple API key check
@app.post("/stream")
@limiter.limit("100/minute")
async def get_stream(
    request: Request,
    query: str,
    video: bool = False,
    api_key: str = Query(..., description="API Key")
):
    """Get direct stream URL for a YouTube video"""
    check_api_key(api_key)
    stream_url = await get_stream_url(query, video)
    if not stream_url:
        raise HTTPException(status_code=404, detail="Stream not found")
    
    yt = YouTubeAPI(query)
    details = await yt._fetch_details()
    
    return {
        "id": details.get('id', '') if details else None,
        "title": details.get('title', '') if details else None,
        "duration": details.get('duration', 0) if details else None,
        "link": details.get('url', '') if details else None,
        "channel": details.get('channel', '') if details else None,
        "views": details.get('view_count', 0) if details else None,
        "thumbnail": details.get('thumbnail', '') if details else None,
        "stream_url": stream_url,
        "stream_type": "Video" if video else "Audio"
    }

@app.get("/details")
@limiter.limit("100/minute")
async def get_video_details(
    request: Request,
    link: str = Query(..., description="YouTube URL or video ID"),
    videoid: bool = Query(False, description="Treat input as video ID"),
    api_key: str = Query(..., description="API Key")
):
    """Get video details"""
    check_api_key(api_key)
    query = f"https://www.youtube.com/watch?v={link}" if videoid else link
    yt = YouTubeAPI(query)
    
    if not await yt.exists():
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    
    details = await yt._fetch_details()
    if not details:
        raise HTTPException(status_code=404, detail="Video not found")
    
    return {
        "id": details.get('id', ''),
        "title": details.get('title', ''),
        "duration": details.get('duration', 0),
        "link": details.get('url', ''),
        "channel": details.get('channel', ''),
        "views": details.get('view_count', 0),
        "thumbnail": details.get('thumbnail', ''),
        "stream_url": None,
        "stream_type": None
    }

@app.get("/track")
@limiter.limit("100/minute")
async def get_track_info(
    request: Request,
    link: str = Query(..., description="YouTube URL or video ID"),
    videoid: bool = Query(False, description="Treat input as video ID"),
    api_key: str = Query(..., description="API Key")
):
    """Get track information"""
    check_api_key(api_key)
    query = f"https://www.youtube.com/watch?v={link}" if videoid else link
    yt = YouTubeAPI(query)
    
    if not await yt.exists():
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    
    track_info, vidid = await yt.track()
    if not track_info:
        raise HTTPException(status_code=404, detail="Track not found")
    
    return {
        "track": track_info,
        "vidid": vidid
    }

@app.get("/playlist")
@limiter.limit("100/minute")
async def get_playlist_items(
    request: Request,
    link: str = Query(..., description="YouTube playlist URL or ID"),
    limit: int = Query(100, description="Maximum number of items to return"),
    user_id: Optional[str] = Query(None, description="User ID for caching"),
    videoid: bool = Query(False, description="Treat input as playlist ID"),
    api_key: str = Query(..., description="API Key")
):
    """Get playlist items"""
    check_api_key(api_key)
    query = f"https://www.youtube.com/playlist?list={link}" if videoid else link
    yt = YouTubeAPI(query)
    
    if not await yt.exists():
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    
    items = await yt.playlist(limit)
    return {
        "items": items,
        "limit": limit
    }

@app.get("/formats")
@limiter.limit("100/minute")
async def get_available_formats(
    request: Request,
    link: str = Query(..., description="YouTube URL or video ID"),
    videoid: bool = Query(False, description="Treat input as video ID"),
    api_key: str = Query(..., description="API Key")
):
    """List available formats for a video"""
    check_api_key(api_key)
    query = f"https://www.youtube.com/watch?v={link}" if videoid else link
    yt = YouTubeAPI(query)
    
    if not await yt.exists():
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    
    formats = await yt.formats()
    return {
        "formats": formats
    }

@app.get("/slider")
@limiter.limit("100/minute")
async def get_search_results(
    request: Request,
    link: str = Query(..., description="Search query or YouTube URL"),
    query_type: str = Query("video", description="Type of search results"),
    videoid: bool = Query(False, description="Not used for search"),
    api_key: str = Query(..., description="API Key")
):
    """Get search results (slider)"""
    check_api_key(api_key)
    yt = YouTubeAPI(link)
    results = await yt.slider(query_type)
    return {
        "results": results
    }

@app.post("/download")
@limiter.limit("50/minute")
async def download_video(
    request: Request,
    link: str = Query(..., description="YouTube URL or video ID"),
    video: bool = Query(False, description="Download video if True, audio otherwise"),
    videoid: bool = Query(False, description="Treat input as video ID"),
    songaudio: bool = Query(False, description="Optimize for song audio"),
    songvideo: bool = Query(False, description="Optimize for song video"),
    format_id: Optional[str] = Query(None, description="Specific format ID to download"),
    title: Optional[str] = Query(None, description="Custom title for downloaded file"),
    api_key: str = Query(..., description="API Key")
):
    """Download audio or video from YouTube"""
    check_api_key(api_key)
    query = f"https://www.youtube.com/watch?v={link}" if videoid else link
    yt = YouTubeAPI(query)
    
    if not await yt.exists():
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")
    
    # Handle song optimization
    if songaudio:
        format_id = "bestaudio[ext=m4a]"
    elif songvideo:
        format_id = "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
    
    download_url = await yt.download(video, format_id, title)
    if not download_url:
        raise HTTPException(status_code=500, detail="Download failed")
    
    details = await yt._fetch_details()
    
    return {
        "id": details.get('id', '') if details else None,
        "title": details.get('title', '') if details else None,
        "duration": details.get('duration', 0) if details else None,
        "link": details.get('url', '') if details else None,
        "channel": details.get('channel', '') if details else None,
        "views": details.get('view_count', 0) if details else None,
        "thumbnail": details.get('thumbnail', '') if details else None,
        "stream_url": download_url,
        "stream_type": "Video" if video else "Audio"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
