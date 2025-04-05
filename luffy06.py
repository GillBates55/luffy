#!/usr/bin/env python3.11
import os
import sys
import signal
import time
import vlc
from PIL import Image, ImageDraw, ImageFont, ImageOps
import RPi.GPIO as GPIO
from st7789 import ST7789
from pathlib import Path
import logging
import io
from mutagen import File as MutagenFile
import random
import threading
from queue import Queue

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AudioPlayer:
    def __init__(self):
        # GPIO Button Configuration
        self.BUTTONS = [5, 6, 16, 24]  # A, B, X, Y
        self.LABELS = ['A', 'B', 'X', 'Y']
        
        # Threading and State Management
        self.event_queue = Queue()
        self.lock = threading.Lock()
        self.running = True
        
        # VLC Instance and Player Setup
        self.instance = vlc.Instance('--no-xlib')  # Headless mode for Raspberry Pi
        self.player = self.instance.media_player_new()
        self.is_playing = False
        self.volume = 50  # Default volume (0-100)
        self.audio_files = []
        self.current_media = None
        
        # Display Configuration
        self.display = ST7789(
            rotation=90,
            port=0,
            cs=1,
            dc=9,
            backlight=13,
            spi_speed_hz=80 * 1000 * 1000
        )
        self.image = Image.new("RGB", (240, 240))
        self.draw = ImageDraw.Draw(self.image)
        
        # Try to load fonts with different sizes
        try:
            self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
            self.small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
        except Exception:
            logger.warning("Default font not found, using default bitmap font")
            self.font = ImageFont.load_default()
            self.small_font = ImageFont.load_default()
        
        # Initialize the system
        self.setup_gpio()
        self.load_audio_files()
        
        # Start event handling thread
        self.event_thread = threading.Thread(target=self.event_handler, daemon=True)
        self.event_thread.start()

    def event_handler(self):
        """Handle events in a separate thread"""
        while self.running:
            try:
                event_type = self.event_queue.get(timeout=1.0)
                if event_type == "MEDIA_END":
                    with self.lock:
                        self.next_track()
                elif event_type == "UPDATE_DISPLAY":
                    self.update_display()
            except Exception:
                continue

    def get_album_art(self, audio_file):
        """Extract album art from audio file metadata"""
        try:
            audio = MutagenFile(audio_file)
            if audio is None:
                return None

            art = None
            
            # MP3 (ID3)
            if hasattr(audio, 'tags'):
                for tag in audio.tags.values():
                    if tag.FrameID in ('APIC', 'PIC'):
                        art = tag.data
                        break
            
            # MP4/M4A
            elif 'covr' in audio:
                art = audio['covr'][0]
            
            # FLAC
            elif hasattr(audio, 'pictures'):
                if audio.pictures:
                    art = audio.pictures[0].data

            if art:
                img = Image.open(io.BytesIO(art))
                img = ImageOps.contain(img, (240, 240))
                background = Image.new('RGB', (240, 240), (0, 0, 0))
                pos = ((240 - img.width) // 2, (240 - img.height) // 2)
                background.paste(img, pos)
                background = background.point(lambda p: p * 0.3)
                return background
                
        except Exception as e:
            logger.error(f"Error extracting album art: {e}")
        
        return None

    def update_display(self):
        """Update the LCD display with current track and status"""
        try:
            # Create a new base image
            self.image = Image.new("RGB", (240, 240), (0, 0, 0))
            
            # Try to get and apply album art as background
            if self.audio_files:
                album_art = self.get_album_art(self.audio_files[self.current_track_index])
                if album_art:
                    self.image = album_art
            
            self.draw = ImageDraw.Draw(self.image)
            
            current_file = Path(self.audio_files[self.current_track_index]).name
            
            self.draw.text(
                (10, 20),
                "Now Playing:",
                font=self.font,
                fill=(255, 255, 255)
            )
            self.draw.text(
                (10, 45),
                current_file,
                font=self.font,
                fill=(0, 255, 0) if self.is_playing else (255, 0, 0)
            )
            
            self.draw.text(
                (10, 85),
                f"Volume: {self.volume}%",
                font=self.font,
                fill=(255, 255, 255)
            )
            
            if self.is_playing and self.player.get_media():
                position = self.player.get_position()
                length = self.player.get_length() / 1000
                current_time = length * position if position else 0
                self.draw.text(
                    (10, 120),
                    f"Time: {int(current_time)}s / {int(length)}s",
                    font=self.font,
                    fill=(255, 255, 255)
                )
            
            controls = [
                "A: Play/Pause",
                "B: Next Track",
                "X: Vol Down",
                "Y: Vol Up"
            ]
            for i, control in enumerate(controls):
                self.draw.text(
                    (10, 160 + i * 20),
                    control,
                    font=self.small_font,
                    fill=(200, 200, 200)
                )
            
            self.display.display(self.image)
        except Exception as e:
            logger.error(f"Error updating display: {e}")

    def setup_gpio(self):
        """Initialize GPIO settings and button handlers"""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.BUTTONS, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            
            for pin in self.BUTTONS:
                GPIO.add_event_detect(
                    pin,
                    GPIO.FALLING,
                    callback=self.handle_button,
                    bouncetime=250
                )
        except Exception as e:
            logger.error(f"Failed to initialize GPIO: {e}")
            sys.exit(1)

    def load_audio_files(self):
        """Load audio files from the audio_library directory"""
        try:
            audio_dir = Path("audio_library")
            if not audio_dir.exists():
                logger.error("audio_library directory not found")
                sys.exit(1)
                
            extensions = ('[mM][pP]3', '[wW][aA][vV]', '[mM]4[aA]', '[aA][aA][cC]')
            self.audio_files = []
            
            for ext in extensions:
                self.audio_files.extend(sorted(str(f) for f in audio_dir.glob(f"*.{ext}")))
            
            if not self.audio_files:
                logger.error("No audio files found in audio_library")
                sys.exit(1)
            
            self.current_track_index = random.randint(0, len(self.audio_files) - 1)
            logger.info(f"Loaded {len(self.audio_files)} audio files")
        except Exception as e:
            logger.error(f"Error loading audio files: {e}")
            sys.exit(1)

    def handle_button(self, pin):
        """Handle button press events"""
        label = self.LABELS[self.BUTTONS.index(pin)]
        logger.debug(f"Button {label} pressed")
        
        try:
            with self.lock:
                if label == 'A':  # Play/Pause
                    self.toggle_playback()
                elif label == 'B':  # Next Track
                    self.next_track()
                elif label == 'X':  # Volume Down
                    self.adjust_volume(-5)
                elif label == 'Y':  # Volume Up
                    self.adjust_volume(5)
        except Exception as e:
            logger.error(f"Error handling button press: {e}")

    def toggle_playback(self):
        """Toggle between play and pause states"""
        if not self.player.get_media():
            self.start_playback()
        else:
            if self.is_playing:
                self.player.pause()
                self.is_playing = False
            else:
                self.player.play()
                self.is_playing = True
            self.event_queue.put("UPDATE_DISPLAY")

    def start_playback(self):
        """Start playing the current track"""
        try:
            current_file = self.audio_files[self.current_track_index]
            
            # Clean up old media and event manager
            if self.current_media:
                events = self.current_media.event_manager()
                events.event_detach(vlc.EventType.MediaStateChanged)
                self.current_media.release()
            
            # Create and set up new media
            self.current_media = self.instance.media_new(current_file)
            self.player.set_media(self.current_media)
            
            # Set up media events
            events = self.current_media.event_manager()
            events.event_attach(vlc.EventType.MediaStateChanged, self.on_media_state_changed)
            
            self.player.audio_set_volume(self.volume)
            self.player.play()
            self.is_playing = True
            self.event_queue.put("UPDATE_DISPLAY")
            logger.info(f"Started playing: {current_file}")
            
        except Exception as e:
            logger.error(f"Error starting playback: {e}")

    def on_media_state_changed(self, event):
        """Handle media state changes"""
        try:
            if event.type == vlc.EventType.MediaStateChanged:
                state = event.u.new_state
                if state == vlc.State.Ended:
                    self.event_queue.put("MEDIA_END")
        except Exception as e:
            logger.error(f"Error in media state change handler: {e}")

    def stop_playback(self):
        """Stop the current playback"""
        with self.lock:
            self.player.stop()
            self.is_playing = False
            self.event_queue.put("UPDATE_DISPLAY")
            logger.info("Playback stopped")

    def next_track(self):
        """Switch to the next track"""
        self.current_track_index = (self.current_track_index + 1) % len(self.audio_files)
        if self.is_playing:
            self.start_playback()
        else:
            self.event_queue.put("UPDATE_DISPLAY")
        logger.info(f"Switched to track: {self.audio_files[self.current_track_index]}")

    def adjust_volume(self, delta):
        """Adjust the playback volume"""
        try:
            self.volume = max(0, min(100, self.volume + delta))
            self.player.audio_set_volume(self.volume)
            self.event_queue.put("UPDATE_DISPLAY")
            logger.info(f"Volume adjusted to {self.volume}%")
        except Exception as e:
            logger.error(f"Error adjusting volume: {e}")

    def cleanup(self):
        """Clean up resources on exit"""
        logger.info("Starting cleanup...")
        self.running = False
        self.stop_playback()
        
        if self.current_media:
            self.current_media.release()
        
        self.player.release()
        self.instance.release()
        
        if self.event_thread.is_alive():
            self.event_thread.join(timeout=1.0)
        
        GPIO.cleanup()
        logger.info("Cleanup completed")

    def run(self):
        """Main run loop"""
        try:
            logger.info("Starting audio player")
            self.update_display()
            
            # Set up signal handlers
            def signal_handler(signum, frame):
                logger.info(f"Received signal {signum}")
                self.cleanup()
                sys.exit(0)
            
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
            
            # Main loop with periodic display updates
            while self.running:
                if self.is_playing:
                    self.event_queue.put("UPDATE_DISPLAY")
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            self.cleanup()

if __name__ == "__main__":
    player = AudioPlayer()
    player.run()
