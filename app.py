from flask import Flask, render_template, request, jsonify, send_file, Response
import yt_dlp
import os
import re
from pathlib import Path

# Try to load cookies from browser environment
COOKIES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cookies.txt')

def get_ydl_opts(url=None):
    """Configura yt-dlp com múltiplas estratégias para evitar bloqueio do YouTube"""
    # No Render, usar /tmp para arquivos temporários (única pasta gravável)
    if os.environ.get('RENDER'):
        cookies_path = '/tmp/cookies.txt'
        # Copiar cookies para /tmp se existir no diretório do app
        if os.path.exists(COOKIES_FILE) and not os.path.exists(cookies_path):
            import shutil
            shutil.copy(COOKIES_FILE, cookies_path)
    else:
        cookies_path = COOKIES_FILE

    has_cookies = os.path.exists(cookies_path)

    base_opts = {
        'quiet': False,  # Mostrar avisos para debug
        'no_warnings': False,
        'extractor_args': {
            'youtube': {
                # Sempre usar múltiplos clients - fallback automático se um falhar
                'player_client': ['ios', 'android', 'web'],
            }
        },
        'socket_timeout': 60,
        'retries': 5,
        'fragment_retries': 5,
    }

    # Sempre tentar usar cookies se existir (mesmo que expirados, ajuda)
    if has_cookies:
        base_opts['cookiefile'] = cookies_path
        print(f'[DEBUG] Usando cookies de: {cookies_path}')
    else:
        print(f'[DEBUG] Cookies não encontrados em: {cookies_path}')

    return base_opts

app = Flask(__name__)

# Pasta para downloads temporários
DOWNLOAD_FOLDER = os.path.join(os.getcwd(), 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

@app.route('/robots.txt')
def robots_txt():
    """Serve o arquivo robots.txt para crawlers"""
    robots_content = """User-agent: *
Allow: /
Disallow: /downloads/
Disallow: /get_video_info
Disallow: /download

Sitemap: https://tubempx.com/sitemap.xml
"""
    return Response(robots_content, mimetype='text/plain')

@app.route('/sitemap.xml')
def sitemap_xml():
    """Serve o sitemap.xml para crawlers"""
    sitemap_content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>https://tubempx.com/</loc>
    <lastmod>2026-08-30</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>"""
    return Response(sitemap_content, mimetype='application/xml')

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
    # Usa o info já extraído - não fazer extract_info() de novo!
    return jsonify({
        'success': True,
        'type': 'video',
        'title': info.get('title', 'Sem título'),
        'duration': info.get('duration', 0),
        'views': info.get('view_count', 0),
        'thumbnail': info.get('thumbnail', ''),
        'formats': get_video_formats(info),
        'audio_formats': get_audio_formats(info)
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
        ydl_opts = get_ydl_opts(url)

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            # Verificar se é uma playlist
            if 'entries' in info:
                return handle_playlist(info, url)

            # Se for vídeo único, processar normalmente
            return handle_single_video(info, url)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/cookies')
def admin_cookies():
    """Página de upload de cookies"""
    return send_file('upload_cookies.html')

@app.route('/upload_cookies', methods=['POST'])
def upload_cookies():
    """Endpoint para fazer upload do arquivo cookies.txt (protegido por senha)"""
    try:
        # Verificar senha de admin (defina uma senha forte!)
        admin_password = os.environ.get('ADMIN_PASSWORD', 'mudar_senha_forte_aqui')
        provided_password = request.form.get('password', '')

        if provided_password != admin_password:
            return jsonify({'error': 'Senha incorreta'}), 403

        # Verificar se o arquivo foi enviado
        if 'file' not in request.files:
            return jsonify({'error': 'Nenhum arquivo enviado'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Arquivo vazio'}), 400

        # Salvar o arquivo cookies.txt no diretório principal
        file.save(COOKIES_FILE)

        # No Render, também salvar em /tmp (única pasta gravável)
        if os.environ.get('RENDER'):
            tmp_cookies = '/tmp/cookies.txt'
            file.seek(0)
            with open(tmp_cookies, 'wb') as f:
                f.write(file.read())
            return jsonify({
                'success': True,
                'message': f'Cookies salvos! App: {COOKIES_FILE}, Tmp: {tmp_cookies}'
            })

        return jsonify({'success': True, 'message': 'Cookies salvos com sucesso!'})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/download', methods=['POST'])
def download():
    """Baixa o vídeo do YouTube e faz streaming direto para o usuário"""
    import glob
    import threading

    try:
        data = request.get_json()
        url = data.get('url', '').strip()
        format_id = data.get('format_id', '')
        download_type = data.get('type', 'video')

        if not url:
            return jsonify({'error': 'URL não fornecida'}), 400

        # Garantir que a pasta de downloads existe
        os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

        ydl_opts = get_ydl_opts(url)

        if download_type == 'audio':
            ydl_opts.update({
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
            })
        else:
            if format_id:
                ydl_opts.update({
                    'format': f'{format_id}+bestaudio[ext=m4a]/{format_id}/best[ext=mp4]/best',
                    'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                    'merge_output_format': 'mp4',
                })
            else:
                ydl_opts.update({
                    'format': 'best[ext=mp4]/best',
                    'outtmpl': os.path.join(DOWNLOAD_FOLDER, '%(title)s.%(ext)s'),
                })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)

            # Se for áudio, o arquivo terá extensão .mp3
            if download_type == 'audio':
                base = filename.rsplit('.', 1)[0]
                filename = base + '.mp3'

            # Se o arquivo exato não existir, procurar por arquivos com mesmo nome base
            if not os.path.exists(filename):
                base = os.path.splitext(filename)[0]
                matches = glob.glob(f'{base}.*')
                if matches:
                    filename = matches[0]

            if not os.path.exists(filename):
                return jsonify({'error': f'Arquivo não encontrado após download: {os.path.basename(filename)}'}), 404

            # Enviar arquivo e agendar limpeza após envio
            response = send_file(
                filename,
                as_attachment=True,
                download_name=os.path.basename(filename)
            )

            # Limpar arquivo temporário após envio (sem bloquear a resposta)
            def cleanup(path):
                try:
                    if os.path.exists(path):
                        os.remove(path)
                except:
                    pass

            threading.Timer(30, cleanup, args=[filename]).start()

            return response

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
