import os
import shutil
import sys

import yt_dlp

def get_ffmpeg_path():
    """
    Returns the path to ffmpeg if it's in the local bin folder or system PATH.
    """
    # 1. Check local bin folder first
    local_bin = os.path.join(os.getcwd(), "bin", "ffmpeg.exe")
    if os.path.exists(local_bin):
        return local_bin

    # 2. Check system PATH
    system_ffmpeg = shutil.which('ffmpeg')
    if system_ffmpeg:
        return system_ffmpeg

    return None

def download_video(url, output_folder="downloads"):
    """
    Downloads a video from a supported URL.
    If FFmpeg is available, it merges high-quality video and audio.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    ffmpeg_path = get_ffmpeg_path()

    if ffmpeg_path:
        print(f"✅ FFmpeg detected at: {ffmpeg_path}")
        print("Downloading merged high-quality video with audio...")
        ydl_opts = {
            'format': 'bv*+ba/b',
            'merge_output_format': 'mp4',
            'outtmpl': f'{output_folder}/%(title)s.%(ext)s',
            'ffmpeg_location': ffmpeg_path, # Tell yt-dlp exactly where the exe is
            'quiet': False,
            'noplaylist': True,
            'retries': 3,
            'fragment_retries': 3,
            'socket_timeout': 30,
            'js_runtimes': {'node': {}},
            'remote_components': {'ejs:github', 'ejs:npm'},
            'extractor_args': {
                'youtube': {
                    'player_client': [
                        'default', 'tv_samsung', 'tv', 'ios', 'android',
                        'android_vr', 'visionos', 'mweb', 'web_embedded', 'web_safari',
                    ],
                },
            },
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                print("\n🏆 TASK COMPLETED: High-quality merged video downloaded successfully!")
                return True
        except Exception as e:
            print(f"❌ Merged download failed: {e}")
    else:
        print("⚠️ FFmpeg NOT detected. Falling back to separate files...")

        video_opts = {
            'format': 'bv*/b',
            'outtmpl': f'{output_folder}/%(title)s_VIDEO.%(ext)s',
            'allow_unplayable_formats': True,
            'noplaylist': True,
            'retries': 3,
        }

        audio_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{output_folder}/%(title)s_AUDIO.%(ext)s',
            'allow_unplayable_formats': True,
            'noplaylist': True,
            'retries': 3,
        }

        try:
            with yt_dlp.YoutubeDL(video_opts) as ydl:
                print("\n🚀 Downloading Video Stream...")
                ydl.download([url])

            with yt_dlp.YoutubeDL(audio_opts) as ydl:
                print("\n🚀 Downloading Audio Stream...")
                ydl.download([url])

            print("\n✅ Video and Audio downloaded as separate files.")
            return True
        except Exception as e:
            print(f"\n🚨 Critical failure: {e}")
            return False


def download_pinterest_video(url, output_folder="downloads"):
    """Backward-compatible name for the generic video downloader."""
    return download_video(url, output_folder)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <VIDEO_URL>")
        sys.exit(1)

    # Handle cases where we are running from a different directory
    # Ensure we are looking for the bin folder relative to this script
    os.chdir(os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd())
    # Since we are in src/main.py, we need to go up one level to reach /bin
    os.chdir("..")

    video_url = sys.argv[1]
    if not download_video(video_url):
        sys.exit(1)
