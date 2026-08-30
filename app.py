from flask import Flask, render_template, request, jsonify, send_file
import yt_dlp
import os
import re
from pathlib import Path

app = Flask(__name__)

# Pasta para downloads temporários
DOWNLOAD_FOLDER = os.path.join(os.getcwd(), 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

def sanitize_filename(filename):
    """Remove caracteres inválidos do nome do arquivo"""
    return re.sub(r'[<>:"/\\|?*]', '', filename)

def get_video_formats(info):
    """Extrai formatos de vídeo disponíveis"""
    formats = []
    seen_qualities = set()

    for f in info.get('formats', []):
        if f.get('vcodec') != 'none':
            height = f.get('height')
            if height and height not in seen_qualities:
                seen_qualities.add(height)
                filesize = f.get('filesize') or f.get('filesize_approx', 0)
                formats.append({
                    'quality': f'{height}p',
                    'format': f.get('ext', 'mp4').upper(),
                    'size': f'{filesize / (1024*1024):.1f} MB' if filesize else 'N/A',
                    'format_id': f.get('format_id')
                })

    formats.sort(key=lambda x: int(x['quality'].replace('p', '')), reverse=True)
    return formats[:6]

def get_audio_formats(info):
    """Extrai formatos de áudio disponíveis"""
    audio_formats = []
    for f in info.get('formats', []):
        if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
            abr = f.get('abr', 0)
            if abr:
                filesize = f.get('filesize') or f.get('filesize_approx', 0)
                audio_formats.append({
                    'quality': f'{int(abr)}kbps',
                    'format': 'MP3',
                    'size': f'{filesize / (1024*1024):.1f} MB' if filesize else 'N/A',
                    'format_id': f.get('format_id')
                })

    audio_formats.sort(key=lambda x: int(x['quality'].replace('kbps', '')), reverse=True)
    return audio_formats[:3]

def handle_single_video(info, url):
    """Processa informações de um único vídeo"""
    # Obter formatos completos
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'age_limit': None,
        'http_headers': {
            'User-Agent': 'com.google.android.youtube/19.02.39 (Linux; U; Android 14) gzip',
            'Accept-Language': 'en-US,en;q=0.9',
        },
        'extractor_args': {
            'youtube': {
                'player_client': ['android'],
            }
        },
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        full_info = ydl.extract_info(url, download=False)

        return jsonify({
            'success': True,
            'type': 'video',
            'title': full_info.get('title', 'Sem título'),
            'duration': full_info.get('duration', 0),
            'views': full_info.get('view_count', 0),
            'thumbnail': full_info.get('thumbnail', ''),
            'formats': get_video_formats(full_info),
            'audio_formats': get_audio_formats(full_info)
        })

def handle_playlist(info, url):
    """Processa informações de uma playlist"""
    playlist_title = info.get('title', 'Playlist sem título')
    entries = info.get('entries', [])

    videos = []
    for idx, entry in enumerate(entries[:20]):  # Limitar a 20 vídeos
        if entry:
            videos.append({
                'index': idx + 1,
                'id': entry.get('id', ''),
                'title': entry.get('title', 'Sem título'),
                'duration': entry.get('duration', 0),
                'thumbnail': entry.get('thumbnail', ''),
                'url': entry.get('url', f"https://www.youtube.com/watch?v={entry.get('id', '')}")
            })

    return jsonify({
        'success': True,
        'type': 'playlist',
        'playlist_title': playlist_title,
        'playlist_count': len(entries),
        'videos': videos
    })

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_video_info', methods=['POST'])
def get_video_info():
    """Obtém informações do vídeo ou playlist do YouTube"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()

        if not url:
            return jsonify({'error': 'URL não fornecida'}), 400

        # Configuração do yt-dlp para obter informações
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'age_limit': None,
            'http_headers': {
                'User-Agent': 'com.google.android.youtube/19.02.39 (Linux; U; Android 14) gzip',
                'Accept-Language': 'en-US,en;q=0.9',
            },
            'extractor_args': {
                'youtube': {
                    'player_client': ['android'],
                }
            },
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            # Verificar se é uma playlist
            if 'entries' in info:
                return handle_playlist(info, url)

            # Se for vídeo único, processar normalmente
            return handle_single_video(info, url)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download():
    """Baixa o vídeo do YouTube"""
    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        format_id = data.get('format_id', '')
        download_type = data.get('type', 'video')

        if not url:
            return jsonify({'error': 'URL não fornecida'}), 400

        # Configuração do yt-dlp para download
        if download_type == 'audio':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
                'http_headers': {
                    'User-Agent': 'com.google.android.youtube/19.02.39 (Linux; U; Android 14) gzip',
                    'Accept-Language': 'en-US,en;q=0.9',
                },
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android'],
                    }
                },
            }
        else:
            if format_id:
                ydl_opts = {
                    'format': f'{format_id}+bestaudio/best',
                    'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                    'merge_output_format': 'mp4',
                    'quiet': True,
                    'http_headers': {
                        'User-Agent': 'com.google.android.youtube/19.02.39 (Linux; U; Android 14) gzip',
                        'Accept-Language': 'en-US,en;q=0.9',
                    },
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android'],
                        }
                    },
                }
            else:
                ydl_opts = {
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                    'merge_output_format': 'mp4',
                    'quiet': True,
                    'http_headers': {
                        'User-Agent': 'com.google.android.youtube/19.02.39 (Linux; U; Android 14) gzip',
                        'Accept-Language': 'en-US,en;q=0.9',
                    },
                    'extractor_args': {
                        'youtube': {
                            'player_client': ['android'],
                        }
                    },
                }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # Se for áudio, o arquivo terá extensão .mp3
            if download_type == 'audio':
                filename = filename.rsplit('.', 1)[0] + '.mp3'

            if os.path.exists(filename):
                return send_file(
                    filename,
                    as_attachment=True,
                    download_name=os.path.basename(filename)
                )
            else:
                return jsonify({'error': 'Arquivo não encontrado'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
