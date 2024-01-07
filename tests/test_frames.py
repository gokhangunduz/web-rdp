import PIL.Image

from controller import FRAME_FULL, FRAME_NOP, FRAME_PARTIAL
from frames import MIN_EMPTY_FRAMES_BEFORE_FULL_REPAINT, FrameEncoder


def screen(color="black"):
    return PIL.Image.new("RGB", (1920, 1080), color)


def kind(packet):
    return packet[5]


def test_first_frame_is_full():
    assert kind(FrameEncoder().encode(screen(), 960, 540, 60)) == FRAME_FULL


def test_unchanged_screen_is_a_nop():
    encoder = FrameEncoder()
    encoder.encode(screen(), 960, 540, 60)
    packet = encoder.encode(screen(), 960, 540, 60)
    assert kind(packet) == FRAME_NOP
    assert len(packet) == 6


def test_changed_region_is_sent_as_partial_frame():
    encoder = FrameEncoder()
    encoder.encode(screen(), 960, 540, 60)

    changed = screen()
    changed.paste("red", (0, 0, 200, 200))
    packet = encoder.encode(changed, 960, 540, 60)

    assert kind(packet) == FRAME_PARTIAL
    assert int.from_bytes(packet[6:8], "little") == 0  # crop x
    assert int.from_bytes(packet[8:10], "little") == 0  # crop y


def test_header_carries_real_screen_size():
    packet = FrameEncoder().encode(screen(), 960, 540, 60)
    assert int.from_bytes(packet[1:3], "little") == 1920
    assert int.from_bytes(packet[3:5], "little") == 1080


def test_viewport_change_forces_full_repaint():
    encoder = FrameEncoder()
    encoder.encode(screen(), 960, 540, 60)
    assert kind(encoder.encode(screen(), 640, 360, 60)) == FRAME_FULL
    assert kind(encoder.encode(screen(), 1920, 1080, 60)) == FRAME_FULL


def test_long_idle_runs_still_get_a_periodic_full_repaint():
    encoder = FrameEncoder()
    kinds = [
        kind(encoder.encode(screen(), 960, 540, 60))
        for _ in range(MIN_EMPTY_FRAMES_BEFORE_FULL_REPAINT + 5)
    ]
    assert kinds.count(FRAME_FULL) == 2


def test_frames_are_never_upscaled():
    packet = FrameEncoder().encode(screen(), 4000, 3000, 60)
    assert kind(packet) == FRAME_FULL
