from pathlib import Path
from typing import Literal, Optional
import shutil
import subprocess
import tempfile
import uuid

import yt_dlp
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

MediaType = Literal["audio", "video", "audio-video"]
TrackType = Literal["main", "overlay"]
OutputFormat = Literal["mp4", "webm", "mp3"]


class Segment(BaseModel):
    url: str = Field(min_length=1)
    media_type: MediaType
    start: float = Field(default=0, ge=0)
    duration: Optional[float] = Field(default=None, gt=0)
    track: TrackType = "main"
    timeline_start: float = Field(default=0, ge=0)


class ComposeRequest(BaseModel):
    segments: list[Segment] = Field(min_length=1)
    output_format: OutputFormat = "mp4"


def cleanup_path(path: Path):
    shutil.rmtree(path, ignore_errors=True) if path.is_dir() else path.unlink(missing_ok=True)


def find_downloaded_file(directory: Path, prefix: str) -> Path:
    files = [path for path in directory.glob(f"{prefix}.*") if path.is_file()]
    if not files:
        raise RuntimeError(f"No media file was downloaded for segment {prefix}.")
    return files[0]


def download_media(segment: Segment, directory: Path, index: int) -> Path:
    prefix = f"segment_{index}"
    template = str(directory / f"{prefix}.%(ext)s")
    if segment.media_type == "audio":
        media_format = "bestaudio/best"
    elif segment.media_type == "video":
        media_format = "bestvideo/best"
    else:
        media_format = "bestvideo+bestaudio/best"

    options = {
        "format": media_format,
        "outtmpl": template,
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(options) as downloader:
            downloader.download([segment.url])
        return find_downloaded_file(directory, prefix)
    except Exception as error:
        raise RuntimeError(f"Unable to download segment {index + 1}: {error}") from error


def run_ffmpeg(arguments: list[str], output: Path):
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *arguments, str(output)],
            check=True,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except FileNotFoundError as error:
        raise RuntimeError("FFmpeg is not installed on the server.") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or "FFmpeg could not process the media."
        raise RuntimeError(detail) from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Media composition timed out.") from error


