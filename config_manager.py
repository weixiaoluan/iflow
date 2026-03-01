"""配置文件读写模块，处理 CLIProxyAPI config.yaml 和 OpenClaw openclaw.json"""

import json
import os
import yaml


def default_cliproxy_config():
    """返回 CLIProxyAPI 的默认配置"""
    return {
        "host": "",
        "port": 8317,
        "tls": {"enable": False, "cert": "", "key": ""},
        "remote-management": {
            "allow-remote": False,
            "secret-key": "",
            "disable-control-panel": False,
        },
        "auth-dir": "~/.cli-proxy-api",
        "api-keys": ["your-api-key-1"],
        "debug": False,
        "commercial-mode": False,
        "logging-to-file": False,
        "logs-max-total-size-mb": 0,
        "error-logs-max-files": 10,
        "usage-statistics-enabled": False,
        "disable-cooling": False,
        "proxy-url": "",
        "force-model-prefix": False,
        "request-retry": 3,
        "max-retry-interval": 30,
        "quota-exceeded": {
            "switch-project": True,
            "switch-preview-model": True,
        },
        "routing": {"strategy": "round-robin"},
        "ws-auth": False,
        "streaming": {"keepalive-seconds": 15, "bootstrap-retries": 2},
        "nonstream-keepalive-interval": 30,
        "oauth-model-alias": {},
    }


def default_openclaw_config():
    """返回 OpenClaw 的默认配置"""
    return {
        "maxConcurrent": 2,
        "subagents": {"maxConcurrent": 4},
        "agents": {
            "defaults": {
                "model": {"primary": "cliproxy/iflow-model", "fallbacks": []},
                "models": {"cliproxy/iflow-model": {}},
            }
        },
        "models": {
            "mode": "merge",
            "providers": {
                "cliproxy": {
                    "baseUrl": "http://127.0.0.1:8317/v1",
                    "apiKey": "your-api-key-1",
                    "api": "openai-completions",
                    "models": [
                        {
                            "id": "iflow-model",
                            "name": "iFlow via CLIProxyAPI",
                            "reasoning": True,
                            "input": ["text", "image"],
                            "contextWindow": 200000,
                            "maxTokens": 64000,
                        }
                    ],
                }
            },
        },
        "heartbeat": {"model": ""},
    }


def load_cliproxy_config(path):
    """加载 CLIProxyAPI config.yaml"""
    defaults = default_cliproxy_config()
    if not os.path.isfile(path):
        return defaults
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not isinstance(data, dict):
            return defaults
        _deep_merge(defaults, data)
        return defaults
    except Exception:
        return defaults


def save_cliproxy_config(path, config):
    """保存 CLIProxyAPI config.yaml"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    clean = _strip_empty(config)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            clean,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )


def load_openclaw_config(path):
    """加载 OpenClaw openclaw.json"""
    defaults = default_openclaw_config()
    if not os.path.isfile(path):
        return defaults
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return defaults
        _deep_merge(defaults, data)
        return defaults
    except Exception:
        return defaults


def save_openclaw_config(path, config):
    """保存 OpenClaw openclaw.json"""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def _deep_merge(base, override):
    """将 override 递归合并到 base 中"""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def _strip_empty(d):
    """移除值为空字符串的顶层键（可选清理）"""
    if not isinstance(d, dict):
        return d
    return {k: v for k, v in d.items() if v != "" or k in ("host", "proxy-url")}
