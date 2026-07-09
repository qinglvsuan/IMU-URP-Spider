> **本工具基于 Vibe Coding 辅助创作完成**
# 🕷️ IMU-URP-Spider (内大教务成绩监控)

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.12-blue.svg" alt="Python Version">
  <img src="https://img.shields.io/badge/Flask-3.1-green.svg" alt="Flask Version">
  <img src="https://img.shields.io/badge/Docker-Supported-2496ED.svg" alt="Docker">
  <img src="https://img.shields.io/badge/License-WTFPL-purple.svg" alt="License">
</p>

基于 Python 构建，无需庞大的无头浏览器即可完成 RSA 加密与模拟登录，极低资源占用（内存 < 50MB），非常适合部署在个人闲置的低配 VPS 上。

借鉴与参考了 [YCITSpider](https://github.com/sinyu1012/YCITSpider) 与 [vscode-jwxt-imu](https://github.com/NiuHK/vscode-jwxt-imu) 的接口思路，针对内大新版教务系统进行了优化重构。

### ✨ 核心特性
- **纯本地无感刷新**：彻底重构前端请求逻辑，仪表盘（成绩、GPA 等）均从本地 SQLite 数据库秒级直出，拒绝页面刷新时带来的卡顿和无效教务系统请求。
- **智能防账号锁定**：内置底层的密码试错熔断机制。一旦后台发现密码错误，会立刻彻底切断自动登录功能，避免死循环爆破导致教务账号被锁定。
- **灵活的 UI 管理**：无缝的深浅色模式切换支持，以及极致响应的前端交互。



---

## 🐳 Docker 部署（推荐）

本项目镜像已发布至 [DockerHub](https://hub.docker.com/r/qinglvsuan/imu-urp-spider)。强烈建议使用 Docker 部署，环境隔离且更新方便。

### 1. 创建配置文件
在任意空目录下新建一个 `docker-compose.yml` 文件，填入以下内容：

```yaml
services:
  imu-spider:
    image: qinglvsuan/imu-urp-spider:latest
    container_name: imu-spider
    restart: unless-stopped
    ports:
      - "5000:5000"
    volumes:
      # 持久化 SQLite 数据库（包含所有用户配置与爬取的成绩数据）
      - ./data:/app/data
    environment:
      - PYTHONUNBUFFERED=1
      - TZ=Asia/Shanghai
```

### 2. 一键启动
在 `docker-compose.yml` 所在的目录中执行：
```bash
docker compose up -d
```
完成后，访问 `http://127.0.0.1:5000`（或你的服务器IP）进入 Web 面板。

### 3. 在 Web 界面完成配置


### 常用 Docker 命令
```bash
# 查看运行日志
docker compose logs -f

# 拉取最新镜像并重启
docker compose pull
docker compose up -d
```

---

## 🚀 Ubuntu 裸机部署 (systemd)

如果你不想使用 Docker，也可以直接在 Ubuntu 上运行。

### 1. 准备环境与代码
```bash
git clone https://github.com/qinglvsuan/IMU-URP-Spider.git /opt/imu-spider
cd /opt/imu-spider
```

### 2. 执行安装脚本
```bash
chmod +x install.sh
./install.sh
```

### 3. 配置并启动服务
首次启动后，访问 `http://你的IP:5000` 在 Web 界面中完成各项设置。注册并启动后台服务：
```bash
sudo cp imu-spider.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now imu-spider
```

### 常用系统命令
```bash
# 查看服务运行状态
sudo systemctl status imu-spider

# 查看实时日志
sudo journalctl -u imu-spider -f
```

---

## ⚙️ 通知与系统配置说明

本项目采用 **Web 界面图形化配置**，所有的配置均保存在本地 SQLite 数据库中。

### 教务与系统配置
在浏览器的**设置**页面中，你可以配置：
- **教务系统账号密码**：用于自动登录拉取成绩。
- **成绩检查间隔（分钟）**：默认 10 分钟。
- **面板访问密码**：保护你的 Web 面板不被外人访问（留空则不设密）。

### 消息推送配置
在界面中填入以下任意渠道的凭证并保存，即可开启推送。你还可以点击「发送测试通知」按钮来验证。

**📧 邮件通知**
- 填写 SMTP 服务器（如 smtp.qq.com）、端口（465）、发件人邮箱及授权码。

**📱 Server酱 (微信推送)**
- 前往 [Server酱](https://sct.ftqq.com/) 注册，复制 `SendKey` 填入即可。

**✈️ Telegram Bot**
- 联系 `@BotFather` 创建机器人获取 Token，联系 `@userinfobot` 获取 Chat ID。

---

## 🛠️ 技术栈

- **语言框架**: Python 3.12, Flask 3.1
- **网络请求**: Requests, BeautifulSoup4, lxml
- **验证码识别**: ddddocr
- **加密处理**: PyCryptodome (RSA 加密解密)
- **任务调度**: APScheduler
- **数据持久**: SQLite3
- **前端界面**: 纯原生 HTML/CSS/JS (无外部框架依赖)

---

## ⚠️ 免责声明

1. **隐私安全**：本项目纯粹作为个人学业管理辅助工具，**程序运行产生的所有数据均保存在本地 SQLite 数据库中，不会上传至任何第三方服务器**。
2. **账号安全**：面板密码及教务账号加密存储在本地 `data/spider.db` 数据库中，请勿将数据库文件分享给他人。
3. **合理使用**：请勿将默认的检查间隔设置得过短（建议 >= 10分钟），避免对学校教务系统服务器造成不必要的压力，违规高频访问可能导致 IP 或账号被封禁。
4. **责任声明**：因不当使用本工具造成的一切后果由使用者自行承担，开发者不对因教务系统改版导致的功能失效负责。

---

## 📄 License

[WTFPL License](LICENSE)
