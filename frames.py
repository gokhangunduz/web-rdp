"""Screen frame encoding: full JPEG frames plus WEBP patches of changed regions."""

from io import BytesIO

import PIL.Image
import PIL.ImageChops
import PIL.ImageGrab

from controller import (
    FRAME_FULL,
    FRAME_NOP,
    FRAME_PARTIAL,
    PACKET_FRAME_RESPONSE,
    encode_int8,
    encode_int16,
)

DOWNSAMPLE = PIL.Image.BILINEAR

# Force a full repaint after this many partial frames, so a client that missed
# an update on a slow link does not stay out of sync forever.
MIN_PARTIAL_FRAMES_BEFORE_FULL_REPAINT = 60

# Same, for runs of unchanged frames.
MIN_EMPTY_FRAMES_BEFORE_FULL_REPAINT = 120


def grab_screen():
    return PIL.ImageGrab.grab()


class FrameEncoder:
    """Keeps per-connection state and turns screenshots into response packets."""

    def __init__(self):
        self.last_frame = None
        self.partial_frames = 0
        self.empty_frames = 0
        self.viewport_width = 0
        self.viewport_height = 0

    def encode(self, image, viewport_width, viewport_height, quality):
        real_width, real_height = image.width, image.height

        if image.width > viewport_width or image.height > viewport_height:
            image.thumbnail((viewport_width, viewport_height), DOWNSAMPLE)

        buffer = BytesIO()
        buffer.write(encode_int8(PACKET_FRAME_RESPONSE))
        buffer.write(encode_int16(real_width))
        buffer.write(encode_int16(real_height))

        needs_full_repaint = (
            self.last_frame is None
            or self.last_frame.size != image.size
            or self.viewport_width != viewport_width
            or self.viewport_height != viewport_height
            or self.partial_frames > MIN_PARTIAL_FRAMES_BEFORE_FULL_REPAINT
            or self.empty_frames > MIN_EMPTY_FRAMES_BEFORE_FULL_REPAINT
        )

        # Only diff frames of identical size, ImageChops raises on a mismatch
        # (e.g. the browser window was resized) which used to freeze the stream.
        diff_bbox = None
        if not needs_full_repaint:
            diff_bbox = PIL.ImageChops.difference(self.last_frame, image).getbbox()

        if needs_full_repaint:
            buffer.write(encode_int8(FRAME_FULL))
            image.save(fp=buffer, format="JPEG", quality=quality)
            self.last_frame = image
            self.viewport_width = viewport_width
            self.viewport_height = viewport_height
            self.partial_frames = 0
            self.empty_frames = 0
        elif diff_bbox is None:
            buffer.write(encode_int8(FRAME_NOP))
            self.empty_frames += 1
        else:
            buffer.write(encode_int8(FRAME_PARTIAL))
            buffer.write(encode_int16(diff_bbox[0]))
            buffer.write(encode_int16(diff_bbox[1]))
            image.crop(diff_bbox).save(fp=buffer, format="WEBP", quality=quality)
            self.last_frame = image
            self.partial_frames += 1

        return buffer.getvalue()
