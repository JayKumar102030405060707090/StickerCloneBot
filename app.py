from flask import Flask, request, jsonify
from youtubesearchpython import VideosSearch, PlaylistsSearch
import yt_dlp
import os

app = Flask(__name__)
API_KEY = "YOUR_STRONG_KEY_HERE"

# Helper: Extract best stream URL
def get_stream(url, is_video=False, quality="best"):
    ydl_opts = {
        'format': 'bestaudio/best' if not is_video else f'bestvideo[height<={quality}p]+bestaudio/best',
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info['url'] if info else None

@app.route('/stream')
def stream():
    if request.args.get('api_key') != API_KEY:
        return jsonify({"error": "Invalid API key"}), 403
    
    query = request.args.get('query')
    if not query:
        return jsonify({"error": "Query missing"}), 400
    
    # Search if not URL
    if not query.startswith(('http://', 'https://')):
        search = VideosSearch(query, limit=1)
        result = search.result()
        if not result['result']:
            return jsonify({"error": "No results found"}), 404
        query = result['result'][0]['link']
    
    stream_url = get_stream(query, request.args.get('video') == 'true')
    if not stream_url:
        return jsonify({"error": "Failed to fetch stream"}), 500
    
    return jsonify({"stream_url": stream_url, "status": "success"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1470)