def media_duration(path: Path) -> float:
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return max(float(result.stdout.strip()), 0.1)
    except (FileNotFoundError, subprocess.CalledProcessError, ValueError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Unable to determine media duration for {path.name}.") from error


def compose_media(request: ComposeRequest, work_dir: Path) -> Path:
    downloaded: list[tuple[int, Segment, Path]] = [
        (index, segment, download_media(segment, work_dir, index))
        for index, segment in enumerate(request.segments)
    ]
    main_segments = [
        (index, segment, path) for index, segment, path in downloaded if segment.track == "main"
    ]
    if not main_segments:
        raise RuntimeError("At least one main timeline segment is required.")

    input_args = []
    for _, _, path in downloaded:
        input_args.extend(["-i", str(path)])

    main_durations = [
        min(segment.duration, media_duration(path) - segment.start)
        if segment.duration
        else media_duration(path) - segment.start
        for _, segment, path in main_segments
    ]
    if any(duration <= 0 for duration in main_durations):
        raise RuntimeError("A segment starts after the end of its downloaded media.")

    filter_parts: list[str] = []
    concat_inputs: list[str] = []
    overlay_audio_inputs: list[str] = []
    video_output = request.output_format != "mp3"

    for main_position, (input_index, segment, path) in enumerate(main_segments):
        duration = main_durations[main_position]
        trim_end = f":duration={duration}"
        if not video_output:
            if segment.media_type in ("audio", "audio-video"):
                filter_parts.append(
                    f"[{input_index}:a]atrim=start={segment.start}{trim_end},"
                    f"asetpts=PTS-STARTPTS[a{main_position}]"
                )
            else:
                filter_parts.append(
                    f"anullsrc=channel_layout=stereo:sample_rate=48000:d={duration},"
                    f"asetpts=PTS-STARTPTS[a{main_position}]"
                )
            concat_inputs.append(f"[a{main_position}]")
            continue
        if segment.media_type == "audio":
            filter_parts.append(
                f"color=c=black:s=1280x720:r=30:d={duration},setpts=PTS-STARTPTS[v{main_position}]"
            )
            filter_parts.append(
                f"[{input_index}:a]atrim=start={segment.start}{trim_end},asetpts=PTS-STARTPTS[a{main_position}]"
            )
        else:
            filter_parts.append(
                f"[{input_index}:v]trim=start={segment.start}{trim_end},"
                f"scale=1280:720:force_original_aspect_ratio=decrease,"
                f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,setpts=PTS-STARTPTS[v{main_position}]"
            )
            if segment.media_type == "video":
                filter_parts.append(
                    f"anullsrc=channel_layout=stereo:sample_rate=48000:d={duration},"
                    f"asetpts=PTS-STARTPTS[a{main_position}]"
                )
            else:
                filter_parts.append(
                    f"[{input_index}:a]atrim=start={segment.start}{trim_end},asetpts=PTS-STARTPTS[a{main_position}]"
                )
        concat_inputs.append(f"[v{main_position}][a{main_position}]")

    if video_output:
        filter_parts.append(
            "".join(concat_inputs) + f"concat=n={len(main_segments)}:v=1:a=1[basev][basea]"
        )
        final_video = "[basev]"
        final_audio = "[basea]"
    else:
        filter_parts.append(
            "".join(concat_inputs) + f"concat=n={len(main_segments)}:v=0:a=1[basea]"
        )
        final_audio = "[basea]"

    for input_index, segment, path in downloaded:
        if segment.track != "overlay":
            continue
        duration = min(segment.duration, media_duration(path) - segment.start) if segment.duration else media_duration(path) - segment.start
        if duration <= 0:
            raise RuntimeError("An overlay starts after the end of its downloaded media.")
        trim_end = f":duration={duration}"
        timeline_start = segment.timeline_start
        if segment.media_type == "audio" or (segment.media_type == "audio-video" and not video_output):
            delay = int(timeline_start * 1000)
            filter_parts.append(
                f"[{input_index}:a]atrim=start={segment.start}{trim_end},"
                f"asetpts=PTS-STARTPTS,adelay={delay}|{delay}[oa{input_index}]"
            )
            overlay_audio_inputs.append(f"[oa{input_index}]")
        elif video_output:
            filter_parts.append(
                f"[{input_index}:v]trim=start={segment.start}{trim_end},"
                f"scale=1280:720:force_original_aspect_ratio=decrease,"
                f"setpts=PTS-STARTPTS+{timeline_start}/TB[ov{input_index}]"
            )
            filter_parts.append(
                f"{final_video}[ov{input_index}]overlay=eof_action=pass[video{input_index}]"
            )
            final_video = f"[video{input_index}]"
            if segment.media_type == "audio-video":
                delay = int(timeline_start * 1000)
                filter_parts.append(
                    f"[{input_index}:a]atrim=start={segment.start}{trim_end},"
                    f"asetpts=PTS-STARTPTS,adelay={delay}|{delay}[oa{input_index}]"
                )
                overlay_audio_inputs.append(f"[oa{input_index}]")

    if overlay_audio_inputs:
        audio_inputs = ["[basea]", *overlay_audio_inputs]
        filter_parts.append(
            "".join(audio_inputs) + f"amix=inputs={len(audio_inputs)}:duration=longest:dropout_transition=2[aout]"
        )
        final_audio = "[aout]"

    output = work_dir / f"edited.{request.output_format}"
    filters = ";".join(filter_parts)
    if request.output_format == "mp3":
        run_ffmpeg(input_args + ["-filter_complex", filters, "-map", final_audio, "-c:a", "libmp3lame", "-b:a", "192k"], output)
    elif request.output_format == "webm":
        run_ffmpeg(
            input_args + ["-filter_complex", filters, "-map", final_video, "-map", final_audio,
                          "-c:v", "libvpx-vp9", "-c:a", "libopus", "-shortest"],
            output,
        )
    else:
        run_ffmpeg(
            input_args + ["-filter_complex", filters, "-map", final_video, "-map", final_audio,
                          "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart",
                          "-shortest"],
            output,
        )
    return output


@app.get("/")
async def root():
    return {"message": "Video editor API is running!"}


@app.get("/download")
async def download_video(url: str, background_tasks: BackgroundTasks):
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    request_dir = Path(tempfile.mkdtemp(prefix="download_", dir=DOWNLOAD_DIR))
    try:
        file_path = download_media(Segment(url=url, media_type="audio-video"), request_dir, 0)
        background_tasks.add_task(cleanup_path, request_dir)
        return FileResponse(path=file_path, filename=f"{file_path.stem}.mp4", media_type="video/mp4")
    except Exception as error:
        cleanup_path(request_dir)
        raise HTTPException(status_code=500, detail=str(error)) from error


@app.post("/compose")
async def compose(request: ComposeRequest, background_tasks: BackgroundTasks):
    request_dir = Path(tempfile.mkdtemp(prefix=f"compose_{uuid.uuid4().hex}_", dir=DOWNLOAD_DIR))
    try:
        output = compose_media(request, request_dir)
        background_tasks.add_task(cleanup_path, request_dir)
        media_type = {
            "mp4": "video/mp4",
            "webm": "video/webm",
            "mp3": "audio/mpeg",
        }[request.output_format]
        return FileResponse(path=output, filename=output.name, media_type=media_type)
    except Exception as error:
        cleanup_path(request_dir)
        raise HTTPException(status_code=500, detail=str(error)) from error
