#!/usr/bin/env python3.11
import os
import sys
import signal
import time
import vlc
from PIL import Image, ImageDraw, ImageFont
import RPi.GPIO as GPIO
from st7789 import ST7789
from pathlib import Path
import logging

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
        
        # VLC Instance and Player Setup
        self.instance = vlc.Instance('--no-xlib')  # Headless mode for Raspberry Pi
        self.player = self.instance.media_player_new()
        self.current_track_index = 0
        self.is_playing = False
        self.volume = 50  # Default volume (0-100)
        self.audio_files = []
        
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
        
        # Try to load a font, fallback to default if not found
        try:
            self.font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
        except Exception:
            logger.warning("Default font not found, using default bitmap font")
            self.font = ImageFont.load_default()
        
        # Initialize the system
        self.setup_gpio()
        self.load_audio_files()
        
    def setup_gpio(self):
        """Initialize GPIO settings and button handlers"""
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.BUTTONS, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            
            # Attach handlers for each button
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
                
            # Support multiple audio formats
            extensions = ('[mM][pP]3', '[wW][aA][vV]', '[mM]4[aA]', '[aA][aA][cC]')
            self.audio_files = []
            
            for ext in extensions:
                self.audio_files.extend(sorted(str(f) for f in audio_dir.glob(f"*.{ext}")))
            
            if not self.audio_files:
                logger.error("No audio files found in audio_library")
                sys.exit(1)
                
            logger.info(f"Loaded {len(self.audio_files)} audio files")
        except Exception as e:
            logger.error(f"Error loading audio files: {e}")
            sys.exit(1)

    def handle_button(self, pin):
        """Handle button press events"""
        label = self.LABELS[self.BUTTONS.index(pin)]
        logger.debug(f"Button {label} pressed")
        
        try:
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
            self.update_display()

    def start_playback(self):
        """Start playing the current track"""
        try:
            current_file = self.audio_files[self.current_track_index]
            media = self.instance.media_new(current_file)
            self.player.set_media(media)
            self.player.audio_set_volume(self.volume)
            self.player.play()
            self.is_playing = True
            self.update_display()
            logger.info(f"Started playing: {current_file}")
            
            # Set up end-of-media callback
            events = self.player.event_manager()
            events.event_attach(vlc.EventType.MediaPlayerEndReached, self.on_media_end)
        except Exception as e:
            logger.error(f"Error starting playback: {e}")

    def on_media_end(self, event):
        """Callback for when media playback ends"""
        self.next_track()

    def stop_playback(self):
        """Stop the current playback"""
        self.player.stop()
        self.is_playing = False
        self.update_display()
        logger.info("Playback stopped")

    def next_track(self):
        """Switch to the next track"""
        self.current_track_index = (self.current_track_index + 1) % len(self.audio_files)
        if self.is_playing:
            self.start_playback()
        else:
            self.update_display()
        logger.info(f"Switched to track: {self.audio_files[self.current_track_index]}")

    def adjust_volume(self, delta):
        """Adjust the playback volume"""
        try:
            self.volume = max(0, min(100, self.volume + delta))
            self.player.audio_set_volume(self.volume)
            self.update_display()
            logger.info(f"Volume adjusted to {self.volume}%")
        except Exception as e:
            logger.error(f"Error adjusting volume: {e}")

    def update_display(self):
        """Update the LCD display with current track and status"""
        try:
            # Clear display
            self.draw.rectangle((0, 0, 240, 240), (0, 0, 0))
            
            # Get current track name
            current_file = Path(self.audio_files[self.current_track_index]).name
            
            # Draw track name
            self.draw.text(
                (10, 10),
                "Media Player:",
                font=self.font,
                fill=(255, 255, 255)
            )
            self.draw.text(
                (10, 30),
                current_file,
                font=self.font,
                fill=(0, 255, 0) if self.is_playing else (255, 0, 0)
            )
            
            # Draw volume and time
            self.draw.text(
                (10, 60),
                f"Volume: {self.volume}%",
                font=self.font,
                fill=(255, 255, 255)
            )
            
            # Draw playback position if playing
            if self.is_playing and self.player.get_media():
                position = self.player.get_position()
                length = self.player.get_length() / 1000  # Convert to seconds
                current_time = length * position if position else 0
                self.draw.text(
                    (10, 80),
                    f"Time: {int(current_time)}s / {int(length)}s",
                    font=self.font,
                    fill=(255, 255, 255)
                )
            
            # Draw controls legend
            controls = [
                "A: Play/Pause",
                "B: Next Track",
                "X: Vol Down",
                "Y: Vol Up"
            ]
            for i, control in enumerate(controls):
                self.draw.text(
                    (10, 120 + i * 20),
                    control,
                    font=self.font,
                    fill=(200, 200, 200)
                )
            
            # Update display
            self.display.display(self.image)
        except Exception as e:
            logger.error(f"Error updating display: {e}")

    def cleanup(self):
        """Clean up resources on exit"""
        self.stop_playback()
        self.player.release()
        self.instance.release()
        GPIO.cleanup()
        logger.info("Cleanup completed")

    def run(self):
        """Main run loop"""
        try:
            logger.info("Starting audio player")
            self.update_display()
            
            # Keep the script running
            signal.pause()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt, shutting down")
            self.cleanup()
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            self.cleanup()

if __name__ == "__main__":
    player = AudioPlayer()
    player.run()
