# iFlow 中转管理工具

一款 Windows 桌面应用（兼容 Windows 7 SP1 及以上），用于一键登录 iFlow 并通过 CLIProxyAPI 引擎中转为 OpenAI 兼容 API，对接 OpenClaw / Cursor / ChatBox 等客户端。

**CLIProxyAPI 引擎已内置**，安装后即可使用，无需额外下载。

## 功能

- **一键登录**：OAuth / Cookie 两种方式登录 iFlow 账号
- **多账号轮询**：多账号自动负载均衡，分散并发不受限制
- **内置引擎**：CLIProxyAPI 引擎随安装包一起分发，开箱即用
- **OpenAI 兼容 API**：代理启动后提供标准 OpenAI API 端点
- **OpenClaw 对接**：一键导出 / 合并 OpenClaw 配置
- **代码示例**：一键复制 curl / Python / JavaScript 调用代码
- **健康监控**：自动检测 Token 异常并提醒重新登录

## 系统要求

- Windows 7 SP1 / 8 / 8.1 / 10 / 11（64 位）

## 安装

运行 `iFlow中转工具_Setup_x.x.x.exe` 安装程序即可。

> **注意**：每次安装会清理之前的登录数据，需要重新登录 iFlow 账号。

## 使用说明

1. 启动后确认「引擎状态」显示「内置引擎已就绪」
2. 点击「OAuth 登录」或「Cookie 登录」添加 iFlow 账号
3. 配置端口、API 密钥、模型，点击「启动代理服务」
4. 在 API 端点区域复制 Base URL / API Key / Model 到目标客户端

## 开发者构建

```bash
# 安装依赖
pip install -r requirements.txt
pip install pyinstaller

# 打包为单文件 exe
pyinstaller "iFlow中转工具.spec"

# 生成安装包（需要 Inno Setup 6）
# 用 Inno Setup Compiler 打开 installer.iss 并编译
```

## 项目结构

```
main.py              # 主程序 GUI
config_manager.py    # 配置文件读写
engine/              # 内置 CLIProxyAPI 引擎
iflow.manifest       # Windows 7+ 应用清单
iFlow中转工具.spec    # PyInstaller 打包配置
installer.iss        # Inno Setup 安装包脚本
```
