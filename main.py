import os
import re
import redis
import uuid
from urllib.parse import urlparse
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
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

@app.get("/youtube")
@limiter.limit("100/minute")
async def youtube_endpoint(
    request: Request,
    query: str,
    video: bool = False,
    api_key: Optional[str] = None
):
    # Generate a unique ID for stream URL
    stream_id = str(uuid.uuid4())
    
    # Check if query is a URL or search term
    if not (query.startswith("http://") or query.startswith("https://")):
        # Perform search
        yt_search = YouTubeAPI(f"ytsearch1:{query}")
        search_results = await yt_search.slider(query_type="video")
        if not search_results:
            raise HTTPException(status_code=404, detail="No results found")
        query = f"https://youtube.com/watch?v={search_results[0]['id']}"
    
    yt = YouTubeAPI(query)
    details = await yt._fetch_details()
    if not details:
        raise HTTPException(status_code=404, detail="Video not found")
    
    # Store the original query in Redis with stream_id as key
    redis_client.setex(f"stream:{stream_id}", 3600, query)  # Expires in 1 hour
    
    # Generate stream URL in same format as your friend's API
    base_url = str(request.base_url).rstrip("/")
    stream_url = f"{base_url}/stream/{stream_id}"
    
    return {
        "id": details.get('id'),
        "title": details.get('title'),
        "duration": details.get('duration'),
        "link": details.get('url'),
        "channel": details.get('channel'),
        "views": details.get('view_count'),
        "thumbnail": details.get('thumbnail'),
        "stream_url": stream_url,
        "stream_type": "Video" if video else "Audio"
    }

@app.get("/stream/{stream_id}")
@limiter.limit("100/minute")
async def stream_proxy(
    request: Request,
    stream_id: str,
    video: bool = False
):
    # Get the original query from Redis
    original_query = redis_client.get(f"stream:{stream_id}")
    if not original_query:
        raise HTTPException(status_code=404, detail="Stream not found or expired")
    
    # Get the actual stream URL from YouTube
    stream_url = await YouTubeAPI.get_stream_url_static(original_query, video)
    if not stream_url:
        raise HTTPException(status_code=404, detail="Stream not found")
    
    # Redirect to the actual YouTube stream URL
    return RedirectResponse(url=stream_url)

# ... [keep all your existing endpoints below] ...

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
