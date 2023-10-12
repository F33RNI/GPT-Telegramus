# 🤖 GPT-Telegramus
### The best Telegram bot for ChatGPT, EdgeGPT (aka Bing AI), DALL-E, Bing Image generator and Bard with stream writing, requests with images (for Bard only), multiple languages, admin control, automatic proxy searcher, data logging and more!
<div style="width:100%;text-align:center;">
   <p align="center">
      <img src="https://badges.frapsoft.com/os/v1/open-source.png?v=103" >
   </p>
</div>
<div style="width:100%;text-align:center;">
   <p align="center">
      <a href="https://www.youtube.com/@F3RNI"><img alt="YouTube" src="https://img.shields.io/badge/-YouTube-red" ></a>
      <a href="https://f3rni.bandcamp.com"><img alt="Bandcamp" src="https://img.shields.io/badge/-Bandcamp-cyan" ></a>
      <a href="https://open.spotify.com/artist/22PQ62alehywlYiksbtzsm"><img alt="Spotify" src="https://img.shields.io/badge/-Spotify-green" ></a>
      <a href="https://soundcloud.com/f3rni"><img alt="SoundCloud" src="https://img.shields.io/badge/-SoundCloud-orange" ></a>
   </p>
</div>

![](Banner.png)

----------

## 😋 Support project

Support the project by buying and listening to my music 🎵

