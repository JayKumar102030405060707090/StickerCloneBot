from flask import Flask, request, jsonify, send_file
import yt_dlp
import uuid
import os

app = Flask(__name__)

API_KEY = "1a873582a7c83342f961cc0a177b2b26"
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@app.route('/youtube')
def youtube_api():
    try:
        if request.args.get('api_key') != API_KEY:
            return jsonify({"error": "Invalid API Key"}), 403

        query = request.args.get('query')
        is_video = request.args.get('video', 'false').lower() == 'true'
        if not query:
            return jsonify({"error": "Missing 'query' parameter"}), 400

        file_id = str(uuid.uuid4())
        ext = 'mp4' if is_video else 'mp3'
        filename = f"{file_id}.{ext}"
        output_path = os.path.join(DOWNLOAD_DIR, filename)

        # yt-dlp options
        ydl_opts = {
            'format': 'bestvideo[height<=720]+bestaudio/best' if is_video else 'bestaudio/best',
            'outtmpl': output_path,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4' if is_video else 'mp3',
        }

        if not is_video:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}" if 'youtu' not in query else query, download=True)
            if 'entries' in info:
                info = info['entries'][0]

        # Confirm file was saved (may be renamed slightly by yt-dlp)
        saved_file = None
        for f in os.listdir(DOWNLOAD_DIR):
            if f.startswith(file_id) and f.endswith(ext):
                saved_file = os.path.join(DOWNLOAD_DIR, f)
                break

        if not saved_file or not os.path.exists(saved_file):
            return jsonify({"error": "File not saved"}), 500

        response = {
            "id": info['id'],
            "title": info.get('title'),
            "channel": info.get('uploader'),
            "duration": info.get('duration'),
            "views": info.get('view_count'),
            "thumbnail": info['thumbnails'][-1]['url'] if info.get('thumbnails') else '',
            "link": f"https://www.youtube.com/watch?v={info['id']}",
            "stream_url": f"http://{request.host}/stream/{os.path.basename(saved_file)}",
            "stream_type": "Video" if is_video else "Audio"
        }

        return jsonify(response)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/stream/<filename>')
def stream(filename):
    file_path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.isfile(file_path):
        return send_file(file_path, as_attachment=False)
    return jsonify({"error": "File not found"}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=1470)
