from importlib import import_module
from highrise.__main__ import *
import time
import traceback
import psutil

# BOT SETTINGS #
bot_file_name = "musicbot"
bot_class_name = "xenoichi"
room_id = "687d9840026e8689afecf1ed"
bot_token = "09b08c1a548fecf3720463585e6f1963013a74af6796b0fec3dfcdac4bab9b48"

def terminate_ffmpeg_processes():
    try:
        terminated_count = 0
        for proc in psutil.process_iter(['pid', 'name', 'create_time']):
            if proc.info['name'] and 'ffmpeg' in proc.info['name'].lower():
                try:
                    print(f"Terminating FFmpeg process: {proc.info['pid']}")
                    proc.terminate()
                    # Wait up to 2 seconds for graceful termination (reduced from 3)
                    proc.wait(timeout=2)
                    print(f"Gracefully terminated FFmpeg process: {proc.info['pid']}")
                    terminated_count += 1
                except psutil.TimeoutExpired:
                    # Force kill if it doesn't terminate gracefully
                    proc.kill()
                    print(f"Force killed FFmpeg process: {proc.info['pid']}")
                    terminated_count += 1
                except psutil.NoSuchProcess:
                    # Process already terminated
                    pass
                except Exception as e:
                    print(f"Failed to terminate process {proc.info['pid']}: {e}")
        
        if terminated_count > 0:
            print(f"✅ تم إنهاء {terminated_count} عملية ffmpeg")
        else:
            print("ℹ️ لم يتم العثور على عمليات ffmpeg نشطة")
            
    except Exception as e:
        print(f"Error while terminating FFmpeg processes: {e}")

def cleanup_temp_files():
    """تنظيف الملفات المؤقتة عند إعادة التشغيل"""
    import glob
    try:
        temp_patterns = ['encoded_song*.mp3', 'temp_*.mp3', '*.tmp']
        cleaned_count = 0
        
        for pattern in temp_patterns:
            for file_path in glob.glob(pattern):
                try:
                    import os
                    os.remove(file_path)
                    cleaned_count += 1
                except:
                    continue
        
        if cleaned_count > 0:
            print(f"🧹 تم تنظيف {cleaned_count} ملف مؤقت")
            
    except Exception as e:
        print(f"خطأ في تنظيف الملفات المؤقتة: {e}")

my_bot = BotDefinition(getattr(import_module(bot_file_name), bot_class_name)(), room_id, bot_token)

while True:
    try:
        # Cleanup lingering FFmpeg processes before restarting
        terminate_ffmpeg_processes()
        
        # تنظيف الملفات المؤقتة
        cleanup_temp_files()

        definitions = [my_bot]
        arun(main(definitions))
    except Exception as e:
        print(f"An exception occurred: {e}")
        traceback.print_exc()
        
        print("🔄 إعادة تشغيل البوت خلال 5 ثوانٍ...")
        # Delay before reconnect attempt
        time.sleep(5)
