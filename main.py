from flask import Flask, request, jsonify, Response, send_file
import yt_dlp
import uuid
import os
import re
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor
import tempfile
import traceback

app = Flask(__name__)
streams = {}
executor = ThreadPoolExecutor(max_workers=4)

# Configuration
CACHE_EXPIRY = 3600  # 1 hour
DOWNLOAD_DIR = tempfile.mkdtemp(prefix="yt_stream_")
API_KEY = "1a873582a7c83342f961cc0a177b2b26"

def sanitize_filename(filename):
    """Sanitize filename to remove invalid characters"""
    return re.sub(r'[\\/*?:"<>|]', "", filename)

def download_media(video_id, stream_id, video=False):
    """Download the media file to local storage"""
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
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_id, download=True)
            filename = ydl.prepare_filename(info)
            
            # Rename to our standardized name
            if filename != temp_file:
                os.rename(filename, temp_file)
                
        return temp_file
    except Exception as e:
        print(f"Download failed: {str(e)}")
        return None

@app.route("/youtube", methods=["GET"])
def youtube_api():
    try:
        # Validate parameters
        query = request.args.get("query", "").strip()
        video = request.args.get("video", "false").lower() == "true"
        api_key = request.args.get("api_key", "").strip()
        
        if not query:
            return jsonify({"error": "Missing video URL or ID"}), 400
        
        if api_key != API_KEY:
            return jsonify({"error": "Invalid API key"}), 401

        # Extract video ID
        video_id = None
        if 'youtube.com/watch?v=' in query:
            video_id = query.split('youtube.com/watch?v=')[1].split('&')[0]
        elif 'youtu.be/' in query:
            video_id = query.split('youtu.be/')[1].split('?')[0]
        else:
            video_id = query  # Assume it's already a video ID
            
        if not re.match(r'^[a-zA-Z0-9_-]{11}$', video_id):
            return jsonify({"error": "Invalid YouTube video ID"}), 400

        # Generate unique stream ID
        stream_id = str(uuid.uuid4())
        
        # Start download and wait for completion
        file_path = download_media(video_id, stream_id, video)
        
        if not file_path:
            return jsonify({"error": "Failed to download media"}), 500
        
        # Store stream info
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

@app.route("/status/<stream_id>")
def status_handler(stream_id):
    if stream_id not in streams:
        return jsonify({"error": "Invalid stream ID"}), 404
    
    file_path = os.path.join(DOWNLOAD_DIR, f"{stream_id}.{'mp4' if streams[stream_id]['video'] else 'mp3'}")
    
    if os.path.exists(file_path):
        streams[stream_id]['status'] = 'ready'
        return jsonify({
            "status": "ready",
            "stream_url": f"http://{request.host}/stream/{stream_id}"
        })
    
    return jsonify({
        "status": streams[stream_id]['status'],
        "message": "Download in progress"
    })

@app.route("/stream/<stream_id>")
def stream_handler(stream_id):
    try:
        if stream_id not in streams:
            return jsonify({"error": "Invalid stream ID"}), 404
        
        stream_data = streams[stream_id]
        file_path = os.path.join(DOWNLOAD_DIR, f"{stream_id}.{'mp4' if stream_data['video'] else 'mp3'}")
        
        if not os.path.exists(file_path):
            return jsonify({
                "status": "downloading",
                "message": "File not ready yet",
                "check_url": f"http://{request.host}/status/{stream_id}"
            }), 425
            
        # Update last accessed time
        streams[stream_id]['timestamp'] = time.time()
        
        return send_file(
            file_path,
            mimetype='video/mp4' if stream_data['video'] else 'audio/mp3',
            conditional=True,
            as_attachment=False
        )
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

def cleanup():
    """Clean up old streams and files"""
    while True:
        time.sleep(3600)
        now = time.time()
        
        # Clean stream entries
        expired = [k for k, v in streams.items() if now - v['timestamp'] > CACHE_EXPIRY]
        for k in expired:
            # Delete associated file
            file_path = os.path.join(DOWNLOAD_DIR, f"{k}.{'mp4' if streams[k]['video'] else 'mp3'}")
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
            except:
                pass
            streams.pop(k, None)

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup, daemon=True)
cleanup_thread.start()

if __name__ == "__main__":
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    app.run(host="0.0.0.0", port=1470, threaded=True)
