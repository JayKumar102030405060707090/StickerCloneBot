
from flask import Flask, request, jsonify, send_file
import yt_dlp
import uuid
import os
import re
import time
import threading
import tempfile
import traceback
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
streams = {}
executor = ThreadPoolExecutor(max_workers=4)

# Configuration
CACHE_EXPIRY = 3600
DOWNLOAD_DIR = tempfile.mkdtemp(prefix="yt_stream_")
API_KEY = "1a873582a7c83342f961cc0a177b2b26"

def sanitize_filename(filename):
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def time_to_seconds(time_str):
    return sum(int(x) * 60**i for i, x in enumerate(reversed(str(time_str).split(":"))))

def extract_info(query, download=False, ydl_opts={}):
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(query, download=download)
    except Exception:
        return None

def download_media(video_id, stream_id, video=False):
    try:
        temp_file = os.path.join(DOWNLOAD_DIR, f"{stream_id}.{'mp4' if video else 'mp3'}")
        ydl_opts = {
            'quiet': True,
            'outtmpl': temp_file,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best' if video else 'bestaudio/best',
            'extractaudio': not video,
            'audioformat': 'mp3',
            'noplaylist': True,
            'retries': 3,
            'continuedl': True,
        }
        info = extract_info(video_id, download=True, ydl_opts=ydl_opts)
        return temp_file if info else None
    except Exception as e:
        print(f"Download failed: {str(e)}")
        return None

@app.route("/youtube", methods=["GET"])
def youtube_api():
    try:
        query = request.args.get("query", "").strip()
        video = request.args.get("video", "false").lower() == "true"
        api_key = request.args.get("api_key", "").strip()

        if not query:
            return jsonify({"error": "Missing query parameter"}), 400
        if api_key != API_KEY:
            return jsonify({"error": "Invalid API key"}), 401

        if 'youtube.com/watch?v=' in query or 'youtu.be/' in query:
            video_id = query.split('v=')[-1].split('&')[0] if 'v=' in query else query.split('/')[-1]
        else:
            opts = {'quiet': True, 'noplaylist': True, 'extract_flat': True, 'default_search': 'ytsearch'}
            search_result = extract_info(f"ytsearch:{query}", download=False, ydl_opts=opts)
            if not search_result or not search_result.get('entries'):
                return jsonify({"error": "No results found"}), 404
            result = search_result['entries'][0]
            video_id = result['id']

        stream_id = str(uuid.uuid4())
        file_path = download_media(video_id, stream_id, video)
        if not file_path:
            return jsonify({"error": "Failed to download media"}), 500

        streams[stream_id] = {
            'video_id': video_id,
            'video': video,
            'timestamp': time.time(),
            'status': 'ready'
        }

        return jsonify({
            "success": True,
            "stream_id": stream_id,
            "status": "ready",
            "stream_url": f"http://{request.host}/stream/{stream_id}",
            "check_url": f"http://{request.host}/status/{stream_id}"
        })
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route("/formats", methods=["GET"])
def formats():
    query = request.args.get("query", "").strip()
    if not query:
        return jsonify({"error": "Missing query parameter"}), 400
    ydl_opts = {"quiet": True}
    info = extract_info(query, download=False, ydl_opts=ydl_opts)
    if not info:
        return jsonify({"error": "Failed to extract formats"}), 500
    formats = [f for f in info.get("formats", []) if f.get("filesize")]
    return jsonify(formats)

@app.route("/metadata", methods=["GET"])
def metadata():
    query = request.args.get("query", "").strip()
    if not query:
        return jsonify({"error": "Missing query parameter"}), 400
    info = extract_info(query, download=False, ydl_opts={"quiet": True})
    if not info:
        return jsonify({"error": "Failed to extract metadata"}), 500
    return jsonify({
        "id": info.get("id"),
        "title": info.get("title"),
        "duration": info.get("duration"),
        "thumbnail": info.get("thumbnail"),
        "channel": info.get("uploader"),
        "view_count": info.get("view_count"),
        "url": info.get("webpage_url")
    })

@app.route("/playlist", methods=["GET"])
def playlist():
    url = request.args.get("url")
    limit = request.args.get("limit", 10)
    try:
        cmd = f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download {url}"
        result = os.popen(cmd).read().strip().splitlines()
        return jsonify({"videos": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/search", methods=["GET"])
def search():
    query = request.args.get("query", "")
    limit = int(request.args.get("limit", 10))
    opts = {'quiet': True, 'noplaylist': True, 'extract_flat': True, 'default_search': 'ytsearch'}
    result = extract_info(f"ytsearch{limit}:{query}", download=False, ydl_opts=opts)
    if not result:
        return jsonify({"error": "No search results"}), 404
    return jsonify(result.get("entries", []))

@app.route("/validate", methods=["GET"])
def validate():
    url = request.args.get("url", "")
    if re.search(r"(?:youtube.com|youtu.be)", url):
        return jsonify({"valid": True})
    return jsonify({"valid": False})

@app.route("/download", methods=["GET"])
def custom_download():
    query = request.args.get("query")
    format_id = request.args.get("format_id")
    filename = sanitize_filename(request.args.get("filename", str(uuid.uuid4())))
    output_file = os.path.join(DOWNLOAD_DIR, filename)

    ydl_opts = {
        'format': format_id,
        'outtmpl': output_file + ".%(ext)s",
        'quiet': True,
        'noplaylist': True,
    }
    info = extract_info(query, download=True, ydl_opts=ydl_opts)
    if not info:
        return jsonify({"error": "Download failed"}), 500
    filepath = output_file + f".{info.get('ext', 'mp4')}"
    return send_file(filepath, as_attachment=True)

@app.route("/status/<stream_id>")
def status_handler(stream_id):
    if stream_id not in streams:
        return jsonify({"error": "Invalid stream ID"}), 404
    file_path = os.path.join(DOWNLOAD_DIR, f"{stream_id}.{'mp4' if streams[stream_id]['video'] else 'mp3'}")
    if os.path.exists(file_path):
        streams[stream_id]['status'] = 'ready'
        return jsonify({"status": "ready", "stream_url": f"http://{request.host}/stream/{stream_id}"})
    return jsonify({"status": streams[stream_id]['status'], "message": "Download in progress"})

@app.route("/stream/<stream_id>")
def stream_handler(stream_id):
    try:
        if stream_id not in streams:
            return jsonify({"error": "Invalid stream ID"}), 404
        stream_data = streams[stream_id]
        file_path = os.path.join(DOWNLOAD_DIR, f"{stream_id}.{'mp4' if stream_data['video'] else 'mp3'}")
        if not os.path.exists(file_path):
            return jsonify({"status": "downloading", "message": "File not ready yet"}), 425
        streams[stream_id]['timestamp'] = time.time()
        return send_file(file_path, mimetype='video/mp4' if stream_data['video'] else 'audio/mp3',
                         conditional=True, as_attachment=False)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def cleanup():
    while True:
        time.sleep(3600)
        now = time.time()
        expired = [k for k, v in streams.items() if now - v['timestamp'] > CACHE_EXPIRY]
        for k in expired:
            try:
                file_path = os.path.join(DOWNLOAD_DIR, f"{k}.{'mp4' if streams[k]['video'] else 'mp3'}")
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            streams.pop(k, None)

cleanup_thread = threading.Thread(target=cleanup, daemon=True)
cleanup_thread.start()

if __name__ == "__main__":
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=1470, threaded=True)
