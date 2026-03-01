"""iFlow 中转管理工具 - 登录 iFlow → 启动代理 → 中转到 OpenClaw API
CLIProxyAPI 引擎内置，无需手动下载。
"""

import json
import os
import re
import subprocess
import sys
import threading
import time
import tkinter as tk
import urllib.request
import webbrowser
from datetime import datetime
from tkinter import filedialog, messagebox

import customtkinter as ctk
import yaml

from config_manager import default_cliproxy_config, save_cliproxy_config, save_openclaw_config

# ---------------------------------------------------------------------------
# Windows 7+ 兼容性
# ---------------------------------------------------------------------------
def _setup_win7_compat():
    """设置 Windows 7+ DPI 感知和兼容性"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # Windows 8.1+ SetProcessDpiAwareness
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            # Windows 7 fallback: SetProcessDPIAware
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (AttributeError, OSError):
                pass
    except Exception:
        pass

def _detect_font():
    """检测系统可用的中文字体（兼容 Windows 7）"""
    preferred = ["Microsoft YaHei UI", "Microsoft YaHei", "SimHei", "SimSun"]
    try:
        import tkinter as _tk
        _root = _tk.Tk()
        _root.withdraw()
        available = list(_root.tk.call("font", "families"))
        _root.destroy()
        for f in preferred:
            if f in available:
                return f
    except Exception:
        pass
    # Win7 一般有微软雅黑，没有 UI 变体则回退
    return "Microsoft YaHei"

_setup_win7_compat()

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

_FONT_FAMILY = _detect_font()
FONT_TITLE = (_FONT_FAMILY, 14, "bold")
FONT_LABEL = (_FONT_FAMILY, 12)
FONT_SMALL = (_FONT_FAMILY, 11)
FONT_MONO = ("Consolas", 12)
FONT_MONO_S = ("Consolas", 11)
PAD = {"padx": 12, "pady": (4, 4)}
SECTION_PAD = {"padx": 12, "pady": (12, 2)}

EXE_NAME = "cli-proxy-api.exe"
# PyInstaller 打包后 __file__ 指向临时目录，实际安装路径用 sys.executable 定位
if getattr(sys, "frozen", False):
    _BASE_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(_BASE_DIR, "engine")

# 可写数据目录：避免写入 Program Files 等受保护路径
_DATA_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "iFlow中转工具")
os.makedirs(os.path.join(_DATA_DIR, "engine"), exist_ok=True)

IFLOW_MODELS = [
    # ── Qwen 系列 ──
    "qwen3-coder-plus",
    "qwen3-max",
    "qwen3-max-preview",
    "qwen3-235b",
    "qwen3-235b-a22b-instruct",
    "qwen3-235b-a22b-thinking-2507",
    "qwen3-vl-plus",
    "qwen3-32b",
    # ── DeepSeek 系列 ──
    "deepseek-v3.2",
    "deepseek-v3.2-reasoner",
    "deepseek-v3.2-chat",
    "deepseek-v3.1",
    "deepseek-v3",
    "deepseek-r1",
    # ── GLM 系列 ──
    "glm-5",
    "glm-4.7",
    "glm-4.6",
    # ── Kimi 系列 ──
    "kimi-k2.5",
    "kimi-k2-thinking",
    "kimi-k2-0905",
    "kimi-k2",
    # ── MiniMax 系列 ──
    "minimax-m2.5",
    "minimax-m2.1",
    "minimax-m2",
    # ── 其他 ──
    "tstars2.0",
    "iflow-rome-30ba3b",
]


# ---------------------------------------------------------------------------
# Auto-detect / download CLIProxyAPI
# ---------------------------------------------------------------------------

def _find_exe():
    """查找内置的 cli-proxy-api.exe（优先 engine/ 目录）"""
    candidates = [
        # 1. engine/ 子目录（内置引擎）
        os.path.join(APP_DIR, EXE_NAME),
        # 2. 与主程序同目录
        os.path.join(_BASE_DIR, EXE_NAME),
    ]
    for p in candidates:
        if p and os.path.isfile(p):
            return os.path.abspath(p)
    return None




# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class Section(ctk.CTkLabel):
    def __init__(self, master, text):
        super().__init__(master, text=f"  {text}", font=FONT_TITLE, anchor="w",
                         fg_color=("gray82", "gray28"), corner_radius=6, height=34)


# ---------------------------------------------------------------------------
# Main App
# ---------------------------------------------------------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("iFlow 中转管理工具")
        self.geometry("760x880")
        self.minsize(680, 650)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._proxy_proc = None
        self._login_proc = None
        self._log_thread = None
        self._exe_path = None
        self._auth_error_count = 0
        self._health_check_id = None

        wrapper = ctk.CTkFrame(self)
        wrapper.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(wrapper)
        scroll.grid(row=0, column=0, sticky="nsew")
        scroll.grid_columnconfigure(0, weight=1)

        self._build_all(scroll)

        # Status bar
        self._status = ctk.CTkLabel(wrapper, text="", font=FONT_SMALL,
                                     anchor="w", height=24, text_color="gray55")
        self._status.grid(row=1, column=0, sticky="ew", padx=8, pady=(4, 2))

        # 强制刷新布局，防止滚动区域初始重叠
        self.update_idletasks()

        # Auto-detect on startup
        self.after(200, self._auto_detect_engine)

    # ==================================================================
    # UI
    # ==================================================================
    def _build_all(self, p):
        r = 0

        # -- 引擎状态 --
        Section(p, "引擎状态  (CLIProxyAPI)").grid(row=r, column=0, sticky="ew", **SECTION_PAD); r += 1

        eng_frame = ctk.CTkFrame(p, fg_color=("gray88", "gray20"), corner_radius=8)
        eng_frame.grid(row=r, column=0, sticky="ew", **PAD); r += 1
        eng_frame.grid_columnconfigure(1, weight=1)

        self._engine_label = ctk.CTkLabel(eng_frame, text="检测中…", font=FONT_LABEL, anchor="w")
        self._engine_label.grid(row=0, column=0, columnspan=2, sticky="ew", padx=12, pady=(8, 2))
        self._engine_path_label = ctk.CTkLabel(eng_frame, text="", font=FONT_MONO_S,
                                                 text_color="gray55", anchor="w")
        self._engine_path_label.grid(row=1, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 4))

        btn_eng = ctk.CTkFrame(eng_frame, fg_color="transparent")
        btn_eng.grid(row=2, column=0, columnspan=2, sticky="ew", padx=12, pady=(0, 8))
        ctk.CTkButton(btn_eng, text="手动选择…", width=100, height=32, font=FONT_SMALL,
                       fg_color="gray40", command=self._browse_exe).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_eng, text="重新检测", width=90, height=32, font=FONT_SMALL,
                       fg_color="gray40", command=self._auto_detect_engine).pack(side="left")

        # -- ① 登录 iFlow --
        Section(p, "① 登录 iFlow 账号").grid(row=r, column=0, sticky="ew", **SECTION_PAD); r += 1
        ctk.CTkLabel(p, text="每次登录添加一个账号，多账号自动轮询分散并发，不受限制",
                     font=FONT_SMALL, anchor="w").grid(row=r, column=0, sticky="ew", **PAD); r += 1

        login_frame = ctk.CTkFrame(p, fg_color="transparent")
        login_frame.grid(row=r, column=0, sticky="ew", **PAD); r += 1
        ctk.CTkButton(login_frame, text="▶  OAuth 登录", width=150, height=38, font=FONT_LABEL,
                       fg_color="#2d8a4e", hover_color="#236b3e",
                       command=lambda: self._run_login("--iflow-login")).pack(side="left", padx=(0, 8))
        ctk.CTkButton(login_frame, text="▶  Cookie 登录", width=150, height=38, font=FONT_LABEL,
                       fg_color="#2d6a8a", hover_color="#1e5570",
                       command=lambda: self._run_login("--iflow-cookie")).pack(side="left", padx=(0, 8))
        ctk.CTkButton(login_frame, text="刷新列表", width=100, height=38, font=FONT_SMALL,
                       fg_color="gray40", command=self._refresh_accounts).pack(side="left")

        self.w_accounts = ctk.CTkTextbox(p, font=FONT_MONO_S, height=80, state="disabled",
                                          fg_color=("gray90", "gray17"))
        self.w_accounts.grid(row=r, column=0, sticky="ew", **PAD); r += 1

        # -- ② 代理服务 --
        Section(p, "② 启动代理服务").grid(row=r, column=0, sticky="ew", **SECTION_PAD); r += 1

        cfg_frame = ctk.CTkFrame(p, fg_color="transparent")
        cfg_frame.grid(row=r, column=0, sticky="ew", **PAD); r += 1
        cfg_frame.grid_columnconfigure(1, weight=1)
        cfg_frame.grid_columnconfigure(3, weight=1)
        ctk.CTkLabel(cfg_frame, text="端口:", font=FONT_LABEL).grid(row=0, column=0, padx=(0, 4))
        self._port_var = ctk.StringVar(value="8317")
        ctk.CTkEntry(cfg_frame, textvariable=self._port_var, font=FONT_MONO, width=80).grid(
            row=0, column=1, sticky="w")
        ctk.CTkLabel(cfg_frame, text="API 密钥:", font=FONT_LABEL).grid(row=0, column=2, padx=(16, 4))
        self._apikey_var = ctk.StringVar(value="sk-iflow-proxy")
        ctk.CTkEntry(cfg_frame, textvariable=self._apikey_var, font=FONT_MONO).grid(
            row=0, column=3, sticky="ew")

        model_frame = ctk.CTkFrame(p, fg_color="transparent")
        model_frame.grid(row=r, column=0, sticky="ew", **PAD); r += 1
        model_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(model_frame, text="iFlow 模型:", font=FONT_LABEL).grid(row=0, column=0, padx=(0, 4))
        self._model_var = ctk.StringVar(value=IFLOW_MODELS[0])
        self._model_combo = ctk.CTkComboBox(
            model_frame, variable=self._model_var, values=IFLOW_MODELS,
            font=FONT_MONO, dropdown_font=FONT_MONO_S, width=360,
            command=lambda _: self._update_api_display())
        self._model_combo.grid(row=0, column=1, sticky="ew")
        ctk.CTkLabel(model_frame, text="可手动输入其他模型名", font=FONT_SMALL,
                     text_color="gray55").grid(row=0, column=2, padx=(8, 0))

        proxy_frame = ctk.CTkFrame(p, fg_color="transparent")
        proxy_frame.grid(row=r, column=0, sticky="ew", **PAD); r += 1
        proxy_frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(proxy_frame, text="网络代理:", font=FONT_LABEL).grid(row=0, column=0, padx=(0, 4))
        self._proxy_var = ctk.StringVar(value="http://127.0.0.1:7897")
        ctk.CTkEntry(proxy_frame, textvariable=self._proxy_var, font=FONT_MONO,
                     placeholder_text="留空=直连  例: http://127.0.0.1:7897").grid(
            row=0, column=1, sticky="ew")

        srv_frame = ctk.CTkFrame(p, fg_color="transparent")
        srv_frame.grid(row=r, column=0, sticky="ew", **PAD); r += 1
        self._btn_start = ctk.CTkButton(srv_frame, text="▶  启动代理服务", width=180, height=42,
                                         font=FONT_TITLE, fg_color="#2d8a4e", hover_color="#236b3e",
                                         command=self._start_proxy)
        self._btn_start.pack(side="left", padx=(0, 8))
        self._btn_stop = ctk.CTkButton(srv_frame, text="■  停止", width=100, height=42,
                                        font=FONT_LABEL, fg_color="#8a2d2d", hover_color="#6b2323",
                                        state="disabled", command=self._stop_proxy)
        self._btn_stop.pack(side="left", padx=(0, 12))
        self._srv_status = ctk.CTkLabel(srv_frame, text="● 未启动", font=FONT_LABEL,
                                         text_color="#ff6b6b")
        self._srv_status.pack(side="left")

        self.w_log = ctk.CTkTextbox(p, font=FONT_MONO_S, height=100, state="disabled",
                                     fg_color=("gray90", "gray17"))
        self.w_log.grid(row=r, column=0, sticky="ew", **PAD); r += 1

        # -- ③ API 端点 --
        Section(p, "③ API 端点  (OpenAI 兼容)").grid(row=r, column=0, sticky="ew", **SECTION_PAD); r += 1
        ctk.CTkLabel(p, text="代理启动后，可直接用于 OpenClaw / Cursor / ChatBox / 代码调用等任何支持 OpenAI API 的客户端",
                     font=FONT_SMALL, anchor="w", wraplength=700).grid(row=r, column=0, sticky="ew", **PAD); r += 1

        api_frame = ctk.CTkFrame(p, fg_color=("gray88", "gray20"), corner_radius=8)
        api_frame.grid(row=r, column=0, sticky="ew", **PAD); r += 1
        api_frame.grid_columnconfigure(1, weight=1)

        self._api_info = {}
        for i, (label, key) in enumerate([
            ("Base URL", "url"), ("API Key", "key"), ("Model", "model")
        ]):
            ctk.CTkLabel(api_frame, text=f"{label}:", font=FONT_LABEL, anchor="e", width=80).grid(
                row=i, column=0, padx=(12, 6), pady=6, sticky="e")
            var = ctk.StringVar(value="—")
            entry = ctk.CTkEntry(api_frame, textvariable=var, font=FONT_MONO, state="readonly",
                                  fg_color="transparent", border_width=0)
            entry.grid(row=i, column=1, sticky="ew", pady=6)
            ctk.CTkButton(api_frame, text="复制", width=50, height=26, font=FONT_SMALL,
                           fg_color="gray40",
                           command=lambda v=var: self._copy(v.get())).grid(
                row=i, column=2, padx=(4, 12), pady=6)
            self._api_info[key] = var

        self._update_api_display()

        # -- Quick copy buttons --
        quick_frame = ctk.CTkFrame(p, fg_color="transparent")
        quick_frame.grid(row=r, column=0, sticky="ew", **PAD); r += 1
        ctk.CTkButton(quick_frame, text="复制 curl 调用示例", width=160,
                       height=34, font=FONT_SMALL, fg_color="#2d6a8a", hover_color="#1e5570",
                       command=self._copy_curl).pack(side="left", padx=(0, 6))
        ctk.CTkButton(quick_frame, text="复制 Python 代码", width=150,
                       height=34, font=FONT_SMALL, fg_color="#2d6a8a", hover_color="#1e5570",
                       command=self._copy_python).pack(side="left", padx=(0, 6))
        ctk.CTkButton(quick_frame, text="复制 JS 代码", width=120,
                       height=34, font=FONT_SMALL, fg_color="#2d6a8a", hover_color="#1e5570",
                       command=self._copy_js).pack(side="left", padx=(0, 6))

        # -- OpenClaw export + 教程 --
        export_frame = ctk.CTkFrame(p, fg_color="transparent")
        export_frame.grid(row=r, column=0, sticky="ew", **PAD); r += 1
        ctk.CTkButton(export_frame, text="导出 OpenClaw 配置", width=160,
                       height=34, font=FONT_SMALL, fg_color="gray40",
                       command=self._export_openclaw).pack(side="left", padx=(0, 6))
        ctk.CTkButton(export_frame, text="复制 OpenClaw JSON", width=155,
                       height=34, font=FONT_SMALL, fg_color="gray40",
                       command=self._copy_openclaw_json).pack(side="left", padx=(0, 6))
        ctk.CTkButton(export_frame, text="配置教程", width=100,
                       height=34, font=FONT_SMALL, fg_color="#6a4c93", hover_color="#543b75",
                       command=self._show_tutorial).pack(side="left")

    # ==================================================================
    # 引擎管理（内置引擎自动检测 / 手动选择）
    # ==================================================================
    def _auto_detect_engine(self):
        exe = _find_exe()
        if exe:
            valid = False
            version_info = ""
            try:
                result = subprocess.run(
                    [exe, "--help"], capture_output=True, encoding="utf-8",
                    errors="replace", timeout=5,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                out = (result.stdout or "") + (result.stderr or "")
                if "cli" in out.lower() or "proxy" in out.lower() or "login" in out.lower() or result.returncode == 0:
                    valid = True
                    for line in out.splitlines():
                        if "version" in line.lower():
                            version_info = line.strip()
                            break
                else:
                    valid = True
            except Exception:
                valid = True

            if valid:
                self._set_exe(exe)
                label = "内置引擎已就绪"
                if version_info:
                    label += "  (" + version_info + ")"
                self._engine_label.configure(text=label, text_color="#4ecb71")
                self._engine_path_label.configure(text=exe)
                self._set_status("引擎已就绪: " + exe)
                self._refresh_accounts()
                return

        self._exe_path = None
        self._engine_label.configure(text="未检测到内置引擎，请点击「手动选择」指定路径", text_color="#ff6b6b")
        self._engine_path_label.configure(text="engine/ 目录下未找到 " + EXE_NAME)
        self._set_status("未检测到 CLIProxyAPI 引擎")

    def _set_exe(self, path):
        self._exe_path = os.path.abspath(path)

    def _browse_exe(self):
        path = filedialog.askopenfilename(
            title="选择 cli-proxy-api.exe",
            filetypes=[("可执行文件", "*.exe"), ("所有文件", "*.*")])
        if path and os.path.isfile(path):
            self._set_exe(path)
            self._engine_label.configure(text="已就绪", text_color="#4ecb71")
            self._engine_path_label.configure(text=self._exe_path)
            self._set_status("已选择引擎: " + self._exe_path)
            self._refresh_accounts()

    def _get_exe(self):
        return self._exe_path

    def _get_writable_config_path(self):
        """返回用户可写目录下的 config.yaml 路径（避免 Program Files 权限问题）"""
        return os.path.join(_DATA_DIR, "engine", "config.yaml")

    # ==================================================================
    # 账号管理
    # ==================================================================
    def _get_auth_dir(self):
        exe = self._get_exe()
        if exe:
            local = os.path.join(os.path.dirname(exe), "auth")
            if os.path.isdir(local):
                return local
        # 检查多种可能的路径
        candidates = [
            os.path.expanduser("~/.cli-proxy-api"),
            os.path.join(os.environ.get("USERPROFILE", ""), ".cli-proxy-api"),
            os.path.join(os.environ.get("HOMEDRIVE", "C:"), os.environ.get("HOMEPATH", "\\"), ".cli-proxy-api"),
        ]
        for d in candidates:
            if d and os.path.isdir(d):
                return d
        return None

    def _refresh_accounts(self):
        self.w_accounts.configure(state="normal")
        self.w_accounts.delete("1.0", "end")

        auth_dir = self._get_auth_dir()
        self._append_log(f"[刷新] 凭证目录: {auth_dir or '未找到'}")
        if not auth_dir:
            self.w_accounts.insert("1.0", "暂无已登录账号，请点击上方按钮登录 iFlow")
            self.w_accounts.configure(state="disabled")
            return

        found = []
        for root, dirs, files in os.walk(auth_dir):
            for f in files:
                fpath = os.path.join(root, f)
                fname = f.lower()
                is_iflow = "iflow" in fname or "iflow" in root.lower()
                if not is_iflow and (fname.endswith(".json") or fname.endswith(".token")):
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                            is_iflow = "iflow" in fp.read(500).lower()
                    except Exception:
                        pass
                if is_iflow:
                    mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
                    found.append(f"  ✓ {f}  (更新: {mtime})")

        if not found:
            for root, dirs, files in os.walk(auth_dir):
                for f in files:
                    fpath = os.path.join(root, f)
                    mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%d %H:%M")
                    rel = os.path.relpath(fpath, auth_dir)
                    found.append(f"  ● {rel}  (更新: {mtime})")

        if found:
            self.w_accounts.insert("1.0", f"已找到 {len(found)} 个凭证:\n" + "\n".join(found))
        else:
            self.w_accounts.insert("1.0", "暂无凭证，请先登录 iFlow 账号")

        self.w_accounts.configure(state="disabled")

    # 用于从 CLIProxyAPI 输出中提取 URL 的正则
    _URL_RE = re.compile(r'(https?://\S+)')

    def _run_login(self, flag):
        exe = self._get_exe()
        if not exe:
            messagebox.showwarning("提示", "引擎未就绪，请先点击「手动选择」指定引擎路径")
            return
        if not os.path.isfile(exe):
            messagebox.showerror("错误", f"引擎文件不存在:\n{exe}\n\n请重新选择")
            self._exe_path = None
            self._auto_detect_engine()
            return

        # 配置文件写入用户可写目录（避免 Program Files 权限问题）
        cfg_path = self._get_writable_config_path()
        if not os.path.isfile(cfg_path):
            try:
                cfg = default_cliproxy_config()
                cfg["port"] = self._get_port()
                cfg["api-keys"] = [self._get_apikey()]
                proxy = self._proxy_var.get().strip()
                if proxy:
                    cfg["proxy-url"] = proxy
                save_cliproxy_config(cfg_path, cfg)
                self._append_log("[配置] 已自动生成: " + cfg_path)
            except Exception as e:
                messagebox.showerror("错误", f"无法创建配置文件:\n{cfg_path}\n\n{e}")
                return

        self._set_status("正在启动登录进程…")

        def _do():
            # 终止之前仍在运行的登录进程（避免端口占用）
            if self._login_proc and self._login_proc.poll() is None:
                self.after(0, self._append_log, "[工具] 正在终止上一个登录进程…")
                try:
                    self._login_proc.terminate()
                    self._login_proc.wait(timeout=3)
                except Exception:
                    try:
                        self._login_proc.kill()
                    except Exception:
                        pass
                self._login_proc = None
                time.sleep(1)  # 等待端口释放

            login_cfg = self._get_writable_config_path()
            self.after(0, self._append_log, "[启动] " + exe + " " + flag + " -no-browser --config " + login_cfg)
            try:
                proc = subprocess.Popen(
                    [exe, flag, "-no-browser", "--config", login_cfg],
                    cwd=os.path.dirname(exe),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.PIPE,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    encoding="utf-8",
                    errors="replace",
                )
            except FileNotFoundError:
                self.after(0, messagebox.showerror, "错误", "找不到可执行文件:\n" + exe)
                return
            except OSError as e:
                self.after(0, messagebox.showerror, "错误", f"无法执行:\n{exe}\n\n{e}")
                return
            except Exception as e:
                self.after(0, messagebox.showerror, "错误", "启动失败: " + str(e))
                return

            self._login_proc = proc
            self.after(0, self._set_status, "登录进程已启动，等待认证…")
            url_opened = False
            waiting_for_enter = False
            login_failed = False

            try:
                for line in proc.stdout:
                    line = line.rstrip("\n\r")
                    if not line:
                        continue
                    self.after(0, self._append_log, line)

                    # 检测登录失败
                    low = line.lower()
                    if "failed" in low or "error" in low and "authentication" in low:
                        login_failed = True

                    # 检测 URL 并用系统默认浏览器打开
                    if not url_opened:
                        m = self._URL_RE.search(line)
                        if m:
                            url = m.group(1)
                            try:
                                # Windows: os.startfile 直接调用 ShellExecuteW，
                                # 比 webbrowser / cmd start 更可靠，不会产生 about: 弹窗
                                if sys.platform == "win32":
                                    os.startfile(url)
                                else:
                                    webbrowser.open(url)
                                url_opened = True
                                self.after(0, self._append_log,
                                           "[工具] 已自动在浏览器中打开登录页面")
                                self.after(0, self._set_status,
                                           "已打开浏览器，请在浏览器中完成 iFlow 登录…")
                            except Exception:
                                self.after(0, self._append_log,
                                           "[工具] 无法自动打开浏览器，请手动复制上方链接到浏览器打开")

                    # 检测等待回调提示，自动发送回车
                    if ("press enter" in low or "keep waiting" in low
                            or "paste the" in low):
                        waiting_for_enter = True

            except Exception:
                pass

            # 如果 CLI 在等待输入，定期发送回车直到进程结束
            if waiting_for_enter and proc.poll() is None:
                def _auto_enter():
                    while proc.poll() is None:
                        try:
                            proc.stdin.write("\n")
                            proc.stdin.flush()
                        except Exception:
                            break
                        time.sleep(2)
                threading.Thread(target=_auto_enter, daemon=True).start()

            proc.wait()
            self._login_proc = None
            code = proc.returncode
            if login_failed:
                self.after(0, self._append_log, "[失败] 登录未成功，请查看上方日志")
                self.after(0, self._set_status, "登录失败，请重试")
            elif code == 0:
                self.after(0, self._append_log, "[完成] 登录成功，正在刷新账号列表…")
                self.after(0, self._set_status, "登录完成")
            else:
                self.after(0, self._append_log, f"[失败] 登录进程退出 (代码:{code})")
                self.after(0, self._set_status, f"登录失败，代码: {code}")
            self.after(500, self._refresh_accounts)

        threading.Thread(target=_do, daemon=True).start()

    # ==================================================================
    # 代理服务控制
    # ==================================================================
    def _start_proxy(self):
        exe = self._get_exe()
        if not exe:
            messagebox.showwarning("提示", "引擎未就绪，请先下载或选择 CLIProxyAPI 程序")
            return
        if not os.path.isfile(exe):
            messagebox.showerror("错误", f"引擎文件不存在:\n{exe}\n\n请重新选择或重新检测")
            self._exe_path = None
            self._auto_detect_engine()
            return

        cfg_path = self._get_writable_config_path()
        port = self._get_port()
        apikey = self._get_apikey()

        cfg = default_cliproxy_config()
        cfg["port"] = port
        cfg["api-keys"] = [apikey]
        proxy = self._proxy_var.get().strip()
        if proxy:
            cfg["proxy-url"] = proxy

        try:
            save_cliproxy_config(cfg_path, cfg)
        except Exception as e:
            self._append_log(f"[错误] 无法写入配置文件: {cfg_path}\n{e}")
            messagebox.showerror("错误", f"无法写入配置文件:\n{cfg_path}\n\n{e}")
            return

        try:
            self._append_log(f"[启动] {exe} --config {cfg_path}")
            self._proxy_proc = subprocess.Popen(
                [exe, "--config", cfg_path],
                cwd=os.path.dirname(exe),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW,
                encoding="utf-8",
                errors="replace",
            )
            self._btn_start.configure(state="disabled")
            self._btn_stop.configure(state="normal")
            self._srv_status.configure(text="● 运行中", text_color="#4ecb71")
            self._update_api_display()
            self._set_status(f"代理服务已启动  |  端口: {port}  |  PID: {self._proxy_proc.pid}")

            self._log_thread = threading.Thread(target=self._read_log, daemon=True)
            self._log_thread.start()

            # Start health check after 10s (give proxy time to init)
            self.after(10000, self._start_health_check)
        except Exception as e:
            self._append_log(f"[错误] 启动代理失败: {e}")
            messagebox.showerror("错误", f"启动代理失败:\n{e}")

    def _stop_proxy(self):
        self._stop_health_check()
        if self._proxy_proc:
            try:
                self._proxy_proc.terminate()
                self._proxy_proc.wait(timeout=5)
            except Exception:
                try:
                    self._proxy_proc.kill()
                except Exception:
                    pass
            self._proxy_proc = None
        self._btn_start.configure(state="normal")
        self._btn_stop.configure(state="disabled")
        self._srv_status.configure(text="● 已停止", text_color="#ff6b6b")
        self._set_status("代理服务已停止")

    # Auth error keywords to monitor in proxy logs
    _AUTH_ERROR_KW = [
        "401", "403", "unauthorized", "unauthenticated",
        "token expired", "token invalid", "invalid token",
        "authentication failed", "auth failed", "credential",
        "refresh token", "access denied", "permission denied",
        "login required", "re-login", "relogin",
        "no valid", "expired", "revoked",
    ]

    def _is_auth_error(self, line):
        """检测日志行是否包含认证相关错误"""
        low = line.lower()
        # Must also contain 'error' or 'fail' or 'warn' to avoid false positives
        if not any(sig in low for sig in ["error", "fail", "warn", "err]", "fatal"]):
            return False
        return any(kw in low for kw in self._AUTH_ERROR_KW)

    def _read_log(self):
        proc = self._proxy_proc
        if not proc or not proc.stdout:
            return
        try:
            for line in proc.stdout:
                line = line.rstrip("\n\r")
                if not line:
                    continue
                if self._is_auth_error(line):
                    self._auth_error_count += 1
                    self.after(0, self._append_log, f"⚠ {line}")
                    if self._auth_error_count >= 3:
                        self.after(0, self._on_auth_alert)
                else:
                    self.after(0, self._append_log, line)
        except Exception:
            pass
        self.after(0, self._on_proxy_exit)

    def _append_log(self, text):
        self.w_log.configure(state="normal")
        self.w_log.insert("end", text + "\n")
        self.w_log.see("end")
        self.w_log.configure(state="disabled")

    def _on_proxy_exit(self):
        self._stop_health_check()
        if self._proxy_proc:
            code = self._proxy_proc.poll()
            self._proxy_proc = None
            self._btn_start.configure(state="normal")
            self._btn_stop.configure(state="disabled")
            self._srv_status.configure(text=f"● 已退出 (代码:{code})", text_color="#ff6b6b")
            self._set_status(f"代理服务已退出，退出代码: {code}")

    def _on_auth_alert(self):
        """Token 异常告警：更新状态并提示用户"""
        self._srv_status.configure(text="● 运行中 (Token异常)", text_color="#ffaa00")
        self._set_status("⚠ 检测到多次认证错误，Token 可能已失效")
        self._append_log("\n⚠⚠⚠ 检测到 Token 异常，建议重新登录 iFlow 账号 ⚠⚠⚠")
        # Only show dialog once per session
        if self._auth_error_count == 3:
            resp = messagebox.askyesno(
                "Token 异常",
                "检测到多次认证错误，iFlow Token 可能已失效。\n\n"
                "可能原因:\n"
                "• Token 过期（长时间未使用）\n"
                "• 在 iFlow 平台撤销了授权\n"
                "• iFlow 平台维护导致 Token 失效\n\n"
                "是否立即重新登录？")
            if resp:
                self._run_login("--iflow-login")

    # ==================================================================
    # 健康检查（代理运行时定期检测）
    # ==================================================================
    def _start_health_check(self):
        """启动定期健康检查"""
        self._auth_error_count = 0
        self._do_health_check()

    def _stop_health_check(self):
        if self._health_check_id:
            self.after_cancel(self._health_check_id)
            self._health_check_id = None

    def _do_health_check(self):
        """定期检查：凭证文件 + API 可用性"""
        if not self._proxy_proc or self._proxy_proc.poll() is not None:
            return

        # 1. Check credential files still exist
        auth_dir = self._get_auth_dir()
        if not auth_dir:
            self._append_log("⚠ 健康检查：未找到凭证目录，Token 可能已被删除")
            self._srv_status.configure(text="● 运行中 (凭证缺失)", text_color="#ffaa00")
        else:
            has_iflow = False
            for f in os.listdir(auth_dir):
                if "iflow" in f.lower():
                    has_iflow = True
                    break
            if not has_iflow:
                self._append_log("⚠ 健康检查：iFlow 凭证文件不存在")
                self._srv_status.configure(text="● 运行中 (凭证缺失)", text_color="#ffaa00")

        # 2. API health check — try to hit the proxy
        threading.Thread(target=self._api_health_ping, daemon=True).start()

        # Schedule next check in 60 seconds
        self._health_check_id = self.after(60000, self._do_health_check)

    def _api_health_ping(self):
        """向代理发送轻量请求检测是否正常响应"""
        port = self._get_port()
        apikey = self._get_apikey()
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/models",
                headers={"Authorization": f"Bearer {apikey}", "User-Agent": "iFlowTool/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                code = resp.getcode()
                if code == 200:
                    data = json.loads(resp.read().decode())
                    model_count = len(data.get("data", []))
                    if model_count > 0:
                        self.after(0, lambda: self._srv_status.configure(
                            text=f"● 运行中 ({model_count}个模型可用)", text_color="#4ecb71"))
                    else:
                        self.after(0, self._append_log,
                                   "⚠ 健康检查：代理返回 0 个可用模型，Token 可能有问题")
                        self.after(0, lambda: self._srv_status.configure(
                            text="● 运行中 (无可用模型)", text_color="#ffaa00"))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                self._auth_error_count += 3
                self.after(0, self._on_auth_alert)
            else:
                self.after(0, self._append_log, f"⚠ 健康检查：HTTP {e.code}")
        except Exception:
            pass  # proxy might be starting up

    # ==================================================================
    # OpenClaw API
    # ==================================================================
    def _get_port(self):
        try:
            return int(self._port_var.get())
        except ValueError:
            return 8317

    def _get_apikey(self):
        return self._apikey_var.get().strip() or "sk-iflow-proxy"

    def _get_model(self):
        return self._model_var.get().strip() or "iflow"

    def _update_api_display(self):
        port = self._get_port()
        apikey = self._get_apikey()
        model = self._get_model()
        self._api_info["url"].set(f"http://127.0.0.1:{port}/v1")
        self._api_info["key"].set(apikey)
        self._api_info["model"].set(model)

    def _build_cliproxy_provider(self):
        """构建 cliproxy provider 配置片段"""
        port = self._get_port()
        apikey = self._get_apikey()
        model = self._get_model()
        return {
            "baseUrl": f"http://127.0.0.1:{port}/v1",
            "apiKey": apikey,
            "api": "openai-completions",
            "models": [{
                "id": model,
                "name": f"iFlow {model}",
                "reasoning": False,
                "input": ["text", "image"],
                "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                "contextWindow": 200000,
                "maxTokens": 64000,
            }],
        }

    def _merge_openclaw_config(self, existing):
        """将 cliproxy provider 合并到现有 OpenClaw 配置中，保留所有原有设置
        
        只修改 AI 模型相关的配置:
        - models.mode / models.providers.cliproxy
        - agents.defaults.model.primary
        - agents.defaults.models 中的 cliproxy/* 条目
        其他配置（auth/channels/gateway/plugins/hooks等）完全不动
        """
        model = self._get_model()
        model_ref = f"cliproxy/{model}"
        provider = self._build_cliproxy_provider()

        # ---- models.providers.cliproxy ----
        if "models" not in existing:
            existing["models"] = {}
        if "mode" not in existing["models"]:
            existing["models"]["mode"] = "merge"
        if "providers" not in existing["models"]:
            existing["models"]["providers"] = {}
        existing["models"]["providers"]["cliproxy"] = provider

        # ---- agents.defaults ----
        if "agents" not in existing:
            existing["agents"] = {}
        if "defaults" not in existing["agents"]:
            existing["agents"]["defaults"] = {}
        defaults = existing["agents"]["defaults"]
        if "models" not in defaults:
            defaults["models"] = {}

        # 清理旧的 cliproxy/* 模型注册（避免残留失效条目）
        stale = [k for k in defaults["models"] if k.startswith("cliproxy/")]
        for k in stale:
            del defaults["models"][k]
        # 注册当前选择的模型
        defaults["models"][model_ref] = {}

        # 设置 primary model
        if "model" not in defaults:
            defaults["model"] = {}
        defaults["model"]["primary"] = model_ref
        if "fallbacks" not in defaults["model"]:
            defaults["model"]["fallbacks"] = []

        return existing

    # ==================================================================
    # API 调用示例生成
    # ==================================================================
    def _copy_curl(self):
        port = self._get_port()
        apikey = self._get_apikey()
        model = self._get_model()
        code = (
            f'curl http://127.0.0.1:{port}/v1/chat/completions \\\n'
            f'  -H "Content-Type: application/json" \\\n'
            f'  -H "Authorization: Bearer {apikey}" \\\n'
            f'  -d \'{{\n'
            f'    "model": "{model}",\n'
            f'    "messages": [{{"role": "user", "content": "你好"}}],\n'
            f'    "stream": true\n'
            f'  }}\''
        )
        self._copy(code)
        self._set_status("已复制 curl 调用示例到剪贴板")

    def _copy_python(self):
        port = self._get_port()
        apikey = self._get_apikey()
        model = self._get_model()
        code = (
            f'from openai import OpenAI\n\n'
            f'client = OpenAI(\n'
            f'    base_url="http://127.0.0.1:{port}/v1",\n'
            f'    api_key="{apikey}",\n'
            f')\n\n'
            f'response = client.chat.completions.create(\n'
            f'    model="{model}",\n'
            f'    messages=[{{"role": "user", "content": "你好"}}],\n'
            f'    stream=True,\n'
            f')\n\n'
            f'for chunk in response:\n'
            f'    if chunk.choices[0].delta.content:\n'
            f'        print(chunk.choices[0].delta.content, end="")\n'
        )
        self._copy(code)
        self._set_status("已复制 Python 调用代码到剪贴板")

    def _copy_js(self):
        port = self._get_port()
        apikey = self._get_apikey()
        model = self._get_model()
        code = (
            f'const response = await fetch("http://127.0.0.1:{port}/v1/chat/completions", {{\n'
            f'  method: "POST",\n'
            f'  headers: {{\n'
            f'    "Content-Type": "application/json",\n'
            f'    "Authorization": "Bearer {apikey}",\n'
            f'  }},\n'
            f'  body: JSON.stringify({{\n'
            f'    model: "{model}",\n'
            f'    messages: [{{ role: "user", content: "你好" }}],\n'
            f'    stream: false,\n'
            f'  }}),\n'
            f'}});\n\n'
            f'const data = await response.json();\n'
            f'console.log(data.choices[0].message.content);\n'
        )
        self._copy(code)
        self._set_status("已复制 JavaScript 调用代码到剪贴板")

    def _export_openclaw(self):
        """智能合并到现有 openclaw.json，不覆盖其他配置"""
        # 默认读取用户的 openclaw.json
        default_path = os.path.join(os.path.expanduser("~"), ".openclaw", "openclaw.json")
        existing = {}
        if os.path.isfile(default_path):
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        merged = self._merge_openclaw_config(existing)

        path = filedialog.asksaveasfilename(
            title="导出 OpenClaw 配置（合并模式）", defaultextension=".json",
            initialdir=os.path.dirname(default_path),
            initialfile="openclaw.json",
            filetypes=[("JSON", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2, ensure_ascii=False)
            self._set_status(f"已导出: {path}")
            model_ref = f"cliproxy/{self._get_model()}"
            messagebox.showinfo("成功",
                f"已将 cliproxy 提供商合并到:\n{path}\n\n"
                f"✔ 保留了原有的所有配置（Telegram、插件等）\n"
                f"✔ 添加了 cliproxy 提供商和模型 {model_ref}\n\n"
                f"运行 openclaw gateway --force 重启生效")
        except Exception as e:
            messagebox.showerror("错误", f"导出失败: {e}")

    def _copy_openclaw_json(self):
        """复制 AI 模型相关的 JSON 配置片段到剪贴板"""
        model = self._get_model()
        model_ref = f"cliproxy/{model}"
        snippet = {
            "models": {
                "mode": "merge",
                "providers": {
                    "cliproxy": self._build_cliproxy_provider()
                }
            },
            "agents": {
                "defaults": {
                    "model": {
                        "primary": model_ref,
                        "fallbacks": []
                    },
                    "models": {
                        model_ref: {}
                    }
                }
            }
        }
        self._copy(json.dumps(snippet, indent=2, ensure_ascii=False))
        self._set_status("已复制 OpenClaw JSON 配置到剪贴板")

    # ==================================================================
    # 配置教程弹窗
    # ==================================================================
    def _show_tutorial(self):
        win = ctk.CTkToplevel(self)
        win.title("配置教程 - iFlow 中转到 OpenClaw")
        win.geometry("660x580")
        win.minsize(550, 400)
        win.transient(self)
        win.protocol("WM_DELETE_WINDOW", win.destroy)
        win.grid_rowconfigure(0, weight=1)
        win.grid_columnconfigure(0, weight=1)

        port = self._get_port()
        apikey = self._get_apikey()
        model = self._get_model()

        tutorial_text = (
            "========================================\n"
            "  第一步：登录 iFlow 账号\n"
            "========================================\n"
            "\n"
            "  1. 确认引擎状态显示「内置引擎已就绪」\n"
            "  2. 点击「OAuth 登录」按钮\n"
            "  3. 浏览器会自动打开 iFlow 登录页面\n"
            "  4. 在浏览器中完成登录（手机号/扫码）\n"
            "  5. 登录成功后本工具会自动识别，账号列表刷新\n"
            "\n"
            "  提示：可登录多个账号，系统会自动轮询分散并发。\n"
            "\n"
            "\n"
            "========================================\n"
            "  第二步：启动代理服务\n"
            "========================================\n"
            "\n"
            "  1. 设置端口（默认 8317）和 API 密钥\n"
            "  2. 选择 iFlow 模型（如 GLM-5、Qwen3-Max）\n"
            "  3. 如需科学上网，填写网络代理地址\n"
            "  4. 点击「启动代理服务」\n"
            "  5. 状态显示「运行中」即代理已就绪\n"
            "\n"
            "\n"
            "========================================\n"
            "  第三步：配置 OpenClaw\n"
            "========================================\n"
            "\n"
            "  方法一：使用「导出 OpenClaw 配置」按钮\n"
            "    - 点击后选择保存路径\n"
            "      (默认 ~/.openclaw/openclaw.json)\n"
            "    - 工具会智能合并，不覆盖已有配置\n"
            "    - 保存后执行: openclaw gateway --force\n"
            "\n"
            "  方法二：使用「复制 OpenClaw JSON」按钮\n"
            "    - 复制配置命令到剪贴板\n"
            "    - 粘贴到终端执行即可\n"
            "\n"
            "  方法三：手动在 openclaw.json 中添加:\n"
            "\n"
            "  {\n"
            '    "models": {\n'
            '      "mode": "merge",\n'
            '      "providers": {\n'
            '        "cliproxy": {\n'
            f'          "baseUrl": "http://127.0.0.1:{port}/v1",\n'
            f'          "apiKey": "{apikey}",\n'
            '          "api": "openai-completions",\n'
            '          "models": [{\n'
            f'            "id": "{model}",\n'
            f'            "name": "iFlow {model}",\n'
            '            "reasoning": false,\n'
            '            "input": ["text", "image"],\n'
            '            "contextWindow": 200000,\n'
            '            "maxTokens": 64000\n'
            "          }]\n"
            "        }\n"
            "      }\n"
            "    },\n"
            '    "agents": {\n'
            '      "defaults": {\n'
            f'        "model": {{"primary": "cliproxy/{model}"}},\n'
            f'        "models": {{"cliproxy/{model}": {{}}}}\n'
            "      }\n"
            "    }\n"
            "  }\n"
            "\n"
            "\n"
            "========================================\n"
            "  第四步：在 OpenClaw / Cursor 中使用\n"
            "========================================\n"
            "\n"
            f"  模型名称: cliproxy/{model}\n"
            f"  API 地址: http://127.0.0.1:{port}/v1\n"
            f"  API 密钥: {apikey}\n"
            "\n"
            "  配置完成后重启 OpenClaw:\n"
            "    openclaw gateway --force\n"
            "\n"
            "  也可用于 Cursor / ChatBox / 任何 OpenAI 兼容客户端。\n"
        )

        tb = ctk.CTkTextbox(win, font=FONT_MONO_S, wrap="word",
                             fg_color=("gray92", "gray14"))
        tb.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 6))
        tb.insert("1.0", tutorial_text)
        tb.configure(state="disabled")

        ctk.CTkButton(win, text="关闭", width=120, height=36, font=FONT_LABEL,
                       command=win.destroy).grid(row=1, column=0, pady=(4, 12))

    # ==================================================================
    # Helpers
    # ==================================================================
    def _copy(self, text):
        self.clipboard_clear()
        self.clipboard_append(text)

    def _set_status(self, msg):
        self._status.configure(text=msg)

    def _on_close(self):
        for proc in (self._proxy_proc, self._login_proc):
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
