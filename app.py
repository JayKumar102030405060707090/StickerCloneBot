from flask import Flask, request, Response
import json
import requests
from collections import OrderedDict

app = Flask(__name__)

VALID_API_KEY = "1a873582a7c83342f961cc0a177b2b26"
YOUTUBE_DATA_API_KEY = "AIzaSyAOorokSXnBGeDFte5_LoxXWh6MYPIOq7I"

def error_response(message, code=400):
    return Response(json.dumps({"error": message}), mimetype="application/json"), code

def success_response(data):
    return Response(json.dumps(data), mimetype="application/json")

def validate_key():
    api_key = request.args.get("api_key")
    if api_key != VALID_API_KEY:
        return error_response("Invalid API key", 401)

def build_fixed_response(info, stream_url=None, stream_type=None):
    return OrderedDict([
        ("id", info.get("id", "")),
        ("title", info.get("title", "")),
        ("duration", int(info.get("duration", 0))),
        ("link", f"https://youtu.be/{info.get('id')}"),
        ("channel", info.get("channelTitle", "N/A")),
        ("views", info.get("viewCount", 0)),
        ("thumbnail", info.get("thumbnail", "")),
        ("stream_url", stream_url or "N/A"),
        ("stream_type", stream_type or "N/A")
    ])

def fetch_video_info(video_id):
    url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet,contentDetails,statistics&id={video_id}&key={YOUTUBE_DATA_API_KEY}"
    response = requests.get(url)
    result = response.json()
    if "items" not in result or not result["items"]:
        return None
    item = result["items"][0]
    duration = parse_duration(item["contentDetails"]["duration"])
    info = {
        "id": item["id"],
        "title": item["snippet"]["title"],
        "duration": duration,
        "channelTitle": item["snippet"]["channelTitle"],
        "viewCount": int(item["statistics"].get("viewCount", 0)),
        "thumbnail": item["snippet"]["thumbnails"]["high"]["url"]
    }
    return info

def parse_duration(duration_str):
    import isodate
    duration = isodate.parse_duration(duration_str)
    return int(duration.total_seconds())

@app.route("/details")
def details():
    check = validate_key()
    if check: return check

    link = request.args.get("link")
    if not link:
        return error_response("Missing 'link' parameter")

    video_id = extract_video_id(link)
    if not video_id:
        return error_response("Invalid YouTube link")

    info = fetch_video_info(video_id)
    if not info:
        return error_response("Video not found")

    response_data = build_fixed_response(info)
    return success_response(response_data)

@app.route("/track")
def track():
    return details()  # Same as details (we return full info anyway)

@app.route("/slider")
def slider():
    check = validate_key()
    if check: return check

    query = request.args.get("link")
    query_type = int(request.args.get("query_type", "0"))
    if not query:
        return error_response("Missing 'link' parameter")

    search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&maxResults=10&q={query}&key={YOUTUBE_DATA_API_KEY}"
    response = requests.get(search_url)
    result = response.json()
    if "items" not in result or not result["items"]:
        return error_response("No results found")

    try:
        selected = result["items"][query_type]
        video_id = selected["id"]["videoId"]
        info = fetch_video_info(video_id)
        if not info:
            return error_response("Video not found")
        response_data = build_fixed_response(info)
        return success_response(response_data)
    except:
        return error_response("Invalid query_type index", 400)

@app.route("/playlist")
def playlist():
    check = validate_key()
    if check: return check

    link = request.args.get("link")
    limit = int(request.args.get("limit", "10"))
    if not link:
        return error_response("Missing 'link' parameter")

    playlist_id = extract_playlist_id(link)
    if not playlist_id:
        return error_response("Invalid playlist link")

    playlist_url = f"https://www.googleapis.com/youtube/v3/playlistItems?part=contentDetails&maxResults={limit}&playlistId={playlist_id}&key={YOUTUBE_DATA_API_KEY}"
    response = requests.get(playlist_url)
    result = response.json()
    if "items" not in result:
        return error_response("Playlist not found")

    video_ids = [item["contentDetails"]["videoId"] for item in result["items"]]
    return success_response({"video_ids": video_ids})

@app.route("/youtube")
def get_stream():
    check = validate_key()
    if check: return check

    query = request.args.get("query")
    is_video = request.args.get("video", "false").lower() == "true"
    if not query:
        return error_response("Missing 'query' parameter")

    search_url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&q={query}&key={YOUTUBE_DATA_API_KEY}"
    response = requests.get(search_url)
    result = response.json()

    if "items" not in result or not result["items"]:
        return error_response("No results found")

    try:
        selected = result["items"][0]
        video_id = selected["id"]["videoId"]
        info = fetch_video_info(video_id)
        if not info:
            return error_response("Video not found")

        stream_url = f"https://www.youtube.com/watch?v={video_id}"
        stream_type = "Video" if is_video else "Audio"

        response_data = build_fixed_response(info, stream_url, stream_type)
        return success_response(response_data)
    except Exception as e:
        return error_response(str(e), 500)

@app.route("/formats")
def formats():
    check = validate_key()
    if check: return check

    link = request.args.get("link")
    if not link:
        return error_response("Missing 'link' parameter")

    try:
        video_id = extract_video_id(link)
        if not video_id:
            return error_response("Invalid YouTube link")

        info = fetch_video_info(video_id)
        if not info:
            return error_response("Video not found")

        formats_available = [{
            "format": "mp4",
            "ext": "mp4",
            "format_note": "HD"
        }]
        return success_response({"formats": formats_available})
    except Exception as e:
        return error_response(str(e), 500)

def extract_video_id(url):
    import re
    regex = r"(?:v=|youtu\.be/|embed/)([a-zA-Z0-9_-]{11})"
    match = re.search(regex, url)
    return match.group(1) if match else None

def extract_playlist_id(url):
    import re
    regex = r"(?:list=)([a-zA-Z0-9_-]+)"
    match = re.search(regex, url)
    return match.group(1) if match else None

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1470)
