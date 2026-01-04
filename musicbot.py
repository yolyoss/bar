# Standard library imports
import os
import subprocess
import time
import threading
import json
import random
import string
import glob
import re
import asyncio
import signal
import gc
from concurrent.futures import ThreadPoolExecutor

# Third-party imports
import yt_dlp
import yt_dlp as youtube_dl
from pytube import YouTube
from highrise import BaseBot, User, Position
from highrise.models import GetMessagesRequest

try:
    import psutil
except ImportError:
    psutil = None
    print("⚠️ psutil not available - some cleanup features may be limited")

PLAYLIST_FILE = "PLAYLIST_FILE.json"

class xenoichi(BaseBot):
    def __init__(self):
        super().__init__()

        self.dance = None
        self.current_song = None
        self.song_queue = []
        self.pending_confirmations = {}
        self.currently_playing = False
        self.skip_event = asyncio.Event()
        self.skip_in_progress = False
        self.ffmpeg_process = None
        self.currently_playing_title = None
        self.credits = {} # Credits system disabled
        self.owners = {'7o__o', '3amo__o', 'imkimo', 'yolyos'}
        self.admins = set(self.owners)
        self.bot_pos = None
        self.ctoggle = False # Always disabled now
        self.is_loading = True
        self.play_task = None
        self.play_event = asyncio.Event()
        self.skip_event = asyncio.Event()
        self.song_request_counts = self.load_stats()
        self.current_time = 0

        self.log_file = 'bot_log.json'
        self.logs, self.logging_enabled = self.load_logs()

        self.playlists = {}

        self.nightcore = False
        self.daycore = False

        # Preloading system
        self.next_song_file = None
        self.preload_task = None
        self.preload_lock = asyncio.Lock()

        # Auto-cleanup settings
        self.max_downloads_size_mb = 500  # الحد الأقصى لحجم مجلد downloads بالميجابايت
        self.cleanup_check_interval = 300  # فحص كل 5 دقائق

    async def on_start(self, session_metadata):
        print(" figo is Ready.")
        self.is_loading = True

        if self.logging_enabled:
            self.logs += 1  # Increment logs count by 1
            self.save_logs()  # Save updated logs to the .json file

        self.queue = []
        self.load_playlists()
        self.currently_playing = False

        await self.highrise.chat("Initialization in progress. Please wait.")

        # Load location data and handle bot position
        self.load_loc_data()
        if self.bot_pos:
            await self.highrise.teleport(self.highrise.my_id, self.bot_pos)

        # Terminate any existing stream before restarting
        await self.stop_existing_stream()
        # Clean up any preloading from previous session
        await self.cleanup_preload()
        await asyncio.sleep(3)

        # Reset the skip event and clear any active playback
        self.skip_event.clear()
        self.load_queue()

        # Load the current song if there is one
        self.current_song = self.load_current_song()

        # Add the current song back to the queue as the first song
        if self.currently_playing_title:
            await self.highrise.chat(f"Replaying song due to disconnection: '{self.current_song['title']}'")
            self.song_queue.insert(0, self.current_song)  # Add it to the front of the queue
            await asyncio.sleep(5)

        # Terminate and recreate the playback loop
        if self.play_task and not self.play_task.done():
            print("Terminating the existing playback loop.")
            self.play_task.cancel()
            try:
                await self.play_task
            except asyncio.CancelledError:
                print("Existing playback loop terminated successfully.")

        print("Creating a new playback loop.")
        self.play_task = asyncio.create_task(self.playback_loop())

        # If there are songs in the queue, trigger the playback loop
        if self.song_queue:
            print("Songs found in queue. Triggering playback loop...")
            self.play_event.set()
        else:
            print("No songs found in queue. Playback loop will wait for new songs.")

        # بدء نظام التنظيف التلقائي
        asyncio.create_task(self.auto_cleanup_downloads())

        self.is_loading = False
        await self.highrise.chat("Initialization is complete.")

    async def on_chat(self, user: User, message: str) -> None:

        if message.startswith('-sfx') and user.username in self.admins:

            if self.currently_playing:
                # Notify the user if a song is ongoing
                await self.highrise.send_whisper(user.id, f"@{user.username} You can't add an sfx while a song is playing.")
                return

            elif not self.currently_playing:

                command = message[5:].strip().lower()  # Get the part after '/sfx' and normalize to lowercase
                print(command)

                if command == "nightcore":
                    self.nightcore = True
                    self.daycore = False
                    await self.highrise.send_whisper(user.id, f"\n@{user.username} Nightcore effect selected.")
                    print("nightcore sfx enabled.")

                elif command == "daycore":
                    self.daycore = True
                    self.nightcore = False
                    await self.highrise.send_whisper(user.id, f"\n@{user.username} Daycore effect selected.")
                    print("daycore sfx enabled.")

                elif command == "normal":
                    self.nightcore = False
                    self.daycore = False
                    await self.highrise.send_whisper(user.id, f"\n@{user.username} Normal mode selected.")
                    print("all sfx removed.")

                else:
                    await self.highrise.send_whisper(user.id, f"\n@{user.username} Invalid effect. Use one of the following: nightcore, daycore, normal.")

                self.save_loc_data()

        if message.startswith('-logstoggle') and user.username in self.admins:
            self.logging_enabled = not self.logging_enabled  # Toggle the logging state
            state = "enabled" if self.logging_enabled else "disabled"
            self.save_logs()  # Save the updated state to the .json file
            await self.highrise.chat(f"Logging has been {state}.")

        if message.startswith('-logsclear') and user.username in self.admins:
            self.logs = 0  # Clear the logs count
            self.save_logs()  # Save the cleared logs to the .json file
            await self.highrise.chat("Logs have been cleared.")

        if message.startswith('-stat'):

            try:
                parts = message.split()
                # Check if a username is provided
                if len(parts) > 1 and parts[1].startswith('@'):
                    username = parts[1][1:]  # Remove the '@' to get the username

                    # Calculate the total requests and the top song for the user
                    user_total_requests = 0
                    user_top_song = None
                    user_top_song_count = 0

                    for song, data in self.song_request_counts.items():
                        # Check if the user has requested this song
                        if username in data["users"]:
                            user_total_requests += data["users"][username]
                            if data["users"][username] > user_top_song_count:
                                user_top_song = song
                                user_top_song_count = data["users"][username]

                    # Display stats for the user
                    if user_total_requests > 0:
                        user_top_song_user_count = self.song_request_counts[user_top_song]["users"].get(username, 0)

                        await self.highrise.chat(
                            f"\n🎶 Stats for @{username}:\n\n"
                            f"Total Song Requests: {user_total_requests}\n"
                            f"Top Requested Song: '{user_top_song}'\n"
                            f"Times Requested: {user_top_song_user_count}\n"
                            f"Total Request Count: {user_top_song_count}\n"
                        )
                    else:
                        await self.highrise.chat(f"Stats for @{username} are not available.")

                else:
                    # Extract page number from the message (default to 1 if not specified)
                    page_number = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 1

                    if not self.song_request_counts:
                        await self.highrise.chat("The stats are empty.")
                        return

                    # Sort songs by request count
                    sorted_songs = sorted(self.song_request_counts.items(), key=lambda item: item[1]["count"], reverse=True)

                    # Limit to top 10 songs
                    sorted_songs = sorted_songs[:10]

                    # Paging logic
                    songs_per_page = 2
                    total_songs = len(sorted_songs)
                    total_pages = (total_songs + songs_per_page - 1) // songs_per_page

                    if page_number < 1 or page_number > total_pages:
                        await self.highrise.chat("Invalid page number.")
                        return

                    # Create the stat message for the current page
                    start_index = (page_number - 1) * songs_per_page
                    end_index = min(start_index + songs_per_page, total_songs)
                    stat_message = f"🎵 Top 10 Requested Songs (Page {page_number}/{total_pages}) 🎵\n\n"

                    # Iterate over the songs and add a blank line after every second song
                    song_count = 0
                    for i, (title, data) in enumerate(sorted_songs[start_index:end_index]):
                        stat_message += f"{start_index + i + 1}. {title} - {data['count']} request(s)\n"
                        song_count += 1

                    # Send the message
                    await self.highrise.chat(stat_message)

                    # Suggest the next page if there are more pages
                    if page_number < total_pages:
                        await self.highrise.chat(f"Use '-stat {page_number + 1}' to view the next page.")

            except Exception as e:
                # Handle any error that occurs
                await self.highrise.chat(f"An error occurred: {str(e)}")

        if message.startswith('-ctoggle') and user.username in self.admins:

            self.ctoggle = not self.ctoggle
            status = "enabled" if self.ctoggle else "disabled"
            await self.highrise.chat(f"Credits requirement has been {status}.")
            self.save_loc_data()

        if message.startswith("-refresh"):
            # Check if the user is in the admin list
            if user.username not in self.admins:
                return

            # Allow admins to crash the bot
            await self.highrise.chat("Refreshing the bot. Please wait.")
            await asyncio.sleep(5)

            # Terminate any active FFmpeg stream process before crashing
            if self.ffmpeg_process:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait()  # Ensure the process is completely stopped
                self.ffmpeg_process = None
                print("Terminated active stream process before crashing.")

            # Raise a RuntimeError to crash the bot intentionally
            raise RuntimeError("Intentional crash triggered by admin")

        if message.startswith("-shutdown"):
            # Check if the user is in the admin list
            if user.username not in self.admins:
                return

            if self.is_loading:
                await self.highrise.chat("The bot is still initializing. Please wait a moment before using the -shutdown command.")
                return

            await self.highrise.chat("Initializing shut down.")
            await asyncio.sleep(3)

            # تنظيف شامل قبل الإغلاق
            try:
                # إيقاف جميع العمليات
                await self.force_stop_all_streams()
                
                # تنظيف الملفات المحملة مسبقاً
                await self.cleanup_preload()
                
                # مسح الطابور والأغنية الحالية
                self.song_queue.clear()
                self.save_queue()
                self.current_song = None
                self.save_current_song()
                
                # حفظ جميع البيانات
                self.save_loc_data()
                
                print("✅ Cleanup completed successfully")
                
            except Exception as e:
                print(f"Error during shutdown cleanup: {e}")
            
            await self.highrise.chat("Shutting down.")
            await asyncio.sleep(2)

            # استخدام sys.exit بدلاً من os._exit للتنظيف الصحيح
            import sys
            sys.exit(0)

        if message.startswith("-setpos") and user.username in self.admins:

            self.bot_pos = await self.get_actual_pos(user.id)
            await self.highrise.chat("Bot position set!")
            await asyncio.sleep(1)
            await self.highrise.teleport(self.highrise.my_id, self.bot_pos)
            await asyncio.sleep(1)
            await self.highrise.teleport(self.highrise.my_id, self.bot_pos)
            self.save_loc_data()

        if message.startswith('-admin ') and user.username in self.owners:

            parts = message.split()
            if len(parts) == 2:
                target_user = parts[1][1:]  # Remove '@' from the username
                if target_user not in self.admins:
                    self.admins.add(target_user)
                    await self.highrise.chat(f"@{target_user} has been added as an admin.")
                    self.save_loc_data()
                else:
                    await self.highrise.chat(f"@{target_user} is already an admin.")
            else:
                await self.highrise.chat("Usage: -admin @<username>")

        if message.startswith('-deladmin ') and user.username in self.owners:

            parts = message.split()
            if len(parts) == 2:
                target_user = parts[1][1:]  # Remove '@' from the username
                if target_user in self.admins:
                    if target_user in self.owners:
                        await self.highrise.chat(f"@{target_user} is an owner and cannot be removed.")
                        return
                    self.admins.remove(target_user)
                    await self.highrise.chat(f"@{target_user} has been removed from the admin list.")
                    self.save_loc_data()
                else:
                    await self.highrise.chat(f"@{target_user} is not an admin.")
            else:
                await self.highrise.chat("Usage: -deladmin @<username>")

        if message.startswith('-cadmin') and user.username in self.admins:

            page_number = 1
            if len(message.split()) > 1:
                try:
                    page_number = int(message.split()[1])
                except ValueError:
                    await self.highrise.chat("Invalid page number.")
                    return
            await self.check_admins(page_number)

        if message.startswith('-play '):

            content = message[6:].strip()
            print(f"{user.username}: -play {content}")

            if content.startswith('[') and content.endswith(']'):
                # Extract the playlist name from inside the brackets
                playlist_name = content[1:-1].strip()

                if playlist_name:  # Ensure the playlist name is not empty
                    await self.play_playlist(playlist_name, user)
                else:
                    await self.highrise.chat("Please provide a valid playlist name inside the brackets. Use '-play [playlist_name]'.")
                return

            if self.is_loading:
                await self.highrise.chat("The bot is still initializing. Please wait a moment before using the -play command.")

            song_request = message[len('-play '):].strip()

            await self.highrise.chat("\n🔎 Search in progress.")

            # Fetch video details using yt_dlp search
            title, duration, file_path, info = await self.search_youtube(song_request, user)

            if not info:
                await self.highrise.chat(f"@{user.username}, I couldn't retrieve details for your song request. Please try a different keyword(s) or URL.")
                return

            # Validate title, duration, and file path
            if not title or duration is None or file_path is None:
                await self.highrise.chat(f"@{user.username}, I couldn't retrieve details for your song request. Please try a different keyword(s) or URL.")
                return

            # Check if the song passed the duration limit
            if duration > 12 * 60:  # 12 minutes limit
                await self.highrise.chat(f"@{user.username}, your song: '{title}' exceeds the 12-minute duration limit and cannot be added.")
                return

            print("search_youtube function done.")

            await self.add_to_queue(user.username, title, duration, file_path)

        if message.startswith('-skip'):
            await self.skip_song(user)  # Pass user.username to the skip_song method

        if message.startswith('-delq'):

            parts = message.split()

            if len(parts) == 1:
                # Call the del_last_song function to delete the user's last song
                await self.del_last_song(user.username)

        if message.startswith('-clearq') and user.username in self.admins:

            parts = message.split()

            if len(parts) == 1:
                # Call the clear_queue function to remove all songs from the user's queue and delete the files
                await self.clear_queue()

        if message.startswith('-cleardownloads') and user.username in self.admins:

            parts = message.split()

            if len(parts) == 1:
                # Call the clear_downloads function to delete all downloaded files
                await self.clear_downloads()

        if message.startswith('-autoclean') and user.username in self.admins:
            parts = message.split()
            
            if len(parts) == 1:
                # عرض الإعدادات الحالية
                current_size = self.get_folder_size_mb('downloads')
                await self.highrise.chat(
                    f"⚙️ إعدادات التنظيف التلقائي:\n\n"
                    f"الحد الأقصى: {self.max_downloads_size_mb}MB\n"
                    f"الحجم الحالي: {current_size:.1f}MB\n"
                    f"فترة الفحص: {self.cleanup_check_interval//60} دقائق\n\n"
                    f"استخدم '-autoclean [حجم بالMB]' لتغيير الحد الأقصى"
                )
            elif len(parts) == 2:
                try:
                    new_size = int(parts[1])
                    if 50 <= new_size <= 2000:  # بين 50MB و 2GB
                        self.max_downloads_size_mb = new_size
                        await self.highrise.chat(f"✅ تم تحديث الحد الأقصى إلى {new_size}MB")
                    else:
                        await self.highrise.chat("❌ يجب أن يكون الحجم بين 50MB و 2000MB")
                except ValueError:
                    await self.highrise.chat("❌ يرجى إدخال رقم صحيح للحجم بالميجابايت")

        if message.startswith('-q'):

            page_number = 1
            try:
                page_number = int(message.split(' ')[1])
            except (IndexError, ValueError):
                pass
            await self.check_queue(page_number)

        if message.startswith('-np'):
            await self.now_playing()

    async def on_message(self, user_id: str, conversation_id: str, is_new_conversation: bool) -> None:
        # Fetch the latest message in the conversation
        response = await self.highrise.get_messages(conversation_id)
        if isinstance(response, GetMessagesRequest.GetMessagesResponse):
            message = response.messages[0].content  # Get the message content

        # Get the username based on user_id
        username = await self.get_user_details(user_id)
        print(f"{username} {message}")

        # Handle -pl create command
        if message.startswith('!create ') and username in self.admins:
            playlist_name = message[len('!create '):].strip()

            # Check if the total number of playlists exceeds the limit (20)
            if len(self.playlists) >= 20:
                await self.highrise.send_message(conversation_id, "Cannot create playlist. Maximum limit of 20 playlists reached.")
                return

            if playlist_name in self.playlists:
                await self.highrise.send_message(conversation_id, f"Playlist '{playlist_name}' already exists.")
            else:
                # Store the playlist with the creator's username
                self.playlists[playlist_name] = {
                    "songs": [],  # List to store songs
                    "created_by": username  # Store the username of the creator
                }

                await self.highrise.send_message(conversation_id, f"Playlist '{playlist_name}' has been created.")
                self.save_playlists()

        if message.startswith('!rename ') and username in self.admins:
            try:
                parts = message.split(maxsplit=1)
                if len(parts) == 2:
                    new_playlist_name = parts[1].strip()
                    playlist_name = self.playlist_selector.get(username)

                    if not playlist_name:
                        await self.highrise.send_message(conversation_id, "You haven't selected a playlist.")
                        return

                    if playlist_name in self.playlists:
                        # Update the playlist name
                        self.playlists[new_playlist_name] = self.playlists.pop(playlist_name)
                        self.save_playlists()
                        self.playlist_selector[username] = new_playlist_name  # Update selected playlist
                        await self.highrise.send_message(conversation_id, f"Playlist has been renamed to '{new_playlist_name}'.")
                    else:
                        await self.highrise.send_message(conversation_id, f"Playlist '{playlist_name}' does not exist.")
                else:
                    await self.highrise.send_message(conversation_id, "Please specify the new name for the playlist.")
            except Exception as e:
                await self.highrise.send_message(conversation_id, "An error occurred while renaming the playlist.")
                print(f"Error: {e}")

        if message.startswith('!select ') and username in self.admins:
            parts = message.split(maxsplit=1)
            if len(parts) == 2:
                playlist_name = parts[1].strip()
                if playlist_name in self.playlists:
                    self.playlist_selector[username] = playlist_name
                    await self.highrise.send_message(conversation_id, f"Playlist '{playlist_name}' has been selected.")
                else:
                    await self.highrise.send_message(conversation_id, f"Playlist '{playlist_name}' does not exist.")
            else:
                await self.highrise.send_message(conversation_id, "Please specify a playlist name to select.")

        if message.startswith('!add ') and username in self.admins:
            try:

                # Check if the user has a selected playlist
                if username not in self.playlist_selector:
                    await self.highrise.send_message(conversation_id, "You haven't selected a playlist. Use '!select [name of playlist]' to select one.")
                    return

                # Retrieve the selected playlist name
                playlist_name = self.playlist_selector[username]
                song_query = message[len('!add '):].strip()

                # Add the song to the selected playlist
                if playlist_name not in self.playlists:
                    await self.highrise.send_message(conversation_id, f"Playlist '{playlist_name}' no longer exists.")
                    return

                # Check if the playlist already has 20 songs
                if len(self.playlists[playlist_name]["songs"]) >= 20:
                    await self.highrise.send_message(conversation_id, f"Playlist '{playlist_name}' is full. You cannot add more.")
                    return

                await self.highrise.send_message(conversation_id, "🔎 Search in progress.")

                await self.add_song_to_playlist(conversation_id, playlist_name, song_query, username)

            except Exception as e:
                await self.highrise.send_message(conversation_id, "An error occurred while adding the song.")
                print(f"Error: {e}")

        if message.startswith('!list') and username in self.admins:
            # No need to handle paging anymore
            playlists_message = "Playlists:\n\n"

            # Check if there are any playlists
            if not self.playlists:
                await self.highrise.send_message(conversation_id, "There are no playlists available.")
                return

            # Loop through all playlists with an index
            for index, (playlist_name, details) in enumerate(self.playlists.items(), start=1):
                creator = details["created_by"]
                song_count = len(details["songs"])  # Number of songs in the playlist
                playlists_message += (
                    f"{index}.\n"
                    f"{playlist_name}\n"
                    f"Created by: @{creator}\n"
                    f"Number of Songs: {song_count}\n"
                    f"\n"
                )

            # Send the list of all playlists
            await self.highrise.send_message(conversation_id, playlists_message)

        if message.startswith('!delete') and username in self.admins:
            try:
                # Check if the user has selected a playlist
                if username in self.playlist_selector:
                    playlist_name = self.playlist_selector[username]

                    # Check if the playlist exists
                    if playlist_name in self.playlists:
                        # Delete the selected playlist
                        del self.playlists[playlist_name]
                        del self.playlist_selector[username]  # Remove the selected playlist for the user
                        self.save_playlists()
                        await self.highrise.send_message(conversation_id, f"Selected playlist '{playlist_name}' has been deleted.")
                    else:
                        await self.highrise.send_message(conversation_id, f"Playlist '{playlist_name}' does not exist.")
                else:
                    await self.highrise.send_message(conversation_id, "You haven't selected a playlist to delete.")
            except Exception as e:
                await self.highrise.send_message(conversation_id, "An error occurred while deleting the playlist.")
                print(f"Error: {e}")

        if message.startswith('!remove ') and username in self.admins:
            try:
                parts = message.split(maxsplit=1)
                if len(parts) == 2:
                    song_position = int(parts[1].strip())
                    playlist_name = self.playlist_selector.get(username)

                    if not playlist_name:
                        await self.highrise.send_message(conversation_id, "You haven't selected a playlist.")
                        return

                    # Check if the playlist exists and has songs
                    if playlist_name in self.playlists and "songs" in self.playlists[playlist_name]:
                        songs = self.playlists[playlist_name]["songs"]

                        # Validate the song position
                        if 1 <= song_position <= len(songs):
                            removed_song = songs.pop(song_position - 1)  # 1-based to 0-based index
                            self.save_playlists()
                            await self.highrise.send_message(conversation_id, f"Song '{removed_song['title']}' has been removed from the playlist.")
                        else:
                            await self.highrise.send_message(conversation_id, f"Invalid song position.")
                    else:
                        await self.highrise.send_message(conversation_id, f"Playlist '{playlist_name}' not found or no songs in the playlist.")
                else:
                    await self.highrise.send_message(conversation_id, "Please specify the song position to remove.")
            except ValueError:
                await self.highrise.send_message(conversation_id, "Please provide a valid song position.")
            except Exception as e:
                await self.highrise.send_message(conversation_id, "An error occurred while removing the song.")
                print(f"Error: {e}")

        if message.startswith('!shuffle') and username in self.admins:
            try:
                playlist_name = self.playlist_selector.get(username)

                if not playlist_name:
                    await self.highrise.send_message(conversation_id, "You haven't selected a playlist.")
                    return

                if playlist_name in self.playlists:
                    songs = self.playlists[playlist_name]["songs"]
                    random.shuffle(songs)  # Shuffle the list of songs
                    self.save_playlists()
                    await self.highrise.send_message(conversation_id, f"Playlist '{playlist_name}' has been shuffled.")
                else:
                    await self.highrise.send_message(conversation_id, f"Playlist '{playlist_name}' does not exist.")
            except Exception as e:
                await self.highrise.send_message(conversation_id, "An error occurred while shuffling the playlist.")
                print(f"Error: {e}")

        if message.startswith('!view') and username in self.admins:
            parts = message.split(maxsplit=1)

            if len(parts) == 2:  # If a playlist name is provided
                playlist_name = parts[1].strip()
            else:  # Use the selected playlist for the user
                playlist_name = self.playlist_selector.get(username)

            if not playlist_name:
                await self.highrise.send_message(conversation_id, "No playlist selected. Use '!select <playlist_name>' to choose a playlist.")
                return

            # View the songs in the playlist
            await self.view_playlist_songs(conversation_id, playlist_name)

        if message.startswith('!help'):
            help_message = """
🎵 **Playlist Creation Guide** 🎵

Admin(s) only:

1. !create [playlist_name]  
- Create a new playlist.  
- Example: `!create MyFavorites`
- You can have a maximum of 20 playlists at a time.

2. !select [playlist_name]
- Select an existing playlist to manage.
- Example: `!select MyFavorites`
- Once selected, the playlist becomes your active playlist for adding and removing songs.

3. !delete
- Delete the currently selected playlist.  
- Make sure you select a playlist first using `!select [playlist_name]`.

4. !rename [new_playlist_name]
- Rename the currently selected playlist.  
- Example: `!rename MyNewFavorites`
- Ensure you've selected a playlist using `!select [playlist_name]` before renaming.

5. !list
- View all available playlists, along with their song count and creator details.

6. !add [song_name]
- Add a song to the currently selected playlist.
- Example: `!add Let Her Go`
- Only a maximum of 20 songs can be added to a playlist.

7. !remove [song_position]
- Remove a song from the currently selected playlist based on its position.
- Example: `!remove 2` will remove the second song in the playlist.

8. !view
- View the songs the in the currently selected playlist.  

9. !shuffle  
- Shuffle the songs in the currently selected playlist.

10. -play [playlist_name]
- Use this commandto add your playlist to the queue.
- The name of the playlist must be inside the brackets.
- Example: `-play [MyFavorites]`
- IMPORTANT: This command must be executed outside of DM.
    """
            await self.highrise.send_message(conversation_id, help_message)


    async def check_admins(self, page_number=1):
        admins_per_page = 5  # How many admins per page
        admins_list = list(self.admins)
        total_pages = (len(admins_list) // admins_per_page) + (1 if len(admins_list) % admins_per_page != 0 else 0)

        if page_number > total_pages:
            await self.highrise.chat(f"Page {page_number} does not exist. Only {total_pages} pages of admins.")
            return

        start_index = (page_number - 1) * admins_per_page
        end_index = min(start_index + admins_per_page, len(admins_list))
        admins_page = admins_list[start_index:end_index]

        # Display the admins on this page with numbers instead of '@'
        admins_message = f"Page {page_number}/{total_pages}:\nAdmins:\n"
        admins_message += "\n".join([f"{index + 1}. {admin}" for index, admin in enumerate(admins_page)])
        await self.highrise.chat(admins_message)

    async def add_credits(self, username, amount):
        """Adds credits to a user."""
        self.credits[username] = self.credits.get(username, 0) + amount
        await self.save_credits()
        await self.highrise.chat(f"Added {amount} credits to @{username}.\n\nCurrent balance: {self.credits[username]}")

    async def remove_credits(self, username, amount):
        if username in self.credits:
            self.credits[username] -= amount
            if self.credits[username] < 0:
                self.credits[username] = 0
            await self.save_credits()
            await self.highrise.chat(f"Removed {amount} credits from @{username}.\n\nRemaining balance: {self.credits[username]}")
        else:
            await self.highrise.chat(f"@{username} does not have any credits.")

    async def check_credits(self, username):
        """Checks the credits of a user."""
        current_credits = self.credits.get(username, 0)
        await self.save_credits()
        await self.highrise.chat(f"@{username}, you have {current_credits} credits.")

    async def clear_all_credits(self):
        self.credits = {}
        await self.highrise.chat("All user credits have been cleared.")

    async def has_enough_credits(self, username):
        """Checks if a user has enough credits to request a song."""
        return self.credits.get(username, 0) > 0

    async def deduct_credit(self, username):
        """Deducts 1 credit from a user's balance."""
        if username in self.credits and self.credits[username] > 0:
            self.credits[username] -= 1
            await self.save_credits()
            print(f"Credit deducted for {username}. Remaining credits: {self.credits[username]}")

    def load_credits(self):
        """Loads the credits from a file."""
        try:
            with open('credits.json', 'r') as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    def load_playlists(self):
        """Load playlists from the JSON file or create it if it doesn't exist."""
        if os.path.exists(PLAYLIST_FILE):
            try:
                with open(PLAYLIST_FILE, "r") as file:
                    print("Loading playlists...")
                    self.playlists = json.load(file)
            except Exception as e:
                print(f"Error loading playlists: {e}")
                self.playlists = {}
        else:
            print(f"{PLAYLIST_FILE} not found. Creating a new one.")
            self.playlists = {}
            self.save_playlists()  # Create the empty file on startup

    def save_playlists(self):
        """Save the playlists to a JSON file."""
        try:
            with open(PLAYLIST_FILE, "w") as f:
                json.dump(self.playlists, f, indent=4)
            print("Playlists saved successfully.")
        except Exception as e:
            print(f"Error saving playlists: {e}")

    def load_logs(self):
        """Load logs and logging state from the .json file, return (logs, logging_enabled)."""
        if os.path.exists(self.log_file):
            try:
                with open(self.log_file, 'r') as f:
                    data = json.load(f)
                    return data.get('logs', 0), data.get('logging_enabled', True)
            except Exception as e:
                print(f"Error loading logs: {e}")
        return 0, True

    def save_logs(self):
        """Save logs and logging state to the .json file."""
        try:
            if os.path.dirname(self.log_file):
                os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            data = {
                'logs': self.logs,
                'logging_enabled': self.logging_enabled
            }
            with open(self.log_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Error saving logs: {e}")

    def load_stats(self):
        """Loads stats from a JSON file or initializes an empty dictionary."""
        if os.path.exists("song_stats.json"):
            with open("song_stats.json", "r") as file:
                return json.load(file)
        return {}

    def update_song_request_stats(self, title, username):

        # Validate the title
        if not title or not isinstance(title, str):  # Check for None, empty, or non-string titles
            print(f"Invalid song title: {title}. Skipping song stat update.")
            return

        # Check if the song exists in the stats; if not, initialize it
        if title not in self.song_request_counts:
            self.song_request_counts[title] = {
                "count": 0,  # Total request count for the song
                "users": {}  # Per-user request counts
            }

        # Increment the total count for the song
        self.song_request_counts[title]["count"] += 1

        # Increment the user's request count for the song
        if username not in self.song_request_counts[title]["users"]:
            self.song_request_counts[title]["users"][username] = 0
        self.song_request_counts[title]["users"][username] += 1

        # Save the updated stats to the JSON file
        with open("song_stats.json", "w") as file:
            json.dump(self.song_request_counts, file)

    async def check_admins(self, page_number):
        """Check the list of admins."""
        if not self.admins:
            await self.highrise.chat("The admin list is empty.")
            return

        admins_list = sorted(list(self.admins))
        admins_per_page = 10
        total_pages = (len(admins_list) + admins_per_page - 1) // admins_per_page

        if page_number < 1 or page_number > total_pages:
            await self.highrise.chat("Invalid page number.")
            return

        start_index = (page_number - 1) * admins_per_page
        end_index = min(start_index + admins_per_page, len(admins_list))
        
        admin_msg = f"🛡️ Bot Admins (Page {page_number}/{total_pages}):\n\n"
        for i, admin in enumerate(admins_list[start_index:end_index], start=start_index + 1):
            admin_msg += f"{i}. @{admin}\n"
            
        await self.highrise.chat(admin_msg)

    def load_loc_data(self):
        """Load location data and admin list from JSON."""
        try:
            if os.path.exists('musicbot_pos.json'):
                with open('musicbot_pos.json', 'r') as file:
                    loc_data = json.load(file)
                    self.bot_pos = Position(**loc_data.get('bot_position')) if loc_data.get('bot_position') is not None else None
                    self.ctoggle = loc_data.get('ctoggle', False)
                    self.nightcore = loc_data.get('nightcore', False)
                    self.daycore = loc_data.get('daycore', False)
                    self.admins = set(loc_data.get('admins', list(self.owners)))
            else:
                self.admins = set(self.owners)
        except Exception as e:
            print(f"Error loading location data: {e}")
            self.admins = set(self.owners)

    def save_loc_data(self):
        """Save location data and admin list to JSON."""
        try:
            loc_data = {
                'bot_position': {'x': self.bot_pos.x, 'y': self.bot_pos.y, 'z': self.bot_pos.z} if self.bot_pos else None,
                'ctoggle': self.ctoggle,
                'nightcore': self.nightcore,
                'daycore': self.daycore,
                'admins': list(self.admins)
            }
            with open('musicbot_pos.json', 'w') as file:
                json.dump(loc_data, file)
        except Exception as e:
            print(f"Error saving location data: {e}")

    async def get_actual_pos(self, user_id):
        """Get the actual position of a user in the room."""
        try:
            room_users = await self.highrise.get_room_users()
            for user, position in room_users.content:
                if user.id == user_id:
                    return position
        except Exception as e:
            print(f"Error getting user position: {e}")
        return None

    async def cleanup_preload(self):
        """Clean up any preloaded files and cancel preload tasks."""
        async with self.preload_lock:
            if self.preload_task and not self.preload_task.done():
                self.preload_task.cancel()
            if self.next_song_file and os.path.exists(self.next_song_file):
                try:
                    os.remove(self.next_song_file)
                    print(f"Cleaned up preloaded file: {self.next_song_file}")
                except Exception as e:
                    print(f"Error cleaning up preloaded file: {e}")
                finally:
                    self.next_song_file = None

    async def force_stop_all_streams(self):
        """Forcefully stop all FFmpeg processes and cleanup streams."""
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=2)
            except:
                try:
                    self.ffmpeg_process.kill()
                except:
                    pass
            self.ffmpeg_process = None
        print("✅ All streams stopped.")

    async def stop_existing_stream(self):
        """Stop any existing FFmpeg stream."""
        await self.force_stop_all_streams()

    async def auto_cleanup_downloads(self):
        """نظام تنظيف ذكي - يعمل فقط عند الحاجة الفعلية"""
        last_cleanup_time = 0
        cleanup_cooldown = 900  # 15 دقيقة بين عمليات التنظيف
        
        while True:
            try:
                # انتظار حتى إضافة أغنية جديدة
                await asyncio.sleep(30)  # فحص خفيف كل 30 ثانية
                
                # تخطي إذا لم يمر وقت كافٍ منذ آخر تنظيف
                current_time = time.time()
                if current_time - last_cleanup_time < cleanup_cooldown:
                    continue
                
                # فحص فقط إذا كان هناك نشاط (أغاني في الطابور أو تشغيل)
                if not self.song_queue and not self.currently_playing:
                    continue
                
                if not os.path.exists('downloads'):
                    continue

                # فحص سريع للحجم فقط
                current_size = self.get_folder_size_mb('downloads')
                
                # تنظيف فقط عند الامتلاء 90% أو أكثر
                if current_size > (self.max_downloads_size_mb * 0.9):
                    print(f"⚠️ مساحة قليلة ({current_size:.1f}MB), بدء تنظيف...")
                    deleted_count = await self.clean_old_downloads()
                    
                    if deleted_count > 0:
                        new_size = self.get_folder_size_mb('downloads')
                        print(f"✅ تم توفير {current_size - new_size:.1f}MB")
                        last_cleanup_time = current_time
                    
            except Exception as e:
                print(f"خطأ في التنظيف التلقائي: {e}")
                await asyncio.sleep(60)