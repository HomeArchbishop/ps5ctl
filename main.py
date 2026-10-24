import os
import re
import sys
import time
import unicodedata

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

DEADZONE = 0.10
FRAME_WIDTH = 68

# SDL gamepad 按钮序号。DualSense 在 pygame 里通常就是这套编号。
LABELS = {
    0: "Cross",
    1: "Circle",
    2: "Square",
    3: "Triangle",
    4: "Create",
    5: "PS",
    6: "Options",
    7: "L3",
    8: "R3",
    9: "L1",
    10: "R1",
    11: "Up",
    12: "Down",
    13: "Left",
    14: "Right",
    15: "Mute",
    20: "Touch",
}

_ANSI = re.compile(r"\033\[[0-9;]*m")
REV = "\033[7m"
BOLD = "\033[1m"
DIM = "\033[2m"
RST = "\033[0m"


def apply_deadzone(value):
    """适用于中心位置为 0 的摇杆轴，不要直接用于扳机轴。"""
    if abs(value) <= DEADZONE:
        return 0.0
    magnitude = (abs(value) - DEADZONE) / (1.0 - DEADZONE)
    return magnitude if value > 0 else -magnitude


def _char_width(char):
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in {"W", "F"}:
        return 2
    return 1


def _vlen(text):
    return sum(_char_width(char) for char in _ANSI.sub("", text))


def _ljust(text, width):
    return text + " " * max(0, width - _vlen(text))


def _center(text, width):
    pad = width - _vlen(text)
    if pad <= 0:
        return text
    left = pad // 2
    return " " * left + text + " " * (pad - left)


def _fmt(value):
    return f"{value:+.3f}"


def _axis(axes, index):
    if index < len(axes):
        return axes[index]
    return None


def _badge(index, pressed, num_buttons):
    text = f"[{index:2d}]"
    if index in pressed:
        return f"{REV}{text}{RST}"
    if index >= num_buttons:
        return f"{DIM}[--]{RST}"
    return text


def _named(index, pressed, num_buttons):
    label = LABELS.get(index, "")
    badge = _badge(index, pressed, num_buttons)
    if label:
        return f"{badge}{label}"
    return badge


def _trigger_level(value):
    """pygame 里 DualSense 扳机静止约为 -1，按满约为 +1。"""
    return max(0.0, min(1.0, (value + 1.0) / 2.0))


def _bar(level, width=10):
    filled = round(max(0.0, min(1.0, level)) * width)
    return "#" * filled + "-" * (width - filled)


def _stick_box(x, y, clicked, cols=7, rows=5):
    x = max(-1.0, min(1.0, apply_deadzone(x)))
    y = max(-1.0, min(1.0, apply_deadzone(y)))
    cx = round((x + 1.0) / 2.0 * (cols - 1))
    cy = round((y + 1.0) / 2.0 * (rows - 1))
    mid_c = cols // 2
    mid_r = rows // 2
    lines = ["+" + "-" * (cols * 2 + 1) + "+"]
    for row in range(rows):
        cells = []
        for col in range(cols):
            if col == cx and row == cy:
                on_center = col == mid_c and row == mid_r
                cells.append("@" if clicked else ("+" if on_center else "O"))
            elif col == mid_c and row == mid_r:
                cells.append("+")
            else:
                cells.append(".")
        lines.append("| " + " ".join(cells) + " |")
    lines.append("+" + "-" * (cols * 2 + 1) + "+")
    return lines


def _cluster(top, left, right, bottom):
    mid = f"{left}     {right}"
    width = max(_vlen(mid), _vlen(top), _vlen(bottom))
    return [_center(top, width), _center(mid, width), _center(bottom, width)]


def _zip_columns(left, right, gap=8):
    rows = max(len(left), len(right))
    left_w = max((_vlen(line) for line in left), default=0)
    merged = []
    for index in range(rows):
        lhs = left[index] if index < len(left) else ""
        rhs = right[index] if index < len(right) else ""
        merged.append(_ljust(lhs, left_w) + " " * gap + rhs)
    return merged


