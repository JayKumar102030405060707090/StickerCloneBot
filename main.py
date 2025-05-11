import os
import re
import redis
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from yt_dlp import YoutubeDL
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import Optional

app = FastAPI(
    title="Ultimate YouTube API (Public Version)",
    description="Fully featured public YouTube API (no API key, exact response format)",
    version="1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

redis_url = os.getenv("REDIS_URL")
if redis_url:
    url = urlparse(redis_url)
    redis_client = redis.Redis(
        host=url.hostname,
        port=url.port,
        password=url.password,
        decode_responses=True
    )
else:
    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        db=int(os.getenv("REDIS_DB", 0)),
        decode_responses=True
    )

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"error": "Rate limit exceeded"})

def clean_url(url: str) -> str:
    return re.split(r'[&?]', url)[0]

class YouTubeAPI:
    def __init__(self, query: str):
        self.query = clean_url(query)

    async def exists(self):
        return "youtube.com" in self.query or "youtu.be" in self.query

    async def _fetch_details(self):
        ydl_opts = {'quiet': True, 'skip_download': True}
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(self.query, download=False)
                return {
                    'id': info.get('id'),
                    'title': info.get('title'),
                    'duration': info.get('duration'),
                    'url': info.get('webpage_url'),
                    'channel': info.get('uploader'),
                    'view_count': info.get('view_count'),
                    'thumbnail': self.get_best_thumbnail(info)
                }
            except:
                return None

    @staticmethod
    def get_best_thumbnail(info):
        vidid = info.get('id')
        if vidid:
            return f"https://i.ytimg.com/vi_webp/{vidid}/maxresdefault.webp"
        return info.get('thumbnail')

    @staticmethod
    async def get_stream_url_static(query: str, video: bool = False):
        query = clean_url(query)
        ydl_opts = {
            'quiet': True,
            'format': 'bestvideo+bestaudio/best' if video else 'bestaudio',
            'skip_download': True
        }
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(query, download=False)
                formats = info.get('formats', [])
                if video:
                    candidates = [f for f in formats if f.get('vcodec') != 'none']
                else:
                    candidates = [f for f in formats if f.get('acodec') != 'none']
                if not candidates:
                    return ""
                url = sorted(candidates, key=lambda x: x.get('filesize', 0) or 0, reverse=True)[0].get('url')
                return url
            except:
                return ""

    async def track(self):
        details = await self._fetch_details()
        if details:
            return ({
                "title": details.get('title'),
                "link": details.get('url'),
                "vidid": details.get('id'),
                "duration_min": int(details.get('duration', 0)) // 60 if details.get('duration') else None,
                "thumb": details.get('thumbnail'),
                "views": details.get('view_count')
            }, details.get('id'))
        return (None, None)

    async def playlist(self, limit):
        ydl_opts = {'quiet': True, 'extract_flat': True, 'playlistend': limit}
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(self.query, download=False)
                return [entry['url'] for entry in info.get('entries', [])][:limit]
            except:
                return []

    async def formats(self):
        ydl_opts = {'quiet': True, 'skip_download': True}
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(self.query, download=False)
                return info.get('formats', [])
            except:
                return []

    async def slider(self, query_type="video"):
        search_query = f"ytsearch5:{self.query}" if query_type == "video" else f"ytsearch5:{self.query} playlist"
        ydl_opts = {'quiet': True, 'extract_flat': True}
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(search_query, download=False)
                return info.get('entries', [])
            except:
                return []

    async def download(self, video=False, format_id=None, title=None):
        format_str = format_id if format_id else ('bestvideo+bestaudio' if video else 'bestaudio')
        ydl_opts = {
            'quiet': True,
            'format': format_str,
            'noplaylist': True,
            'outtmpl': f"{title or '%(title)s'}-%(id)s.%(ext)s"
        }
        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(self.query, download=True)
                return info.get('url')
            except:
                return None

async def make_response(details, stream_url=None, stream_type=None):
    return {
        "id": details.get('id') if details else None,
        "title": details.get('title') if details else None,
        "duration": details.get('duration') if details else None,
        "link": details.get('url') if details else None,
        "channel": details.get('channel') if details else None,
        "views": details.get('view_count') if details else None,
        "thumbnail": details.get('thumbnail') if details else None,
        "stream_url": stream_url or None,
        "stream_type": stream_type or None
    }

@app.post("/stream")
@limiter.limit("100/minute")
async def stream(request: Request, query: str, video: bool = False):
    stream_url = await YouTubeAPI.get_stream_url_static(query, video)
    yt = YouTubeAPI(query)
    details = await yt._fetch_details()
    return await make_response(details, stream_url, "Video" if video else "Audio")

@app.get("/details")
@limiter.limit("100/minute")
async def details(request: Request, link: str, videoid: bool = False):
    query = f"https://www.youtube.com/watch?v={link}" if videoid else link
    yt = YouTubeAPI(query)
    details = await yt._fetch_details()
    return await make_response(details)

@app.get("/track")
@limiter.limit("100/minute")
async def track(request: Request, link: str, videoid: bool = False):
    query = f"https://www.youtube.com/watch?v={link}" if videoid else link
    yt = YouTubeAPI(query)
    info, vidid = await yt.track()
    return {"track": info, "vidid": vidid}

@app.get("/playlist")
@limiter.limit("100/minute")
async def playlist(request: Request, link: str, limit: int = 100, user_id: Optional[str] = None, videoid: bool = False):
    query = f"https://www.youtube.com/playlist?list={link}" if videoid else link
    yt = YouTubeAPI(query)
    items = await yt.playlist(limit)
    return {"items": items, "limit": limit}

@app.get("/formats")
@limiter.limit("100/minute")
async def formats(request: Request, link: str, videoid: bool = False):
    query = f"https://www.youtube.com/watch?v={link}" if videoid else link
    yt = YouTubeAPI(query)
    fmts = await yt.formats()
    return {"formats": fmts}

@app.get("/slider")
@limiter.limit("100/minute")
async def slider(request: Request, link: str, query_type: str = "video", videoid: bool = False):
    query = f"https://www.youtube.com/watch?v={link}" if videoid else link
    yt = YouTubeAPI(query)
    results = await yt.slider(query_type)
    return {"results": results}

@app.post("/download")
@limiter.limit("50/minute")
async def download(request: Request, link: str, video: bool = False, videoid: bool = False, songaudio: bool = False, songvideo: bool = False, format_id: Optional[str] = None, title: Optional[str] = None):
    query = f"https://www.youtube.com/watch?v={link}" if videoid else link
    yt = YouTubeAPI(query)
    if songaudio:
        format_id = "bestaudio[ext=m4a]"
    elif songvideo:
        format_id = "bestvideo[ext=mp4]+bestaudio[ext=m4a]"
    download_url = await yt.download(video, format_id, title)
    details = await yt._fetch_details()
    return await make_response(details, stream_url=download_url, stream_type="Video" if video else "Audio")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
