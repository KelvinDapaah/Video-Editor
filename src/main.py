import sys
import os
import yt_dlp
import shutil

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

def download_pinterest_video(url, output_folder="downloads"):
    """
    Downloads a Pinterest video.
    If FFmpeg is available (local or system), it merges high-quality video and audio.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    ffmpeg_path = get_ffmpeg_path()

    if ffmpeg_path:
        print(f"✅ FFmpeg detected at: {ffmpeg_path}")
        print("Downloading merged high-quality video with audio...")
        ydl_opts = {
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'outtmpl': f'{output_folder}/%(title)s.%(ext)s',
            'ffmpeg_location': ffmpeg_path, # Tell yt-dlp exactly where the exe is
            'quiet': False,
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
            'format': 'bestvideo/best',
            'outtmpl': f'{output_folder}/%(title)s_VIDEO.%(ext)s',
            'allow_unplayable_formats': True,
        }

        audio_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{output_folder}/%(title)s_AUDIO.%(ext)s',
            'allow_unplayable_formats': True,
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

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python main.py <Pinterest_URL>")
        sys.exit(1)

    # Handle cases where we are running from a different directory
    # Ensure we are looking for the bin folder relative to this script
    os.chdir(os.path.dirname(os.path.abspath(__file__)) if '__file__' in locals() else os.getcwd())
    # Since we are in src/main.py, we need to go up one level to reach /bin
    os.chdir("..")

    video_url = sys.argv[1]
    if not download_pinterest_video(video_url):
        sys.exit(1)
