import time
from colorsys import hsv_to_rgb
from PIL import Image, ImageDraw
from ST7789 import ST7789

# Initialize the display
st7789 = ST7789(
    rotation=90,  # Rotate display
    port=0,       # SPI port
    cs=1,         # Chip-select channel
    dc=9,         # Data/command pin
    backlight=13, # Backlight pin
    spi_speed_hz=80 * 1000 * 1000  # SPI speed
)

# Create a blank image for the display
image = Image.new("RGB", (240, 240))
draw = ImageDraw.Draw(image)

while True:
    # Generate a color based on time (hue)
    hue = time.time() / 10
    r, g, b = [int(c * 255) for c in hsv_to_rgb(hue, 1.0, 1.0)]

    # Fill the screen with the generated color
    draw.rectangle((0, 0, 240, 240), (r, g, b))

    # Display the image
    st7789.display(image)

    # Wait for a bit to control the frame rate
    time.sleep(1.0 / 30)
