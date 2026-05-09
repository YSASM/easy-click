import importlib
import os
import random
from threading import Event
from threading import Thread
import time
from tkinter import NO
from PIL import Image
import cv2
import traceback
from src.utils import BaseControl, Bean, random_xy
from src.utils.adb import Adb
from src.utils.uiautomator2Manger import Uiautomator2


def _compile_script_lines(raw_lines: list[str]) -> list[list[str]]:
    """
    规范化脚本行：合并空白、忽略注释与空行，拆成 token 列表。
    比逐行 re.sub 更快；行为与原先「strip 后 # 开头视为空行」一致。
    """
    lines = [""] + list(raw_lines)
    out: list[list[str]] = []
    for cmd in lines:
        stripped = cmd.strip()
        if not stripped or stripped.startswith("#"):
            out.append([""])
            continue
        norm = " ".join(stripped.split())
        out.append(norm.split(" ") if norm else [""])
    return out


def _build_image_path_lookup(images_dir: str) -> dict[str, str]:
    """
    文件名 -> 绝对路径；对 *.png 额外注册无后缀 stem，便于脚本写 xxx 或 xxx.png。
    """
    lookup: dict[str, str] = {}
    if not os.path.isdir(images_dir):
        return lookup
    try:
        names = os.listdir(images_dir)
    except OSError:
        return lookup
    for name in names:
        path = os.path.join(images_dir, name)
        if not os.path.isfile(path):
            continue
        lookup[name] = path
        if name.lower().endswith(".png"):
            stem, _ = os.path.splitext(name)
            lookup.setdefault(stem, path)
    return lookup


# run 循环中：返回此对象表示结束脚本（原 END / 部分 fatal）
_HALT = object()


