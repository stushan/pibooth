#!/usr/bin/env python3
"""
Thermal Printer Photobooth
==========================
Made by digiiash

A Raspberry Pi photobooth that prints instant snapshots to a thermal printer.

Flow:
  1. Idle  -> shows images/attract.jpg
  2. Shutter button pressed -> live camera preview fills the screen with a
     faded 3-2-1 countdown drawn over the feed
  3. Photo is snapped and spooled to the printer; images/printing.jpg is shown
     while the job processes
  4. Loops back to the attract screen

Images (in the images/ folder next to this script):
  attract.jpg   - idle / rest screen
  printing.jpg  - shown while a photo prints

Countdown numbers are rendered by pygame directly over the live camera feed.
Tweak the style constants in the "Countdown overlay style" section to customize
the look.

Author : digiiash
License : MIT
"""

import os
import time
import subprocess
import pygame
import RPi.GPIO as GPIO

__author__ = "digiiash"
__license__ = "MIT"
__version__ = "1.0.0"

# ── Configuration ──────────────────────────────────────────────────────────────
SHUTTER_PIN    = 16      # GPIO pin for shutter button (active LOW, BCM numbering)
SHUTDOWN_PIN   = 26      # GPIO pin for shutdown button (active LOW, BCM numbering)
COUNTDOWN_SECS = 3       # how many seconds to count down
COUNTDOWN_HOLD = 1.0     # seconds to display each number
CAPTURE_MS     = 500     # raspistill final-capture timeout in ms
PRINT_CMD      = "raspistill -ex auto --timeout {ms} -o - | lp"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES = {
    "attract":  os.path.join(SCRIPT_DIR, "images", "attract.jpg"),
    "printing": os.path.join(SCRIPT_DIR, "images", "printing.jpg"),
}

# ── Countdown overlay style ────────────────────────────────────────────────────
FONT_SIZE      = 280
NUMBER_COLOR   = (255, 255, 255)  # white number
NUMBER_ALPHA   = 210              # 0-255; 255 = fully opaque
SHADOW_COLOR   = (0, 0, 0)
SHADOW_ALPHA   = 130
SHADOW_OFFSET  = 8                # drop-shadow offset in pixels
CIRCLE_COLOR   = (0, 0, 0)
CIRCLE_ALPHA   = 110              # dim backing circle behind number
CIRCLE_RADIUS  = 160
# ──────────────────────────────────────────────────────────────────────────────