def build_frame(name, axes, pressed, hats, num_buttons):
    pressed = set(pressed)
    lx = _axis(axes, 0)
    ly = _axis(axes, 1)
    rx = _axis(axes, 2)
    ry = _axis(axes, 3)
    l2 = _axis(axes, 4)
    r2 = _axis(axes, 5)

    l2_level = 0.0 if l2 is None else _trigger_level(l2)
    r2_level = 0.0 if r2 is None else _trigger_level(r2)
    l2_text = "  n/a" if l2 is None else _fmt(l2)
    r2_text = "  n/a" if r2 is None else _fmt(r2)

    shoulder = (
        _ljust(
            f"L2 [{_bar(l2_level)}] {l2_text}  L1 {_badge(9, pressed, num_buttons)}",
            36,
        )
        + f"R1 {_badge(10, pressed, num_buttons)}  [{_bar(r2_level)}] {r2_text} R2"
    )

    # 有的驱动把方向键放在 hat 上，而不是按钮 11-14。图上两种来源都点亮。
    dpad_pressed = set(pressed)
    for hat_x, hat_y in hats:
        if hat_y > 0:
            dpad_pressed.add(11)
        elif hat_y < 0:
            dpad_pressed.add(12)
        if hat_x < 0:
            dpad_pressed.add(13)
        elif hat_x > 0:
            dpad_pressed.add(14)
    dpad = _cluster(
        _badge(11, dpad_pressed, num_buttons),
        _badge(13, dpad_pressed, num_buttons),
        _badge(14, dpad_pressed, num_buttons),
        _badge(12, dpad_pressed, num_buttons),
    )
    face = _cluster(
        _badge(3, pressed, num_buttons),
        _badge(2, pressed, num_buttons),
        _badge(1, pressed, num_buttons),
        _badge(0, pressed, num_buttons),
    )

    left_stick = _stick_box(
        0.0 if lx is None else lx, 0.0 if ly is None else ly, 7 in pressed
    )
    right_stick = _stick_box(
        0.0 if rx is None else rx, 0.0 if ry is None else ry, 8 in pressed
    )
    left_readout = "n/a" if lx is None else f"x={_fmt(lx)} y={_fmt(ly)}"
    right_readout = "n/a" if rx is None else f"x={_fmt(rx)} y={_fmt(ry)}"
    stick_w = _vlen(left_stick[0])
    left_block = [
        _center("Lx / Ly", stick_w),
        *left_stick,
        _center(left_readout, stick_w),
        _center(f"L3 {_badge(7, pressed, num_buttons)}", stick_w),
    ]
    right_block = [
        _center("Rx / Ry", stick_w),
        *right_stick,
        _center(right_readout, stick_w),
        _center(f"R3 {_badge(8, pressed, num_buttons)}", stick_w),
    ]

    menu = "  ".join(_named(index, pressed, num_buttons) for index in (4, 5, 6))
    extra_ids = [index for index in (15, 16, 20) if index < num_buttons]
    extra = "  ".join(_named(index, pressed, num_buttons) for index in extra_ids)

    placed = {0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, *extra_ids}
    unknown = [
        _named(index, pressed, num_buttons)
        for index in range(num_buttons)
        if index not in placed and index in pressed
    ]

    hat_text = (
        " ".join(f"{index}:({x:+d},{y:+d})" for index, (x, y) in enumerate(hats)) or "-"
    )
    axes_text = (
        " ".join(f"{index}:{_fmt(value)}" for index, value in enumerate(axes)) or "-"
    )
    pressed_text = ",".join(str(index) for index in sorted(pressed)) or "-"

    lines = [
        f"{BOLD}DualSense{RST}  {name}",
        "原地刷新，Ctrl+C 退出。摇杆上负下正，高亮为按下或方向帽。",
        "",
        shoulder,
        "",
        *_zip_columns(
            [_center(line, stick_w) for line in dpad],
            [_center(line, stick_w) for line in face],
        ),
        "",
        *_zip_columns(left_block, right_block),
        "",
        menu,
    ]
    if extra:
        lines.append(extra)
    if unknown:
        lines.append("其他按下  " + "  ".join(unknown))
    lines.extend(
        [
            "",
            f"{DIM}hat {hat_text}",
            f"axes {axes_text}",
            f"pressed {pressed_text}{RST}",
        ]
    )

    width = max(FRAME_WIDTH, *(_vlen(line) for line in lines))
    return "\n".join(_center(line, width) if line else "" for line in lines)


def _enable_ansi():
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except OSError:
        return


class _LiveScreen:
    def __enter__(self):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
        _enable_ansi()
        sys.stdout.write("\033[?1049h\033[H\033[?25l")
        sys.stdout.flush()
        return self

    def __exit__(self, exc_type, exc, tb):
        sys.stdout.write("\033[?25h\033[?1049l")
        sys.stdout.flush()

    def draw(self, frame):
        sys.stdout.write("\033[H\033[0m" + frame + "\033[J")
        sys.stdout.flush()


def main():
    pygame.init()
    pygame.joystick.init()

    try:
        if pygame.joystick.get_count() == 0:
            print("没有检测到手柄，请检查 USB 连接后重新运行。")
            return

        controller = pygame.joystick.Joystick(0)
        controller.init()
        connected = True

        with _LiveScreen() as screen:
            while connected:
                for event in pygame.event.get():
                    if (
                        event.type == pygame.JOYDEVICEREMOVED
                        and event.instance_id == controller.get_instance_id()
                    ):
                        connected = False

                if not connected:
                    break

                axes = [
                    round(controller.get_axis(i), 3)
                    for i in range(controller.get_numaxes())
                ]
                pressed = [
                    i
                    for i in range(controller.get_numbuttons())
                    if controller.get_button(i)
                ]
                hats = [controller.get_hat(i) for i in range(controller.get_numhats())]
                screen.draw(
                    build_frame(
                        controller.get_name(),
                        axes,
                        pressed,
                        hats,
                        controller.get_numbuttons(),
                    )
                )
                time.sleep(0.05)

        if not connected:
            print("手柄已断开。")

    except KeyboardInterrupt:
        print("已退出。")
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