class Vm(Thread):
    def __init__(self, page, dir, address: BaseControl, code: list[str]):
        super().__init__(daemon=True)
        self.page = page
        self.child = None
        # 用 Event 作为停止信号，避免某些场景下 bool 标志“看起来没生效”的错觉
        self._killed_event = Event()
        self.variable = {}
        self.end = False
        self._if_runtime_stack: list[dict] = []
        self._for_runtime_stack: list[dict] = []
        self._device_xy_vars: set[str] = set()
        # 脚本坐标系默认与设备一致（也可用 RES 指令覆盖）
        self._script_res = (1280, 720)
        self._device_res = (1280, 720)
        self.__script_name__ = "__main__"

        self.control = Uiautomator2(address)
        err = self.control.connect()
        if err is not None:
            self.add_cmd_out(str(err))
            raise Exception(f"链接失败{str(err)}")

        self.add_cmd_out(f"INFO {self.control.d.info}")
        try:
            info = self.control.d.info or {}
            dw = int(info.get("displayWidth") or info.get("width") or 1280)
            dh = int(info.get("displayHeight") or info.get("height") or 720)
            if dw > 0 and dh > 0:
                self._device_res = (dw, dh)
        except Exception:
            pass
        # 若脚本未显式声明 RES，则默认脚本分辨率与设备分辨率一致
        self._script_res = self._device_res
        self.adb = Adb(address)
        self.address = address
        self.dir = dir
        self._import_path_prefix = self.dir.replace("/", ".")
        # 按需加载模板图，避免启动时解码全部 PNG（大幅缩短初始化时间）
        images_dir = os.path.join(dir, "images")
        self._image_lookup = _build_image_path_lookup(images_dir)
        self._template_cv2_cache: dict[str, object] = {}

        self.code = _compile_script_lines(code)

        self.tags = {}
        for line, args in enumerate(self.code):
            if args and args[0] == "TAG" and len(args) > 1:
                self.tags[args[1]] = line

        self._if_block_map = self._build_if_block_map()
        self._for_block_map = self._build_for_block_map()
        # 每行的“块嵌套深度”（FOR/IF 共同计数），用于限制跳转：禁止从外层跳入更深层级
        self._line_depth = self._build_line_depth_map()

    def _build_line_depth_map(self) -> list[int]:
        """
        计算每一行的块嵌套深度（FOR/IF）。
        depth[i] 表示“执行第 i 行时”所处的深度（进入块后的行会更深）。

        只对「块结构」生效：
        - IF：仅当该 IF 能在 _if_block_map 中找到对应 END_IF 时才视为块（单行 IF THEN 不计入）
        - FOR：仅当该 FOR 能在 _for_block_map 中找到对应 END_FOR 时才视为块
        """
        n = len(self.code)
        depth = [0] * n
        d = 0
        for i in range(n):
            depth[i] = d
            args = self.code[i]
            if not args or not args[0]:
                continue
            kw = args[0]
            if kw == "FOR":
                info = self._for_block_map.get(i)
                if info and info.get("kind") == "FOR":
                    d += 1
            elif kw == "IF":
                info = self._if_block_map.get(i)
                if info and info.get("kind") == "IF":
                    d += 1
            elif kw == "END_FOR":
                info = self._for_block_map.get(i)
                if info and info.get("kind") == "END_FOR":
                    d = max(0, d - 1)
            elif kw == "END_IF":
                info = self._if_block_map.get(i)
                if info and info.get("kind") == "END_IF":
                    d = max(0, d - 1)
        return depth

    def _can_jump_to_line(self, *, from_line: int, to_line: int) -> bool:
        """
        跳转限制：只能同层或往外跳（to_depth <= from_depth），不能往里跳。
        """
        try:
            if to_line < 0:
                return True
            if from_line < 0:
                return True
            from_depth = self._line_depth[from_line] if from_line < len(self._line_depth) else 0
            to_depth = self._line_depth[to_line] if to_line < len(self._line_depth) else 0
            return to_depth <= from_depth
        except Exception:
            # 深度表异常时，宁可不拦截，避免误伤
            return True

    def _get_shared_call_stack(self) -> list[dict]:
        """与 page 绑定，主脚本与 IMPORT / PYTHON_RUN 之间共享，反映调用链。"""
        if not hasattr(self.page, "_vm_call_stack"):
            self.page._vm_call_stack = []
        return self.page._vm_call_stack

    def _call_stack_push(self, frame: dict) -> None:
        stack = self._get_shared_call_stack()
        stack.append(frame)
        sn = frame.get("script", "?")
        depth = len(stack)
        self.add_cmd_out(f"INFO [CALL +] {sn} (depth={depth})")

    def _call_stack_pop(self) -> None:
        stack = self._get_shared_call_stack()
        if not stack:
            return
        frame = stack.pop()
        sn = frame.get("script", "?")
        depth = len(stack)
        self.add_cmd_out(f"INFO [CALL -] {sn} (depth={depth})")

    def _call_stack_set_line(self, line: int) -> None:
        stack = self._get_shared_call_stack()
        if stack:
            stack[-1]["line"] = line

    def call_stack_snapshot(self) -> list[dict]:
        """当前调用栈副本（顶层为当前帧），供调试或 UI。"""
        return [dict(f) for f in self._get_shared_call_stack()]

    def _sleep_interruptible(self, seconds: float, *, step: float = 0.1) -> None:
        """
        可中断 sleep：关闭运行页时会调用 kill()，此处能更快退出线程。
        step 越小退出越快，但 CPU 唤醒更频繁。
        """
        try:
            total = float(seconds)
        except Exception:
            return
        if total <= 0:
            return
        step = max(0.02, float(step))
        end = time.monotonic() + total
        while not self._killed_event.is_set():
            left = end - time.monotonic()
            if left <= 0:
                return
            time.sleep(min(step, left))

    def add_cmd_out(self, cmd):
        self.page.cmd_out_list.append(cmd)
        self.page.update_cmd_out_signal.emit()

    def _resolve_template_path(self, name: str) -> str | None:
        p = self._image_lookup.get(name)
        if p is not None:
            return p
        return self._image_lookup.get(f"{name}.png")

    def _get_template_cv2(self, name: str):
        """按路径缓存 OpenCV 图像，同一文件只解码一次。"""
        path = self._resolve_template_path(name)
        if path is None:
            raise KeyError(name)
        cached = self._template_cv2_cache.get(path)
        if cached is not None:
            return cached
        im = self.control.pillow_to_cv2(Image.open(path))
        self._template_cv2_cache[path] = im
        return im

    def _scale_images_for_match(self, screenshot_cv2, template_cv2):
        """
        为模板匹配对齐分辨率：
        - 设备分辨率高于脚本 RES：缩小截图到脚本坐标系（不放大）
        - 设备分辨率低于脚本 RES：缩小模板到设备坐标系（不放大）

        返回：(big, small, pos_scale) 其中 pos_scale=(sx,sy) 表示匹配坐标->设备坐标的缩放。
        """
        sw, sh = self._script_res
        dw, dh = self._device_res
        # 默认：不缩放，坐标直接是设备坐标
        pos_sx = 1.0
        pos_sy = 1.0
        big = screenshot_cv2
        small = template_cv2

        try:
            # 设备更大：缩小截图到脚本分辨率
            if dw > sw and dh > sh and sw > 0 and sh > 0:
                big = cv2.resize(big, (sw, sh), interpolation=cv2.INTER_AREA)
                pos_sx = dw / sw
                pos_sy = dh / sh
            # 设备更小：缩小模板到设备尺度（按比例）
            elif (dw < sw or dh < sh) and dw > 0 and dh > 0 and sw > 0 and sh > 0:
                fx = dw / sw
                fy = dh / sh
                # 若比例不一致，取较小比例避免放大（更稳）
                f = min(fx, fy)
                if f > 0 and f < 1:
                    tw = max(1, int(round(small.shape[1] * f)))
                    th = max(1, int(round(small.shape[0] * f)))
                    small = cv2.resize(small, (tw, th), interpolation=cv2.INTER_AREA)
        except Exception:
            pass

        return big, small, (pos_sx, pos_sy)

    def find_image(self, name):
        big_image = self.control.screenshot()
        small_image = self._get_template_cv2(name)
        big_image, small_image, (sx, sy) = self._scale_images_for_match(big_image, small_image)
        result = cv2.matchTemplate(big_image, small_image, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        if max_val > 0.95:
            x, y = max_loc
            x += small_image.shape[1] // 2
            y += small_image.shape[0] // 2
            # 坐标统一返回到设备分辨率空间
            return [x * sx, y * sy]
        return None

    def has_images(self, names):
        big_image = self.control.screenshot()
        for name in names:
            small_image = self._get_template_cv2(name)
            big_m, small_m, _ = self._scale_images_for_match(big_image, small_image)
            result = cv2.matchTemplate(big_m, small_m, cv2.TM_CCOEFF_NORMED)
            min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
            if max_val < 0.95:
                return False
        return True

    def wait_image(self, name, time_out=5):
        count = 0
        while True:
            if self._killed_event.is_set():
                return None
            res = self.find_image(name)
            if res is not None:
                return res
            if count > time_out:
                return None
            self._sleep_interruptible(1.0, step=0.1)
            count += 1

    def back(self):
        self.adb.cmd("shell input keyevent 4")

    def home(self):
        self.adb.cmd("shell input keyevent 3")

    def start_app(self, package):
        res = self.adb.cmd("shell ps")
        if not package in res:
            self.adb.cmd(
                f"shell monkey -p {package} -c android.intent.category.LAUNCHER 1"
            )

    def get_tag(self, tag, line, pos=None):
        if tag == "PASS" or tag is None:
            return line
        if tag == "CONT":
            # 仅允许在 FOR 内使用：continue 到 END_FOR，让 END_FOR 负责自增/判断并回跳
            if not self._for_runtime_stack:
                return -3
            end_for = self._for_runtime_stack[-1].get("end")
            try:
                end_for = int(end_for)
            except Exception:
                return -3
            # 外层会做 +1，因此这里返回 end_for - 1，让下一步执行 end_for 行
            return end_for - 1
        if tag == "BREAK":
            # 跳出最近一层 FOR 循环：返回 END_FOR 所在行号（外层会再 +1）
            return self._break_loop_target_line()
        if tag == "END":
            return -2
        if tag == "CLICK" and pos is not None:
            x, y = pos
            x = random_xy(x)
            y = random_xy(y)
            self.control.click([x, y])
            self._sleep_interruptible(random.uniform(1.0, 2.0), step=0.1)
            self.add_cmd_out(f"INFO [点击坐标({x},{y})]")
            return line
        dest = self.tags.get(tag, -3)
        if isinstance(dest, int) and dest >= 0:
            if not self._can_jump_to_line(from_line=line, to_line=dest):
                try:
                    fd = self._line_depth[line] if line < len(self._line_depth) else 0
                    td = self._line_depth[dest] if dest < len(self._line_depth) else 0
                except Exception:
                    fd, td = -1, -1
                self.add_cmd_out(
                    f"ERROR {line}:GO {tag} [禁止跳入更深层级: fromDepth={fd} -> toDepth={td}]"
                )
                return -3
        return dest

    def _break_loop_target_line(self) -> int:
        """
        BREAK：跳出最近一层 FOR 循环。
        返回对应 END_FOR 行号（供 _after_tag 做 +1），并弹出该循环的运行栈帧。
        若不在循环内，则返回 -1（结束当前脚本循环）。
        """
        if not self._for_runtime_stack:
            return -1
        fr = self._for_runtime_stack.pop()
        end_for = fr.get("end")
        try:
            return int(end_for)
        except Exception:
            return -1

    def is_num(self, s):
        try:
            float(s)
            return True
        except ValueError:
            return False

    def import_script(self, name):
        """同步执行子脚本：直接在当前线程调用 run()，等价于 start()+join() 但不新建线程。"""
        try:
            with open(f"scripts/{name}/index.txt", "r+", encoding="utf-8") as f:
                code = f.read().split("\n")
            self.child = Vm(self.page, f"scripts/{name}", self.address, code)
            self.child.__script_name__ = name
            self.child.run()
            self.child = None
        except Exception as e:
            Bean.cmd_out_list.append(str(e))

    def kill(self):
        if self.child is not None:
            self.child.kill()
        self._killed_event.set()

    def getArg(self, args, index):
        try:
            return args[index]
        except Exception:
            return None

    def _scale_xy_if_needed(self, x: float, y: float, *, space: str) -> tuple[float, float]:
        """space=script 时按 RES->设备分辨率缩放；space=device 时不缩放。"""
        if space != "script":
            return x, y
        sw, sh = self._script_res
        dw, dh = self._device_res
        try:
            if sw > 0 and sh > 0 and dw > 0 and dh > 0:
                return x * dw / sw, y * dh / sh
        except Exception:
            pass
        return x, y

    def _xy_from_var(self, name: str) -> tuple[float, float, str]:
        """取坐标变量，返回 (x,y,space)。"""
        v = self.variable.get(name)
        if not isinstance(v, (list, tuple)) or len(v) < 2:
            raise KeyError(name)
        x, y = v[0], v[1]
        space = "device" if name in self._device_xy_vars else "script"
        return float(x), float(y), space

    def _value_of(self, token):
        if token is None:
            return None
        if isinstance(token, (int, float, bool)):
            return token
        if token in self.variable:
            return self.variable[token]
        if isinstance(token, str):
            t = token.strip()
            if t.upper() in ("TRUE", "FALSE"):
                return t.upper() == "TRUE"
            try:
                return float(t) if "." in t else int(t)
            except Exception:
                return token
        return token

    def _eval_condition_tokens(self, tokens: list) -> bool:
        """
        支持：
        - 单 token：布尔变量 / TRUE/FALSE / 非空字符串判真
        - 三 token：a <op> b （== != > >= < <=）
        """
        if not tokens:
            return False
        if len(tokens) == 1:
            v = self._value_of(tokens[0])
            return bool(v)
        if len(tokens) >= 3:
            a = self._value_of(tokens[0])
            op = tokens[1]
            b = self._value_of(tokens[2])
            try:
                if op == "==":
                    return a == b
                if op == "!=":
                    return a != b
                if op == ">":
                    return a > b
                if op == ">=":
                    return a >= b
                if op == "<":
                    return a < b
                if op == "<=":
                    return a <= b
            except Exception:
                return False
        return False

    @staticmethod
    def _split_then(args: list) -> tuple[list, str | None, str | None]:
        """
        把形如：<prefix...> THEN yes [no] 拆分。
        返回：(prefix, yes, no)。若无 THEN 或缺少 yes 则 yes/no 为 None。
        若缺少 no，则 no 自动视为 PASS。
        """
        try:
            i = args.index("THEN")
        except ValueError:
            return args, None, None
        if i + 1 >= len(args):
            return args[:i], None, None
        yes = args[i + 1]
        no = args[i + 2] if i + 2 < len(args) else "PASS"
        return args[:i], yes, no

    @staticmethod
    def _split_time_out(args: list) -> tuple[list, float | None]:
        """
        把形如：<prefix...> TIME_OUT t 拆分。
        返回：(prefix, t)。无 TIME_OUT 则 t=None。
        """
        try:
            i = args.index("TIME_OUT")
        except ValueError:
            return args, None
        if i + 1 >= len(args):
            return args[:i], None
        try:
            t = float(args[i + 1])
        except Exception:
            t = None
        return args[:i], t

    def _build_if_block_map(self) -> dict[int, dict]:
        """
        预编译 IF/ELSE_IF/ELSE/END_IF 的匹配关系（仅同层级）。
        返回：line -> {kind, end, next}，kind 为 IF/ELSE_IF/ELSE/END_IF。
        next：本分支失败时跳到的下一个分支头（或 END_IF）。
        """
        stacks: list[dict] = []
        m: dict[int, dict] = {}
        for i, args in enumerate(self.code):
            if not args or not args[0]:
                continue
            kw = args[0]
            if kw == "IF":
                frame = {"if": i, "branches": [i], "end": None}
                stacks.append(frame)
            elif kw in ("ELSE_IF", "ELSE"):
                if not stacks:
                    continue
                stacks[-1]["branches"].append(i)
            elif kw == "END_IF":
                if not stacks:
                    continue
                frame = stacks.pop()
                frame["end"] = i
                branches = frame["branches"]
                end = i
                for j, b in enumerate(branches):
                    nxt = branches[j + 1] if j + 1 < len(branches) else end
                    m[b] = {"kind": self.code[b][0], "end": end, "next": nxt}
                m[end] = {"kind": "END_IF", "end": end, "next": end}
        return m

    def _build_for_block_map(self) -> dict[int, dict]:
        """预编译 FOR/END_FOR 配对。返回 line -> {kind, other}。"""
        st: list[int] = []
        m: dict[int, dict] = {}
        for i, args in enumerate(self.code):
            if not args or not args[0]:
                continue
            kw = args[0]
            if kw == "FOR":
                st.append(i)
            elif kw == "END_FOR":
                if not st:
                    continue
                start = st.pop()
                m[start] = {"kind": "FOR", "other": i}
                m[i] = {"kind": "END_FOR", "other": start}
        return m

    def _next_line(self, line: int) -> int:
        """顺序执行一行后的下标（等价于原逻辑里的 line 当前行执行完再 +1）。"""
        return line + 1

    def _unwind_for_stack_for_jump(self, dest_line: int) -> None:
        """
        当 GO / tag 跳转到 dest_line 时，自动弹出已离开的 FOR 循环帧，确保能“跳出循环”。
        规则：只要目标行不在 [start, end]（包含端点）内，就弹出该层循环。
        """
        while self._for_runtime_stack:
            fr = self._for_runtime_stack[-1]
            try:
                start = int(fr.get("start"))
                end = int(fr.get("end"))
            except Exception:
                self._for_runtime_stack.pop()
                continue
            if start <= dest_line <= end:
                return
            self._for_runtime_stack.pop()

    def _after_tag(self, tag_line: int) -> int:
        """get_tag 返回的脚本行号再 +1，与原先循环末尾 line += 1 一致。"""
        if isinstance(tag_line, int) and tag_line >= 0:
            self._unwind_for_stack_for_jump(tag_line)
        return tag_line + 1

    def _normalize_command(self, args: list) -> tuple[list, str | None]:
        """返回 (参数列表, 命令名)。已取消 P 前缀语法。"""
        cmd_name = self.getArg(args, 0)
        return args, cmd_name

    def _execute_line(self, line: int, args: list) -> int | object:
        """
        执行一行，返回下一个 line 指针（已含「执行完本行再前进」），或 _HALT 结束脚本。
        """
        args, cmd_name = self._normalize_command(args)
        if cmd_name == "" or cmd_name is None:
            return self._next_line(line)

        if cmd_name == "IMPORT":
            return self._cmd_IMPORT(line, args)
        if cmd_name == "START":
            return self._cmd_START(line, args)
        if cmd_name == "PYTHON_RUN":
            return self._cmd_PYTHON_RUN(line, args)
        if cmd_name == "HAS_IMAGE":
            return self._cmd_HAS_IMAGE(line, args)
        if cmd_name == "WAIT_IMAGE":
            return self._cmd_WAIT_IMAGE(line, args)
        if cmd_name == "FIND_IMAGE":
            return self._cmd_FIND_IMAGE(line, args)
        if cmd_name == "CLICK":
            return self._cmd_CLICK(line, args)
        if cmd_name == "SWIP":
            return self._cmd_SWIP(line, args)
        if cmd_name in ("LOG", "ERROR", "WARN", "INFO"):
            return self._cmd_LOG(line, args)
        if cmd_name == "GO":
            return self._cmd_GO(line, args)
        if cmd_name == "SET":
            return self._cmd_SET(line, args)
        if cmd_name == "RES":
            return self._cmd_RES(line, args)
        if cmd_name == "IF":
            return self._cmd_IF(line, args)
        if cmd_name == "CALC":
            return self._cmd_CALC(line, args)
        if cmd_name == "RANDOM":
            return self._cmd_RANDOM(line, args)
        if cmd_name == "BACK":
            return self._cmd_BACK(line, args)
        if cmd_name == "HOME":
            return self._cmd_HOME(line, args)
        if cmd_name == "WAIT":
            return self._cmd_WAIT(line, args)
        if cmd_name == "END":
            return self._cmd_END(line, args)
        if cmd_name == "BREAK":
            return self._cmd_BREAK(line, args)
        if cmd_name == "CONT":
            return self._cmd_CONT(line, args)
        if cmd_name == "IF":
            return self._cmd_IF(line, args)
        if cmd_name == "ELSE_IF":
            return self._cmd_ELSE_IF(line, args)
        if cmd_name == "ELSE":
            return self._cmd_ELSE(line, args)
        if cmd_name == "END_IF":
            return self._cmd_END_IF(line, args)
        if cmd_name == "FOR":
            return self._cmd_FOR(line, args)
        if cmd_name == "END_FOR":
            return self._cmd_END_FOR(line, args)

        return self._next_line(line)

    def _cmd_IMPORT(self, line: int, args: list) -> int:
        self.import_script(args[1])
        return self._next_line(line)

    def _cmd_START(self, line: int, args: list) -> int:
        self.start_app(args[1])
        self.add_cmd_out(f"INFO [启动{args[1]}]")
        return self._next_line(line)

    def _cmd_PYTHON_RUN(self, line: int, args: list) -> int:
        script_name = self.getArg(args, 1)
        script_path = self._import_path_prefix + "." + script_name
        py_frame = {
            "script": f"PY:{script_name}",
            "dir": self.dir,
            "line": line,
            "kind": "PYTHON_RUN",
            "module": script_name,
        }
        self._call_stack_push(py_frame)
        try:
            importlib.import_module(script_path).start(self)
        finally:
            self._call_stack_pop()
        return self._next_line(line)

    def _cmd_HAS_IMAGE(self, line: int, args: list) -> int:
        # 新语法：
        # HAS_IMAGE a b THEN yes no
        # HAS_IMAGE a b
        prefix, yes, no = self._split_then(args)
        names = prefix[1:]
        ok = self.has_images(names)
        if yes is None:
            return self._next_line(line)
        tag_line = self.get_tag(yes if ok else no, line, None)
        return self._after_tag(tag_line)

    def _cmd_WAIT_IMAGE(self, line: int, args: list) -> int:
        # 新语法组合：
        # WAIT_IMAGE img var THEN yes no TIME_OUT 5
        # WAIT_IMAGE img var TIME_OUT 5
        # WAIT_IMAGE img var THEN yes no
        # WAIT_IMAGE img var
        name = self.getArg(args, 1)
        var = self.getArg(args, 2)
        if not name or not var:
            return self._next_line(line)

        prefix1, yes, no = self._split_then(args)
        prefix2, t = self._split_time_out(prefix1)
        time_out = t if t is not None else 5

        pos = self.wait_image(name, time_out)
        if pos:
            self.variable[var] = pos
            if isinstance(var, str):
                self._device_xy_vars.add(var)
            self.add_cmd_out(
                f"INFO {line}:{' '.join(args)} [找到图片({pos[0]},{pos[1]})]"
            )
            if yes is None:
                return self._next_line(line)
            tag_line = self.get_tag(yes, line, pos)
            return self._after_tag(tag_line)

        # 没找到
        if yes is None:
            return self._next_line(line)
        tag_line = self.get_tag(no, line)
        return self._after_tag(tag_line)

    def _cmd_FIND_IMAGE(self, line: int, args: list) -> int:
        # 新语法：
        # FIND_IMAGE img var THEN yes no
        # FIND_IMAGE img var
        name = self.getArg(args, 1)
        var = self.getArg(args, 2)
        if not name or not var:
            return self._next_line(line)

        _, yes, no = self._split_then(args)

        pos = self.find_image(name)
        if pos:
            self.variable[var] = pos
            if isinstance(var, str):
                self._device_xy_vars.add(var)
            self.add_cmd_out(
                f"INFO {line}:{' '.join(args)} [找到图片({pos[0]},{pos[1]})]"
            )
            if yes is None:
                return self._next_line(line)
            tag_line = self.get_tag(yes, line, pos)
            return self._after_tag(tag_line)

        if yes is None:
            return self._next_line(line)
        tag_line = self.get_tag(no, line)
        return self._after_tag(tag_line)

    def _cmd_CLICK(self, line: int, args: list) -> int:
        try:
            if len(args) == 2:
                # 变量坐标：FIND/WAIT_IMAGE 得到的是 device 坐标；SET 得到的是 script 坐标
                x, y, space = self._xy_from_var(args[1])
                x, y = self._scale_xy_if_needed(x, y, space=space)
            else:
                # 直接写坐标：按脚本坐标系缩放到设备分辨率
                x, y = float(args[1]), float(args[2])
                x, y = self._scale_xy_if_needed(x, y, space="script")
            x = random_xy(x)
            y = random_xy(y)
            self.control.click([x, y])
            self._sleep_interruptible(random.uniform(1.0, 2.0), step=0.1)
            self.add_cmd_out(f"INFO {line}:{' '.join(args)} [点击坐标({x},{y})]")
        except Exception as e:
            _ = f"ERROR {line}:{' '.join(args)} [{str(e)}]"
        return self._next_line(line)

    def _cmd_SWIP(self, line: int, args: list) -> int:
        x1, y1, s1 = self._xy_from_var(args[1])
        x2, y2, s2 = self._xy_from_var(args[2])
        x1, y1 = self._scale_xy_if_needed(x1, y1, space=s1)
        x2, y2 = self._scale_xy_if_needed(x2, y2, space=s2)
        duration = self.getArg(args, 3)
        x1 = random_xy(x1)
        y1 = random_xy(y1)
        x2 = random_xy(x2)
        y2 = random_xy(y2)
        if duration is not None:
            duration = (
                float(duration)
                if self.is_num(duration)
                else self.variable[duration]
            )
        try:
            self.control.swiper([x1, y1], [x2, y2], duration)
        except Exception:
            pass
        self.add_cmd_out(
            f"INFO {line}:{' '.join(args)} [滑动坐标({x1},{y1})到({x2},{y2})]"
        )
        return self._next_line(line)

    def _cmd_LOG(self, line: int, args: list) -> int:
        value = args[1]
        if args[1] in self.variable:
            value = self.variable[args[1]]
        self.add_cmd_out(f"{args[0]} {value}")
        return self._next_line(line)

    def _cmd_GO(self, line: int, args: list) -> int:
        tag_line = self.get_tag(args[1], line)
        self.add_cmd_out(f"INFO {tag_line}:{' '.join(args)} [跳转{tag_line}]")
        return self._after_tag(tag_line)

    def _cmd_SET(self, line: int, args: list) -> int:
        """
        SET 自动识别：
        - SET name value        -> 数值/字符串/变量
        - SET name x y          -> 坐标 [x, y]

        兼容旧写法：
        - SET VAR name value
        - SET XY  name x y
        """
        # 兼容旧语法：剥离 VAR/XY
        if len(args) >= 2 and args[1] in ("VAR", "XY"):
            args = [args[0]] + args[2:]

        if len(args) < 3:
            return self._next_line(line)

        name = args[1]
        # 坐标：有两个值
        if len(args) >= 4:
            x = args[2]
            y = args[3]
            # 优先取变量，其次数字，否则保留原值
            xv = self.variable[x] if x in self.variable else (float(x) if self.is_num(x) else x)
            yv = self.variable[y] if y in self.variable else (float(y) if self.is_num(y) else y)
            self.variable[name] = [xv, yv]
            if isinstance(name, str):
                self._device_xy_vars.discard(name)
            return self._next_line(line)

        # 单值：数值/布尔/字符串/变量
        v = args[2]
        if v in self.variable:
            self.variable[name] = self.variable[v]
        else:
            if isinstance(v, str) and v.upper() in ("TRUE", "FALSE"):
                self.variable[name] = v.upper() == "TRUE"
            elif self.is_num(v):
                self.variable[name] = float(v)
            else:
                self.variable[name] = v
        if isinstance(name, str):
            # 单值肯定不是 device 坐标
            self._device_xy_vars.discard(name)
        return self._next_line(line)

    def _cmd_RES(self, line: int, args: list) -> int:
        """
        RES sw sh
        声明脚本坐标系分辨率（默认 1280x720）。之后 CLICK / SWIP 会把“脚本坐标”缩放到设备分辨率。
        """
        try:
            sw = int(float(args[1]))
            sh = int(float(args[2]))
            if sw > 0 and sh > 0:
                self._script_res = (sw, sh)
                self.add_cmd_out(f"INFO {line}:{' '.join(args)} [脚本分辨率={sw}x{sh}]")
        except Exception:
            pass
        return self._next_line(line)

    def _cmd_IF(self, line: int, args: list) -> int:
        value1 = (
            float(args[1]) if self.is_num(args[1]) else self.variable[args[1]]
        )
        value2 = (
            float(args[3]) if self.is_num(args[3]) else self.variable[args[3]]
        )
        res = False
        if args[2] == "==":
            res = value1 == value2
        elif args[2] == "!=":
            res = value1 != value2
        elif args[2] == ">":
            res = value1 > value2
        elif args[2] == ">=":
            res = value1 >= value2
        elif args[2] == "<":
            res = value1 < value2
        elif args[2] == "<=":
            res = value1 <= value2
        if res:
            tag_line = self.get_tag(self.getArg(args, 4), line)
        else:
            tag_line = self.get_tag(self.getArg(args, 5), line)
        return self._after_tag(tag_line)

    def _calc_get_coord_pair(self, name: str, line: int) -> list | None:
        v = self.variable.get(name)
        if not isinstance(v, (list, tuple)) or len(v) < 2:
            self.add_cmd_out(
                f"ERROR {line}: CALC 变量 `{name}` 不是坐标 [x y]（请先 SET 或使用 FIND_IMAGE）"
            )
            return None
        try:
            return [float(v[0]), float(v[1])]
        except (TypeError, ValueError):
            self.add_cmd_out(f"ERROR {line}: CALC 坐标 `{name}` 分量不是数字")
            return None

    def _calc_read_operand(self, token: str, line: int):
        """返回 (kind, value)，kind 为 's'（标量）或 'c'（(x,y) 坐标对）。"""
        t = token.strip()
        if not t:
            self.add_cmd_out(f"ERROR {line}: CALC 操作数为空")
            return None
        if self.is_num(t):
            return ("s", float(t))
        if "." in t:
            base, comp = t.rsplit(".", 1)
            comp = comp.lower()
            if comp not in ("x", "y"):
                self.add_cmd_out(
                    f"ERROR {line}: CALC 坐标分量只支持 `.x` / `.y`，收到 `{token}`"
                )
                return None
            xy = self._calc_get_coord_pair(base, line)
            if xy is None:
                return None
            i = 0 if comp == "x" else 1
            return ("s", float(xy[i]))
        if t not in self.variable:
            self.add_cmd_out(f"ERROR {line}: CALC 未知变量 `{t}`")
            return None
        v = self.variable[t]
        if isinstance(v, (list, tuple)) and len(v) >= 2:
            try:
                return ("c", (float(v[0]), float(v[1])))
            except (TypeError, ValueError):
                self.add_cmd_out(f"ERROR {line}: CALC 变量 `{t}` 不是合法坐标")
                return None
        try:
            return ("s", float(v))
        except (TypeError, ValueError):
            self.add_cmd_out(
                f"ERROR {line}: CALC 变量 `{t}` 不是数字，无法参与运算"
            )
            return None

    def _calc_apply_scalar_op(self, a: float, b: float, op: str, line: int):
        if op == "+":
            return a + b
        if op == "-":
            return a - b
        if op == "*":
            return a * b
        if op == "/":
            if b == 0:
                self.add_cmd_out(f"ERROR {line}: CALC 除数为零")
                return None
            return a / b
        self.add_cmd_out(f"ERROR {line}: CALC 不支持的运算符 `{op}`（支持 + - * /）")
        return None

    def _calc_apply_coord_scalar(
        self, cx: float, cy: float, s: float, op: str, scalar_on_left: bool, line: int
    ):
        """标量在左：s op (cx,cy)；标量在右：(cx,cy) op s。"""
        if scalar_on_left:
            rx = self._calc_apply_scalar_op(s, cx, op, line)
            ry = self._calc_apply_scalar_op(s, cy, op, line)
        else:
            rx = self._calc_apply_scalar_op(cx, s, op, line)
            ry = self._calc_apply_scalar_op(cy, s, op, line)
        if rx is None or ry is None:
            return None
        return (rx, ry)

    def _calc_write_scalar_dest(self, dest_t: str, value: float, line: int) -> bool:
        if "." in dest_t:
            base, comp = dest_t.rsplit(".", 1)
            comp = comp.lower()
            if comp not in ("x", "y"):
                self.add_cmd_out(
                    f"ERROR {line}: CALC 赋值目标只支持 `名` 或 `名.x` / `名.y`，收到 `{dest_t}`"
                )
                return False
            xy = self._calc_get_coord_pair(base, line)
            if xy is None:
                return False
            i = 0 if comp == "x" else 1
            xy[i] = value
            self.variable[base] = xy
            return True
        self.variable[dest_t] = value
        if isinstance(dest_t, str):
            self._device_xy_vars.discard(dest_t)
        return True

    def _calc_write_coord_dest(self, dest_t: str, x: float, y: float, line: int) -> bool:
        if "." in dest_t:
            self.add_cmd_out(
                f"ERROR {line}: CALC 坐标整体运算结果请赋给坐标变量名，不能写 `{dest_t}`"
            )
            return False
        self.variable[dest_t] = [x, y]
        return True

    def _cmd_CALC(self, line: int, args: list) -> int | object:
        """
        CALC 左操作数 运算符 右操作数 目标
        计算 左 op 右，写入 目标。

        标量：CALC count + 1 count
        只改 x 或 y：CALC ya.x - 100 ya.x
        坐标与标量同时作用在 x、y：CALC ya + 1 ya
        坐标与坐标（分量分别运算）：CALC a + b c（a、b、c 均为坐标变量名）
        """
        if len(args) != 5:
            self.add_cmd_out(
                f"ERROR {line}: CALC 需要 4 个参数：左 运算符 右 目标；"
                f"例：CALC count + 1 count；CALC pos.x + 10 pos.x；CALC pos + 1 pos"
            )
            return _HALT

        left_t, op, right_t, dest_t = args[1], args[2], args[3], args[4]
        if op not in ("+", "-", "*", "/"):
            self.add_cmd_out(
                f"ERROR {line}: CALC 运算符必须是 + - * /，当前为 `{op}`"
            )
            return _HALT

        lr = self._calc_read_operand(left_t, line)
        rr = self._calc_read_operand(right_t, line)
        if lr is None or rr is None:
            return _HALT
        lk, lv = lr
        rk, rv = rr

        if lk == "s" and rk == "s":
            res = self._calc_apply_scalar_op(lv, rv, op, line)
            if res is None:
                return _HALT
            if not self._calc_write_scalar_dest(dest_t, res, line):
                return _HALT
            self.add_cmd_out(f"INFO {line}:{' '.join(args)} [计算结果 {res}]")
            return self._next_line(line)

        if lk == "c" and rk == "s":
            pair = self._calc_apply_coord_scalar(
                lv[0], lv[1], rv, op, scalar_on_left=False, line=line
            )
        elif lk == "s" and rk == "c":
            pair = self._calc_apply_coord_scalar(
                rv[0], rv[1], lv, op, scalar_on_left=True, line=line
            )
        elif lk == "c" and rk == "c":
            rx = self._calc_apply_scalar_op(lv[0], rv[0], op, line)
            ry = self._calc_apply_scalar_op(lv[1], rv[1], op, line)
            if rx is None or ry is None:
                return _HALT
            pair = (rx, ry)
        else:
            self.add_cmd_out(f"ERROR {line}: CALC 操作数类型无法组合")
            return _HALT

        if pair is None:
            return _HALT
        if not self._calc_write_coord_dest(dest_t, pair[0], pair[1], line):
            return _HALT
        self.add_cmd_out(
            f"INFO {line}:{' '.join(args)} [计算结果 [{pair[0]}, {pair[1]}]]"
        )
        return self._next_line(line)

    def _cmd_RANDOM(self, line: int, args: list) -> int:
        start = float(self.getArg(args, 1))
        end = float(self.getArg(args, 2))
        name = self.getArg(args, 3)
        value = str(random.uniform(start, end)).split(".")
        value = float(value[0]) + float(value[1][0:2]) / 100
        self.variable[name] = value
        self.add_cmd_out(
            f"INFO {line}:{' '.join(args)} [随机结果{self.variable[name]}]"
        )
        return self._next_line(line)

    def _cmd_BACK(self, line: int, args: list) -> int:
        self.back()
        self.add_cmd_out(f"INFO {line}:{' '.join(args)} [返回]")
        return self._next_line(line)

    def _cmd_HOME(self, line: int, args: list) -> int:
        self.home()
        self.add_cmd_out(f"INFO {line}:{' '.join(args)} [回到主页]")
        return self._next_line(line)

    def _cmd_WAIT(self, line: int, args: list) -> int:
        s_t = (
            float(args[1])
            if self.is_num(args[1])
            else self.variable[args[1]]
        )
        self.add_cmd_out(f"INFO {line}:{' '.join(args)} [等待{s_t}秒]")
        time.sleep(s_t)
        return self._next_line(line)

    def _cmd_END(self, line: int, args: list) -> object:
        _ = line, args
        return _HALT

    def _cmd_BREAK(self, line: int, args: list) -> int | object:
        """
        BREAK：跳出最近一层 FOR 循环。
        - 在循环内：跳到 END_FOR 之后（并弹出该循环帧）
        - 不在循环内：结束脚本
        """
        _ = args
        end_for = self._break_loop_target_line()
        if end_for < 0:
            return _HALT
        return end_for + 1

    def _cmd_CONT(self, line: int, args: list) -> int | object:
        """
        CONT：仅在 FOR 内使用，相当于 continue。
        直接跳到当前最近一层 FOR 的 END_FOR 行，让 END_FOR 执行自增/判断并回跳。
        """
        _ = args
        if not self._for_runtime_stack:
            self.add_cmd_out(f"ERROR {line}:CONT [不在 FOR 循环内，无法 CONT]")
            return _HALT
        end_for = self._for_runtime_stack[-1].get("end")
        try:
            end_for = int(end_for)
        except Exception:
            self.add_cmd_out(f"ERROR {line}:CONT [循环结构异常，无法定位 END_FOR]")
            return _HALT
        return end_for

    def _cmd_IF(self, line: int, args: list) -> int:
        """
        支持两种写法：\n
        1) IF [条件...] [yes_tag] [no_tag]\n
           例如：IF a > 1 yesTag noTag\n
        2) IF [条件...]\n
           ...\n
           ELSE_IF [条件...]\n
           ...\n
           ELSE\n
           ...\n
           END_IF\n
        """
        # 单行 THEN 形式：IF <cond...> THEN yes no
        prefix, yes, no = self._split_then(args)
        if yes is not None:
            cond_tokens = prefix[1:]
            ok = self._eval_condition_tokens(cond_tokens)
            tag_line = self.get_tag(yes if ok else no, line, None)
            return self._after_tag(tag_line)

        # block 形式
        info = self._if_block_map.get(line)
        if info is None:
            # 没有 THEN 也没有块配对：等价 PASS
            return self._next_line(line)
        end = info["end"]
        ok = self._eval_condition_tokens(args[1:])
        self._if_runtime_stack.append({"end": end, "taken": False})
        if ok:
            self._if_runtime_stack[-1]["taken"] = True
            return self._next_line(line)
        # 条件失败：跳到下一个分支头（ELSE_IF/ELSE/END_IF）
        return info["next"]

    def _cmd_ELSE_IF(self, line: int, args: list) -> int:
        info = self._if_block_map.get(line)
        if info is None:
            return self._next_line(line)
        end = info["end"]
        st = self._if_runtime_stack[-1] if self._if_runtime_stack else None
        if st is None or st.get("end") != end:
            # 不在同一个 if 链中，跳过
            return self._next_line(line)
        if st.get("taken"):
            return end + 1
        ok = self._eval_condition_tokens(args[1:])
        if ok:
            st["taken"] = True
            return self._next_line(line)
        return info["next"]

    def _cmd_ELSE(self, line: int, args: list) -> int:
        _ = args
        info = self._if_block_map.get(line)
        if info is None:
            return self._next_line(line)
        end = info["end"]
        st = self._if_runtime_stack[-1] if self._if_runtime_stack else None
        if st is None or st.get("end") != end:
            return self._next_line(line)
        if st.get("taken"):
            return end + 1
        st["taken"] = True
        return self._next_line(line)

    def _cmd_END_IF(self, line: int, args: list) -> int:
        _ = args
        # 弹出对应 end 的帧
        if self._if_runtime_stack and self._if_runtime_stack[-1].get("end") == line:
            self._if_runtime_stack.pop()
        return self._next_line(line)

    def _parse_for_header(self, args: list):
        """
        FOR 支持：\n
        - FOR                          (死循环，直到 BREAK / GO 离开)\n
        - FOR 10                       (循环 10 次)\n
        - FOR varBool                  (当变量为真时循环；每次 END_FOR 再判断)\n
        - FOR a < b                    (三 token 条件循环)\n
        - FOR 变量名 RANGE 1 3         (变量名=1..3)\n
        - FOR 变量名 (RANGE 1 3)       (同上)\n
        - （兼容旧）FOR RANGE 1 3 ...  (i=1..3)\n
        """
        hdr = args[1:]
        if not hdr:
            return ("infinite", None)

        # 允许写成：FOR var (RANGE 1 3)
        if len(hdr) >= 2 and isinstance(hdr[1], str) and hdr[1].startswith("("):
            hdr[1] = hdr[1].lstrip("(")
        if hdr and isinstance(hdr[-1], str) and hdr[-1].endswith(")"):
            hdr[-1] = hdr[-1].rstrip(")")

        # 新范围语法：FOR var RANGE a b
        if len(hdr) >= 4 and str(hdr[1]).upper() == "RANGE":
            var_name = hdr[0]
            a = self._value_of(hdr[2])
            b = self._value_of(hdr[3])
            try:
                start = int(a)
                end = int(b)
            except Exception:
                start = 0
                end = -1
            step = 1 if end >= start else -1
            return ("range", (var_name, start, end, step))

        # 兼容旧范围语法：FOR RANGE a b（变量名默认为 i）
        if len(hdr) >= 3 and str(hdr[0]).upper() == "RANGE":
            a = self._value_of(hdr[1])
            b = self._value_of(hdr[2])
            try:
                start = int(a)
                end = int(b)
            except Exception:
                start = 0
                end = -1
            step = 1 if end >= start else -1
            return ("range", ("i", start, end, step))
        # 纯数字次数
        if len(hdr) == 1:
            v = self._value_of(hdr[0])
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                return ("count", int(v))
            return ("while", hdr)
        # 条件循环（>=3 token 用前三个）
        return ("while", hdr[:3])

    def _cmd_FOR(self, line: int, args: list) -> int:
        info = self._for_block_map.get(line)
        end_for = info["other"] if info else None
        if end_for is None:
            return self._next_line(line)
        mode, payload = self._parse_for_header(args)
        if mode == "infinite":
            self._for_runtime_stack.append(
                {"start": line, "end": end_for, "mode": "infinite"}
            )
            return self._next_line(line)
        if mode == "count":
            remaining = int(payload)
            if remaining <= 0:
                return end_for + 1
            self._for_runtime_stack.append(
                {"start": line, "end": end_for, "mode": "count", "remaining": remaining, "i": 0}
            )
            self.variable["i"] = 0
            return self._next_line(line)
        if mode == "range":
            var_name, start, end, step = payload
            if (step > 0 and start > end) or (step < 0 and start < end):
                return end_for + 1
            self._for_runtime_stack.append(
                {
                    "start": line,
                    "end": end_for,
                    "mode": "range",
                    "cur": start,
                    "endv": end,
                    "step": step,
                    "var": var_name,
                }
            )
            self.variable[str(var_name)] = start
            return self._next_line(line)
        # while
        cond_tokens = payload
        if not self._eval_condition_tokens(cond_tokens):
            return end_for + 1
        self._for_runtime_stack.append(
            {"start": line, "end": end_for, "mode": "while", "cond": cond_tokens}
        )
        return self._next_line(line)

    def _cmd_END_FOR(self, line: int, args: list) -> int:
        _ = args
        if not self._for_runtime_stack:
            return self._next_line(line)
        fr = self._for_runtime_stack[-1]
        if fr.get("end") != line:
            # 不匹配，按普通行
            return self._next_line(line)
        mode = fr.get("mode")
        if mode == "count":
            fr["remaining"] -= 1
            fr["i"] += 1
            if fr["remaining"] > 0:
                self.variable["i"] = fr["i"]
                return fr["start"] + 1
            self._for_runtime_stack.pop()
            return self._next_line(line)
        if mode == "range":
            cur = fr["cur"] + fr["step"]
            fr["cur"] = cur
            if (fr["step"] > 0 and cur <= fr["endv"]) or (fr["step"] < 0 and cur >= fr["endv"]):
                self.variable[str(fr.get("var", "i"))] = cur
                return fr["start"] + 1
            self._for_runtime_stack.pop()
            return self._next_line(line)
        if mode == "while":
            if self._eval_condition_tokens(fr.get("cond") or []):
                return fr["start"] + 1
            self._for_runtime_stack.pop()
            return self._next_line(line)
        if mode == "infinite":
            return fr["start"] + 1
        self._for_runtime_stack.pop()
        return self._next_line(line)

    def run(self):
        script_name = self.dir.replace("/", "\\").split("\\")[-1]
        self.end = False
        line = 0
        run_frame = {
            "script": script_name,
            "dir": self.dir,
            "line": 0,
            "kind": "SCRIPT",
        }
        self._call_stack_push(run_frame)
        self.add_cmd_out(f"LOG 开始{script_name}")
        args: list = []
        try:
            while True:
                if line == -1:
                    break
                if line == -2:
                    self.add_cmd_out("ERROR [未知TAG]")
                    break
                if self._killed_event.is_set():
                    break
                self._call_stack_set_line(line)
                try:
                    args = self.code[line]
                except Exception:
                    break
                try:
                    nxt = self._execute_line(line, args)
                    if nxt is _HALT:
                        break
                    line = nxt
                except Exception as e:
                    self.add_cmd_out(
                        f"ERROR {line}:{' '.join(args)} [{traceback.format_exc()}]"
                    )
                    Bean.cmd_out_list.append(str(e))
                    break
        finally:
            self._call_stack_pop()
        self.end = True
        self.add_cmd_out(f"LOG 结束{script_name}")
        if self.page.after_run_close_script:
            self.page.close_self.emit()
