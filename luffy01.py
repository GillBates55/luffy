#!/usr/bin/env python3.11
import os
import sys
import signal
import subprocess
import time
from colorsys import hsv_to_rgb
from PIL import Image, ImageDraw, ImageFont
import RPi.GPIO as GPIO
from ST7789 import ST7789
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
        
        # Audio Control Variables
        self.current_track_index = 0
        self.is_playing = False
        self.volume = 50  # Default volume (0-100)
        self.audio_process = None
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
                
            # Support both WAV and MP3 files
            self.audio_files = sorted([
                str(f) for f in audio_dir.glob("*.[mwMW][aApP][vV3]*")
            ])
            
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

    def get_player_command(self, file_path):
        """Determine the appropriate player command based on file extension"""
        ext = file_path.lower().split('.')[-1]
        if ext == 'mp3':
            return ['mpg123', '-a', 'default', '--scale', str(self.volume), file_path]
        else:  # wav files
            return ['aplay', '-D', 'default', file_path]

    def toggle_playback(self):
        """Toggle between play and pause states"""
        if self.is_playing:
            self.stop_playback()
        else:
            self.start_playback()

    def start_playback(self):
        """Start playing the current track"""
        try:
            if self.audio_process:
                self.stop_playback()
                
            current_file = self.audio_files[self.current_track_index]
            command = self.get_player_command(current_file)
            
            self.audio_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            self.is_playing = True
            self.update_display()
            logger.info(f"Started playing: {current_file}")
        except Exception as e:
            logger.error(f"Error starting playback: {e}")

    def stop_playback(self):
        """Stop the current playback"""
        if self.audio_process:
            self.audio_process.terminate()
            self.audio_process = None
            self.is_playing = False
            self.update_display()
            logger.info("Playback stopped")

    def next_track(self):
        """Switch to the next track"""
        self.current_track_index = (self.current_track_index + 1) % len(self.audio_files)
        if self.is_playing:
            self.start_playback()
        self.update_display()
        logger.info(f"Switched to track: {self.audio_files[self.current_track_index]}")

    def adjust_volume(self, delta):
        """Adjust the system volume"""
        try:
            self.volume = max(0, min(100, self.volume + delta))
            subprocess.run(['amixer', 'set', 'Master', f'{self.volume}%'])
            
            # If currently playing, restart with new volume for MP3
            if self.is_playing and self.audio_files[self.current_track_index].lower().endswith('.mp3'):
                self.start_playback()
                
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
                f"Now Playing:",
                font=self.font,
                fill=(255, 255, 255)
            )
            self.draw.text(
                (10, 30),
                current_file,
                font=self.font,
                fill=(0, 255, 0) if self.is_playing else (255, 0, 0)
            )
            
            # Draw volume
            self.draw.text(
                (10, 60),
                f"Volume: {self.volume}%",
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
                    (10, 100 + i * 20),
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
        GPIO.cleanup()
        logger.info("Cleanup completed")

    def run(self):
        """Main run loop"""
        try:
            logger.info("Starting audio player")
            self.update_display()
            # Start playing the first track
            self.start_playback()
            
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
