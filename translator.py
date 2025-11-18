from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import tempfile
import subprocess
import json
from pathlib import Path
import uuid
from threading import Thread
import time

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend requests

# Store processing status for each job
processing_jobs = {}

# Configuration
UPLOAD_FOLDER = tempfile.mkdtemp()
MAX_VIDEO_DURATION = 3600  # 60 minutes in seconds
CHUNK_DURATION = 600  # 10 minutes per chunk

def download_youtube_video(url, output_path):
    """Download YouTube video using yt-dlp"""
    try:
        cmd = [
            'yt-dlp',
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '--merge-output-format', 'mp4',
            '-o', output_path,
            url
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"Error downloading video: {e}")
        return False

def get_video_duration(video_path):
    """Get video duration in seconds using ffprobe"""
    try:
        cmd = [
            'ffprobe',
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'json',
            video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(result.stdout)
        return float(data['format']['duration'])
    except Exception as e:
        print(f"Error getting duration: {e}")
        return 0

def extract_audio(video_path, audio_path):
    """Extract audio from video"""
    try:
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-vn',
            '-acodec', 'libmp3lame',
            '-q:a', '2',
            audio_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return False

def detect_language(audio_path):
    """Detect language from audio using Whisper"""
    try:
        # Using Whisper for language detection
        cmd = [
            'whisper',
            audio_path,
            '--model', 'base',
            '--language', 'auto',
            '--task', 'transcribe',
            '--output_format', 'json',
            '--output_dir', tempfile.gettempdir()
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Read the output JSON to get detected language
        json_path = Path(audio_path).with_suffix('.json')
        if json_path.exists():
            with open(json_path, 'r') as f:
                data = json.load(f)
                return data.get('language', 'en')
        return 'en'
    except Exception as e:
        print(f"Error detecting language: {e}")
        return 'en'

def transcribe_audio(audio_path, language='auto'):
    """Transcribe audio using Whisper"""
    try:
        output_dir = tempfile.mkdtemp()
        cmd = [
            'whisper',
            audio_path,
            '--model', 'medium',
            '--language', language if language != 'auto' else '',
            '--task', 'transcribe',
            '--output_format', 'srt',
            '--output_dir', output_dir
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        
        # Find the generated SRT file
        srt_files = list(Path(output_dir).glob('*.srt'))
        if srt_files:
            return str(srt_files[0])
        return None
    except Exception as e:
        print(f"Error transcribing audio: {e}")
        return None

def translate_srt(srt_path, target_lang='hi'):
    """Translate SRT subtitles (placeholder - would need actual translation API)"""
    # In production, use Google Translate API, DeepL, or similar
    # For now, returning the same file as placeholder
    try:
        # This is where you'd integrate with translation API
        # For demo purposes, we'll just copy the file
        translated_path = srt_path.replace('.srt', f'_{target_lang}.srt')
        
        # Placeholder: In real implementation, parse SRT and translate each subtitle
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        with open(translated_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        return translated_path
    except Exception as e:
        print(f"Error translating SRT: {e}")
        return None

def generate_tts_audio(srt_path, output_audio_path, target_lang='hi'):
    """Generate TTS audio from translated subtitles"""
    try:
        # Using gTTS for text-to-speech (basic implementation)
        # In production, use better TTS like Azure, Google Cloud TTS, or ElevenLabs
        from gtts import gTTS
        import pysrt
        
        subs = pysrt.open(srt_path)
        audio_segments = []
        
        for i, sub in enumerate(subs):
            text = sub.text.replace('\n', ' ')
            tts = gTTS(text=text, lang=target_lang[:2])
            segment_path = f"{output_audio_path}_{i}.mp3"
            tts.save(segment_path)
            audio_segments.append((segment_path, sub.start.ordinal, sub.end.ordinal))
        
        return audio_segments
    except Exception as e:
        print(f"Error generating TTS: {e}")
        return []

def merge_audio_video(video_path, audio_segments, output_path):
    """Merge dubbed audio with video"""
    try:
        # Create a complex filter for audio mixing
        # This is simplified - real lip-sync would need sophisticated processing
        
        # For now, we'll replace the entire audio track
        temp_audio = os.path.join(tempfile.gettempdir(), f"dubbed_{uuid.uuid4()}.mp3")
        
        # Concatenate all audio segments (simplified approach)
        # In production, use precise timing from SRT
        filter_complex = []
        for i, (segment_path, start, end) in enumerate(audio_segments):
            filter_complex.append(f"[{i}:a]")
        
        cmd = [
            'ffmpeg',
            '-i', video_path,
            '-i', audio_segments[0][0] if audio_segments else video_path,
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-map', '0:v:0',
            '-map', '1:a:0',
            '-shortest',
            output_path
        ]
        
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"Error merging audio/video: {e}")
        return False

def split_video(video_path, chunk_duration=600):
    """Split video into chunks"""
    try:
        duration = get_video_duration(video_path)
        chunks = []
        
        for i, start in enumerate(range(0, int(duration), chunk_duration)):
            chunk_path = video_path.replace('.mp4', f'_chunk_{i}.mp4')
            cmd = [
                'ffmpeg',
                '-i', video_path,
                '-ss', str(start),
                '-t', str(chunk_duration),
                '-c', 'copy',
                chunk_path
            ]
            subprocess.run(cmd, check=True, capture_output=True)
            chunks.append(chunk_path)
        
        return chunks
    except Exception as e:
        print(f"Error splitting video: {e}")
        return []

def merge_video_chunks(chunk_paths, output_path):
    """Merge video chunks back together"""
    try:
        # Create concat file
        concat_file = os.path.join(tempfile.gettempdir(), f"concat_{uuid.uuid4()}.txt")
        with open(concat_file, 'w') as f:
            for chunk in chunk_paths:
                f.write(f"file '{chunk}'\n")
        
        cmd = [
            'ffmpeg',
            '-f', 'concat',
            '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',
            output_path
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        return True
    except Exception as e:
        print(f"Error merging chunks: {e}")
        return False

def process_video_job(job_id, video_url, target_lang):
    """Main processing function that runs in background"""
    try:
        # Update status
        processing_jobs[job_id]['status'] = 'downloading'
        processing_jobs[job_id]['progress'] = 10
        
        # Download video
        video_path = os.path.join(UPLOAD_FOLDER, f"{job_id}.mp4")
        if not download_youtube_video(video_url, video_path):
            raise Exception("Failed to download video")
        
        # Check duration
        processing_jobs[job_id]['status'] = 'checking_duration'
        processing_jobs[job_id]['progress'] = 20
        duration = get_video_duration(video_path)
        
        if duration > MAX_VIDEO_DURATION:
            raise Exception(f"Video too long ({duration/60:.1f} minutes). Maximum is 60 minutes.")
        
        # Determine if chunking is needed
        need_chunking = duration > CHUNK_DURATION
        
        if need_chunking:
            processing_jobs[job_id]['message'] = 'Video longer than 10 minutes, splitting into chunks...'
            chunks = split_video(video_path, CHUNK_DURATION)
        else:
            chunks = [video_path]
        
        processed_chunks = []
        
        # Process each chunk
        for i, chunk_path in enumerate(chunks):
            chunk_progress = 20 + (60 * (i / len(chunks)))
            
            # Extract audio
            processing_jobs[job_id]['status'] = f'processing_chunk_{i+1}'
            processing_jobs[job_id]['progress'] = chunk_progress + 5
            audio_path = chunk_path.replace('.mp4', '.mp3')
            extract_audio(chunk_path, audio_path)
            
            # Detect language (only for first chunk)
            if i == 0:
                processing_jobs[job_id]['status'] = 'detecting_language'
                processing_jobs[job_id]['progress'] = chunk_progress + 10
                detected_lang = detect_language(audio_path)
                processing_jobs[job_id]['detected_language'] = detected_lang
            
            # Transcribe
            processing_jobs[job_id]['status'] = f'transcribing_chunk_{i+1}'
            processing_jobs[job_id]['progress'] = chunk_progress + 20
            srt_path = transcribe_audio(audio_path, detected_lang)
            
            # Translate
            processing_jobs[job_id]['status'] = f'translating_chunk_{i+1}'
            processing_jobs[job_id]['progress'] = chunk_progress + 30
            translated_srt = translate_srt(srt_path, target_lang)
            
            # Generate TTS
            processing_jobs[job_id]['status'] = f'generating_audio_chunk_{i+1}'
            processing_jobs[job_id]['progress'] = chunk_progress + 40
            audio_segments = generate_tts_audio(translated_srt, 
                                               chunk_path.replace('.mp4', '_tts.mp3'), 
                                               target_lang)
            
            # Merge audio/video
            processing_jobs[job_id]['status'] = f'merging_chunk_{i+1}'
            processing_jobs[job_id]['progress'] = chunk_progress + 50
            output_chunk = chunk_path.replace('.mp4', '_dubbed.mp4')
            merge_audio_video(chunk_path, audio_segments, output_chunk)
            processed_chunks.append(output_chunk)
        
        # Merge chunks if needed
        if need_chunking:
            processing_jobs[job_id]['status'] = 'merging_chunks'
            processing_jobs[job_id]['progress'] = 90
            final_output = os.path.join(UPLOAD_FOLDER, f"{job_id}_final.mp4")
            merge_video_chunks(processed_chunks, final_output)
        else:
            final_output = processed_chunks[0]
        
        # Complete
        processing_jobs[job_id]['status'] = 'completed'
        processing_jobs[job_id]['progress'] = 100
        processing_jobs[job_id]['output_file'] = final_output
        
    except Exception as e:
        processing_jobs[job_id]['status'] = 'error'
        processing_jobs[job_id]['error'] = str(e)
        print(f"Error processing job {job_id}: {e}")

@app.route('/api/process', methods=['POST'])
def process_video():
    """Start video processing"""
    data = request.json
    video_url = data.get('video_url')
    target_lang = data.get('target_lang', 'hi')
    
    if not video_url:
        return jsonify({'error': 'No video URL provided'}), 400
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Initialize job status
    processing_jobs[job_id] = {
        'status': 'queued',
        'progress': 0,
        'message': 'Job queued'
    }
    
    # Start processing in background thread
    thread = Thread(target=process_video_job, args=(job_id, video_url, target_lang))
    thread.start()
    
    return jsonify({'job_id': job_id})

@app.route('/api/status/<job_id>', methods=['GET'])
def get_status(job_id):
    """Get processing status"""
    if job_id not in processing_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify(processing_jobs[job_id])

@app.route('/api/download/<job_id>', methods=['GET'])
def download_video(job_id):
    """Download processed video"""
    if job_id not in processing_jobs:
        return jsonify({'error': 'Job not found'}), 404
    
    job = processing_jobs[job_id]
    
    if job['status'] != 'completed':
        return jsonify({'error': 'Video not ready'}), 400
    
    output_file = job.get('output_file')
    if not output_file or not os.path.exists(output_file):
        return jsonify({'error': 'Output file not found'}), 404
    
    return send_file(output_file, 
                     as_attachment=True, 
                     download_name=f'dubbed_video_{job_id}.mp4',
                     mimetype='video/mp4')

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy'})

if __name__ == '__main__':
    # Check for required dependencies
    required_tools = ['ffmpeg', 'ffprobe', 'yt-dlp', 'whisper']
    for tool in required_tools:
        if subprocess.run(['which', tool], capture_output=True).returncode != 0:
            print(f"Warning: {tool} not found. Please install it.")
    
    app.run(host='0.0.0.0', port=5000, debug=True)