- 🟦 [Bandcamp](https://f3rni.bandcamp.com)
- 🟧 [SoundCloud](https://soundcloud.com/f3rni)

Or message me if you would like to donate 💰

[![Star History Chart](https://api.star-history.com/svg?repos=F33RNI/GPT-Telegramus&type=Date)](https://star-history.com/#F33RNI/GPT-Telegramus&Date)

----------

## 🤗 Contributors

- 1️⃣ [Sprav04ka](https://github.com/Sprav04ka) - *Tofii'skovyi' language, Testing, Super beautiful DIY jack o'lantern (for poster), Motivation*
- 2️⃣ [Sergey Krashevich](https://github.com/skrashevich) - *Docker, GitHub Actions*
- 3️⃣ [Wahit Fitriyanto](https://github.com/wahitftry) - *Indonesian language*
- 4️⃣ [Alexander Fadeyev](https://github.com/alfsoft) - *EdgeGPT Fix*

----------

## 📙 Dependencies

- **ChatGPT** (ChatGPT by OpenAI): https://chat.openai.com/chat
- **Bing chat** (EdgeGPT by Microsoft): https://bing.com/chat
- **DALL-E** (DALLE by OpenAI): https://openai.com/dall-e-2/
- **Bard** (Bard by Google): https://bard.google.com/
- **acheong08/ChatGPT** (API): https://github.com/acheong08/ChatGPT
- **acheong08/EdgeGPT** (API): https://github.com/acheong08/EdgeGPT
- **jacobgelling/EdgeGPT** (API): https://github.com/jacobgelling/EdgeGPT
- **dsdanielpark/Bard-API** (API): https://github.com/dsdanielpark/Bard-API
- **acheong08/BingImageCreator** (API): https://github.com/acheong08/BingImageCreator
- **python-telegram-bot** (Telegram bot API): https://github.com/python-telegram-bot/python-telegram-bot

----------

## ❓ Get started

1. Install Python and pip
2. Download source code
3. Install requirements `pip install -r requirements.txt --upgrade`
4. Access the modules you want to use (Generate an API key to ChatGPT / DALL-E, save cookies for EdgeGPT / Bard)
5. Carefully change all the settings (in the `config.json` file) to suit your needs. If you have questions regarding any setting, open an issue, I will add a more detailed description
6. Create bot at https://t.me/BotFather
7. Type Bot's token into `api_key` in `telegram` in `config.json` file
8. Run main script `python main.py`

- **ChatGPT**
  - Browser-like Chat-GPT. Currently, without extensions and image requests (text only) (because I don't have a paid account to test it)
  - Stream response support
  - Chat history support
  - Works better with API type 1 and an access_token for authentication
  - Note: Please refer to the `🔗 Chat-GPT Base URL (proxy)` section for correct usage.
- **DALL·E**
  - Image generation tool from OpenAI
  - Requires an OpenAI account with unexpired credits
- **EdgeGPT (aka Bing AI) (aka Sydney)**
  - Supports conversation style `/style`
  - Stream response support
  - Chat history support
  - Web-browsing and sources support
  - Unfortunately, it can't accept images as input yet, nor can it generate them. Please use Bing ImageGen to generate images.
- **Bing ImageGen**
  - Bing Image Generator. Used as a separate module due to issues with the EdgeGPT module
  - Free and unlimited
- **Bard**
  - Google's Bard AI
  - Chat history support
  - Web-browsing support (probably)
  - Now supports requests with images (you can send an image with text to it) **NEW**

----------

## 💬 Bot messages

- You can edit telegram bot messages by editing file `messages.json`. You can add new lines by adding `\\n`
- You can add a new language simply by copying one of existing language (with `{}`) to the end of file (before the last `]`) and translating all values

**Note:** make sure you don't delete argumensts `{0}`, `{1}`, ... in message and please restart python script to apply changes

### Currently available languages:

- 🇺🇸 English
- 🇷🇺 Русский
- ‍☠️ Тофийсковый
- 🇮🇩 Bahasa Indonesia

If you want to add a language, create a pull request 💜

----------

## 🐧 Running as service on linux

1. Install Python and pip
2. Clone repo
   1. `git clone https://github.com/F33RNI/GPT-Telegramus/`
   2. `cd GPT-Telegramus`
3. Edit `config.json`
4. Install systemd
   1. `sudo apt-get install -y systemd`
5. Create new service file
   1. `sudo nano /etc/systemd/system/gpt-telegramus.service`
      ```
      [Unit]
      Description=GPT-Telegramus service
      After=multi-user.target
      
      [Service]
      Type=simple
      Restart=always
      WorkingDirectory=YOUR DIRECTORY HERE/GPT-Telegramus
      ExecStart=YOUR DIRECTORY HERE/GPT-Telegramus/run.sh
      RestartSec=5
      
      [Install]
      WantedBy=multi-user.target
      
      ```
6. Reload systemctl daemon
   1. `sudo systemctl daemon-reload`
7. Enable and start service
   1. `sudo systemctl enable gpt-telegramus.service`
   2. `sudo systemctl start gpt-telegramus.service`

----------

## 🐋 Running in Docker

**WARNING: not tested**

1. Install Docker
2. Clone repo
3. Build container
    ```shell
    docker buildx build -t telegramus --load -f Dockerfile .
    ```
4. Run the container
    ```shell
    docker run -d --name gpt-telegramus --restart on-failure telegramus
    ```

**Note:** You can specify settings and messages files and chats folder location. (default location is in project folder):
```shell
docker run -d -e TELEGRAMUS_SETTINGS_FILE="PATH_TO_config.json" --name gpt-telegramus --restart on-failure telegramus
```

----------

## 🔗 Chat-GPT Base URL (proxy)

Default base URL by acheong08/ChatGPT stopped working. Below is an instruction on how to launch your own ChatGPT proxy server (on Linux)

1. Install GO
   1. `sudo apt-get update`
   2. `sudo apt-get install golang-go`
2. Clone acheong08/ChatGPTProxy repo
   1. `git clone https://github.com/acheong08/ChatGPTProxy/tree/main`
   2. `cd ChatGPTProxy`
3. Build it
   1. `go build`
4. Install systemd
   1. `sudo apt-get install systemd`
5. Create service
   1. `sudo nano /etc/systemd/system/chatgpt-proxy.service`
      ```
      [Unit]
      Description=ChatGPTProxy service
      After=multi-user.target
      
      [Service]
      Type=simple
      Restart=always
      
      # Proxy (if needed, or remove this and next line)
      Environment="http_proxy=http://USERNAME:PASSWORD@IP:PORT"
      
      # ChatGPT login
      Environment="OPENAI_EMAIL=YOUR_EMAIL"
      Environment="OPENAI_PASSWORD=YOUR_PASSWORD"
      
      WorkingDirectory=PATH_TO_ChatGPTProxy_DIRECTORY
      ExecStart=PATH_TO_ChatGPTProxy_DIRECTORY/ChatGPTProxy
      RestartSec=5
      
      [Install]
      WantedBy=multi-user.target
      
      ```
6. Reload systemctl daemon
   1. `sudo systemctl daemon-reload`
7. Enable and start service
   1. `sudo systemctl enable chatgpt-proxy.service`
   2. `sudo systemctl start chatgpt-proxy.service`
8. See logs to make sure it's running and see current port
   1. `systemctl status chatgpt-proxy.service`
9. Add it's IP to `config.json`
   1. ex. `"base_url": "http://127.0.0.0:9090/api/",`

----------

## 🌎 Proxy to bypass geo-blocking

### NOT TESTED

It is possible to bypass geo-blocking of ChatGPT, EdgeGPT, DALL-E or Bard. GPT-Telegramus includes automatic proxy-list downloading with periodic checks

1. Set `enabled` in `proxy_automation` in `config.json` to `true`
2. Set `auto` in `proxy` for modules you want to connect automatic proxy search
3. Restart app and hope for the best. 

GPT-Telegramus will download the proxy list itself and start trying various proxies (see console for logs).
Sometimes, searching for a proxy can take a long time. If you think that the found proxy is not suitable, you can restart the bot using the `/restart` command

- To use **manual proxy**, specify tham in `http://IP:Port` or `http://user:password@IP:Port` format (even if they are HTTPS proxies)  in `proxy` for modules you need

----------

## 🤖 Telegram bot commands

- 📄 `/start` - Welcome message and bot version
- ❓ `/help` - Show this message
- ↕️ `/module` - Change module to chat with
- 🧹 `/clear` - Clear chat history
- 🌎 `/lang` - Change the language
- 🆔 `/chatid` - Show your chat_id
- `/style` - Bing AI conversation style
- `/chatgpt <Text request>` - Request to the ChatGPT module
- `/dalle <Text request>` - Request to the DALL-E module
- `/bing <Text request>` - Request to the Bing AI module
- `/bingigen <Text request>` - Request to the Bing Image Generator
- `/bard <Text request>` - Request to the Bard module


### Admin commands:
- 💬 `/queue` - Show requests queue
- 🔃 `/restart` - Restart proxies and telegram bot
- 👤 `/users` - Show list of all users
- 🔨 `/ban <id> [reason]` - Ban a user by their id with reason (optional)
- 🔓 `/unban <id>` - Unban a user by their id
- 📢 `/broadcast <message>` - Send text message to everyone except banned users

----------

## 📄 Chat history

GPT-Telegramus saves chat history for some modules locally (`"conversations_dir": "conversations"`) to keep conversation with users

----------

## 📜 Data collecting

GPT-Telegramus has a built-in data collecting function (request and response)

- **For ChatGPT, EdgeGPT (aka Bing AI) and Bard** response is saved as plain text and Base64-encoded images
- **For DALL-E and Bing Image generator** response is saved as Base64-encoded image (in the same text file)

You can enable and configure data collection in config in `data_collecting` block

**NOTE:** Please make sure you notify your bot users that you are collecting data

----------

## 📝 TODO

- Add some free GPT-4 model
- Add image input and generation for EdgeGPT (and ChatGPT?)
- Add Bard's text-to-speech
- Add list of commands

----------

## ✨ Contribution

- Anyone can contribute! Just create a pull request

----------

### 🚧 P.S. This project is still under development!

- If you find a **bug** in GPT-Telegramus, please create an Issue
