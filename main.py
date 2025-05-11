from fastapi import FastAPI, Query from pytube import YouTube, Playlist, Search from fastapi.middleware.cors import CORSMiddleware import re

app = FastAPI()

app.add_middleware( CORSMiddleware, allow_origins=[""], allow_credentials=True, allow_methods=[""], allow_headers=["*"], )

Helper function to detect video ID, playlist ID, or full link

def detect_and_format_query(query: str): query = query.strip()

# YouTube video ID pattern
video_id_pattern = r"^[a-zA-Z0-9_-]{11}$"
# YouTube playlist ID pattern
playlist_id_pattern = r"^(PL|UU|LL|RD)[a-zA-Z0-9_-]{16,34}$"

# Full YouTube video link pattern
video_link_pattern = r"^(https?://)?(www\.)?(youtube\.com|youtu\.be)/.+$"

if re.match(video_id_pattern, query):
    return f"https://youtu.be/{query}"
elif re.match(playlist_id_pattern, query):
    return f"https://www.youtube.com/playlist?list={query}"
elif re.match(video_link_pattern, query):
    return query
else:
    return None

@app.get("/videoinfo") async def video_info(query: str, videoid: bool = Query(False)): try: url = query if videoid: formatted = detect_and_format_query(query) if formatted: url = formatted

yt = YouTube(url)
    info = {
        "title": yt.title,
        "author": yt.author,
        "length": yt.length,
        "views": yt.views,
        "description": yt.description,
        "thumbnail_url": yt.thumbnail_url
    }
    return info

except Exception as e:
    return {"error": str(e)}

@app.get("/playlistinfo") async def playlist_info(query: str, videoid: bool = Query(False)): try: url = query if videoid: formatted = detect_and_format_query(query) if formatted: url = formatted

pl = Playlist(url)
    videos = []
    for video in pl.videos:
        videos.append({
            "title": video.title,
            "author": video.author,
            "length": video.length,
            "views": video.views,
            "description": video.description,
            "thumbnail_url": video.thumbnail_url
        })

    info = {
        "title": pl.title,
        "owner": pl.owner,
        "video_count": len(videos),
        "videos": videos
    }
    return info

except Exception as e:
    return {"error": str(e)}

@app.get("/search") async def search(query: str): try: s = Search(query) results = [] for result in s.results: results.append({ "title": result.title, "author": result.author, "length": result.length, "views": result.views, "description": result.description, "thumbnail_url": result.thumbnail_url, "watch_url": result.watch_url }) return {"results": results}

except Exception as e:
    return {"error": str(e)}