def load_images(screen_size):
    """Load and scale JPEGs; generate a placeholder if a file is missing."""
    loaded = {}
    for key, path in IMAGES.items():
        if not os.path.exists(path):
            print(f"[WARNING] Missing image: {path}")
            surf = pygame.Surface(screen_size)
            surf.fill((20, 20, 20))
            font = pygame.font.SysFont(None, 64)
            label = font.render(f"[{key}]", True, (180, 180, 180))
            surf.blit(label, label.get_rect(center=(screen_size[0] // 2, screen_size[1] // 2)))
            loaded[key] = surf
        else:
            img = pygame.image.load(path).convert()
            loaded[key] = pygame.transform.scale(img, screen_size)
    return loaded


def show(screen, images, key):
    """Blit a full-screen image and flip the display."""
    screen.blit(images[key], (0, 0))
    pygame.display.flip()


def start_preview(screen_w, screen_h):
    """
    Launch raspistill with a full-screen preview window.
    The Pi's GPU composites the camera feed *beneath* the framebuffer layer,
    so wherever pygame paints black (or nothing), the camera shows through.
    """
    preview_rect = f"0,0,{screen_w},{screen_h}"
    proc = subprocess.Popen([
        "raspistill",
        "-ex", "auto",
        "-p", preview_rect,   # position + size of the preview on screen
        "--timeout", "0",     # run until we kill it
    ])
    return proc


def stop_preview(proc):
    """Terminate the preview subprocess, killing it if it doesn't exit cleanly."""
    if proc and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


def draw_countdown_number(screen, number, screen_size, font_large):
    """
    Paint the screen black (camera shows through) then draw:
      - a semi-transparent dark circle as a backing shape
      - a drop shadow
      - the countdown number with partial transparency
    """
    w, h = screen_size
    cx, cy = w // 2, h // 2

    # Black background — the GPU camera layer beneath will show through
    screen.fill((0, 0, 0))

    # Semi-transparent backing circle
    circle_surf = pygame.Surface((CIRCLE_RADIUS * 2, CIRCLE_RADIUS * 2), pygame.SRCALPHA)
    pygame.draw.circle(
        circle_surf,
        (*CIRCLE_COLOR, CIRCLE_ALPHA),
        (CIRCLE_RADIUS, CIRCLE_RADIUS),
        CIRCLE_RADIUS,
    )
    screen.blit(circle_surf, (cx - CIRCLE_RADIUS, cy - CIRCLE_RADIUS))

    # Drop shadow
    shadow_surf = font_large.render(str(number), True, SHADOW_COLOR)
    shadow_surf.set_alpha(SHADOW_ALPHA)
    screen.blit(shadow_surf, shadow_surf.get_rect(center=(cx + SHADOW_OFFSET, cy + SHADOW_OFFSET)))

    # Number
    num_surf = font_large.render(str(number), True, NUMBER_COLOR)
    num_surf.set_alpha(NUMBER_ALPHA)
    screen.blit(num_surf, num_surf.get_rect(center=(cx, cy)))

    pygame.display.flip()


def countdown_with_preview(screen, screen_size, font_large):
    """
    Start the live preview then tick down 3-2-1 with the overlay.
    Returns the preview subprocess so the caller can stop it before capture.
    """
    preview_proc = start_preview(*screen_size)
    time.sleep(0.4)  # let raspistill start painting before we overlay

    for n in range(COUNTDOWN_SECS, 0, -1):
        draw_countdown_number(screen, n, screen_size, font_large)
        time.sleep(COUNTDOWN_HOLD)

    return preview_proc


def take_and_print(screen, images, preview_proc):
    """Kill the preview, show the printing screen, then snap + spool."""
    stop_preview(preview_proc)
    time.sleep(0.1)
    show(screen, images, "printing")
    subprocess.call(PRINT_CMD.format(ms=CAPTURE_MS), shell=True)


def setup_gpio():
    """Configure shutter and shutdown pins as inputs with pull-ups."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(SHUTTER_PIN,  GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(SHUTDOWN_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def main():
    setup_gpio()

    os.environ["SDL_FBDEV"] = "/dev/fb0"
    os.environ.setdefault("SDL_VIDEODRIVER", "fbcon")

    pygame.init()
    pygame.mouse.set_visible(False)

    info = pygame.display.Info()
    screen_size = (info.current_w, info.current_h)
    screen = pygame.display.set_mode(screen_size, pygame.FULLSCREEN)

    images     = load_images(screen_size)
    font_large = pygame.font.SysFont(None, FONT_SIZE, bold=True)
    clock      = pygame.time.Clock()

    print("Photobooth ready — waiting for button press.")

    try:
        while True:
            # Keep the event queue drained so the OS doesn't think we're frozen
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    raise SystemExit
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    raise SystemExit

            show(screen, images, "attract")

            # ── Shutter button ────────────────────────────────────────────
            if GPIO.input(SHUTTER_PIN) == GPIO.LOW:
                while GPIO.input(SHUTTER_PIN) == GPIO.LOW:
                    time.sleep(0.05)          # wait for physical release

                preview_proc = countdown_with_preview(screen, screen_size, font_large)
                take_and_print(screen, images, preview_proc)
                time.sleep(2)
                print("Photo taken and sent to printer!")

            # ── Shutdown button ───────────────────────────────────────────
            if GPIO.input(SHUTDOWN_PIN) == GPIO.LOW:
                while GPIO.input(SHUTDOWN_PIN) == GPIO.LOW:
                    time.sleep(0.05)
                print("Shutdown triggered.")
                time.sleep(1)
                subprocess.call(["sudo", "shutdown", "now"])

            clock.tick(15)

    except (SystemExit, KeyboardInterrupt):
        print("Exiting.")
    finally:
        GPIO.cleanup()
        pygame.quit()


if __name__ == "__main__":
    main()
