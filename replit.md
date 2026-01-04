# Highrise Music Bot

## Overview

This is a music bot for the Highrise virtual world platform. The bot connects to a Highrise room and provides music playback functionality, allowing users to request songs from YouTube, manage playlists, and control playback through chat commands. The bot uses FFmpeg for audio processing and yt-dlp for downloading YouTube audio.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Core Components

1. **Bot Framework**: Built on the `highrise-bot-sdk`, which provides the connection layer to Highrise rooms and handles user interactions through chat messages.

2. **Music Playback Engine**:
   - **YouTube Integration**: Uses `yt-dlp` (and `pytube` as fallback) to extract and download audio from YouTube videos
   - **Audio Processing**: FFmpeg handles audio encoding and streaming
   - **Queue System**: Songs are managed in a queue stored in `song_queue.json`

3. **Entry Points**:
   - `main.py`: Simple bot launcher for single instance
   - `reconnect.py`: Advanced launcher with auto-reconnection, FFmpeg process cleanup, and error recovery

### Data Storage

All data is stored in JSON files (no database):
- `PLAYLIST_FILE.json`: User-created playlists with songs, durations, and metadata
- `song_queue.json`: Current playback queue
- `current_song.json`: Currently playing song state
- `musicbot_pos.json`: Bot position, admin list, and audio effect toggles (nightcore/daycore)
- `song_stats.json`: Song play statistics
- `bot_log.json`: Logging configuration

### Permission System

- **Owners**: Hardcoded set of usernames with full control (`7o__o`, `3amo__o`, `imkimo`, `yolyos`)
- **Admins**: Stored in `musicbot_pos.json`, can be managed by owners

### Audio Effects

The bot supports audio modifications:
- Nightcore mode (faster/higher pitch)
- Daycore mode (slower/lower pitch)

### Process Management

- FFmpeg processes are spawned for audio streaming
- `reconnect.py` includes cleanup logic to terminate orphaned FFmpeg processes using `psutil`
- Temporary audio files are cleaned up on restart

## External Dependencies

### Third-Party Services
- **YouTube**: Primary source for music content via yt-dlp extraction
- **Highrise Platform**: Virtual world platform where the bot operates (requires room_id and bot_token)

### Key Libraries
- `highrise-bot-sdk`: Official SDK for Highrise bot development
- `yt-dlp`: YouTube content extraction (modern youtube-dl fork)
- `pytube`: Alternative YouTube library
- `ffmpeg`: System dependency for audio processing (must be installed on system)
- `psutil`: Process management for FFmpeg cleanup
- `pydub`: Audio manipulation

### Authentication
- Bot authentication via `bot_token` (API token from Highrise)
- Room connection via `room_id` (target Highrise room identifier)
- Credentials are hardcoded in entry point files (should be moved to environment variables for security)