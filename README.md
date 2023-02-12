# GPT-Telegramus
## ChatGPT and DALLE implementation as a telegram bot
<div style="width:100%;text-align:center;">
    <p align="center">
        <img src="https://badges.frapsoft.com/os/v1/open-source.png?v=103" >
        <a href="https://soundcloud.com/f3rni"><img alt="SoundCloud" src="https://img.shields.io/badge/-SoundCloud-orange" ></a>
        <a href="https://www.youtube.com/@F3RNI"><img alt="YouTube" src="https://img.shields.io/badge/-YouTube-red" ></a>
    </p>
</div>
<div style="width:100%;text-align:center;">
    <p align="center">
        <img src="Screenshots/start.png" width="auto" height="300">
        <img src="Screenshots/chatgpt.png" width="auto" height="300">
        <img src="Screenshots/dalle.png" width="auto" height="300">
    </p>
</div>

----------

## Dependencies

- **ChatGPT** (ChatGPT by OpenAI): https://chat.openai.com/chat
- **DALLE** (DALLE by OpenAI): https://openai.com/dall-e-2/
- **acheong08/ChatGPT** (API): https://github.com/acheong08/ChatGPT
- **python-telegram-bot** (Telegram bot API): https://github.com/python-telegram-bot/python-telegram-bot

----------

## Get started

1. Install Python and pip
2. Download source code
3. Install requirements `pip install -r requirements.txt --upgrade`
4. Create bot at https://t.me/BotFather
5. Type Bot's token into `telegram_api_key` in `settings.json` file
6. Create account at OpenAI using email and password
7. Type OpenAI account email and password into `chatgpt_auth_email` and `chatgpt_auth_password` in `settings.json` file
8. For DALL-E, generate API Key https://platform.openai.com/account/api-keys
9. Type OpenAI API Key into `open_ai_api_key` in `settings.json` file
10. Run main script `python main.py`

----------

## Bot messages

You can edit telegram bot messages by editing file `messages.json`. You can add new lines by adding `\\n`

Note: make shure you don't delete argumensts `{0}` in message and please restart script to apply changes

----------

## Running as service on linux

1. Install Python and pip
2. Clone repo
3. Fill `telegram_api_key`, `chatgpt_auth_email`, `chatgpt_auth_password` and `open_ai_api_key` in `settings.json` file
4. Install systemd `sudo apt-get install -y systemd`
5. Create new service file `sudo nano /etc/systemd/system/gpt-telegramus.service`
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
6. Reload systemctl daemon `sudo systemctl daemon-reload`
7. Enable service `sudo systemctl enable gpt-telegramus.service`
8. Start service `sudo systemctl start gpt-telegramus.service`

----------

## Running in Docker

1. Install Docker
2. Clone repo
3. Build container
    ```
    docker buildx build -t telegramus --load -f Dockerfile .
    ```
4. Run the container
    ```
    docker run -d -e TELEGRAMUS_CHATGPT_AUTH_EMAIL=you_email -e TELEGRAMUS_CHATGPT_AUTH_PASSWORD=you_password -e TELEGRAMUS_OPEN_AI_API_KEY=you_apikey -e TELEGRAMUS_TELEGRAM_API_KEY=you_tgbot_apikey --name gpt-telegramus --restart on-failure telegramus
    ```

----------

## Custom proxy or insecure auth to bypass OpenAI's geo-blocking

To enable insecure auth:
- you can set `chatgpt_auth_insecure` to `true` in `settings.json` file
- or you can set `TELEGRAMUS_CHATGPT_AUTH_INSECURE` env variable to `True` (docker: `-e TELEGRAMUS_CHATGPT_AUTH_INSECURE='True'`)

To enable custom proxy (see https://github.com/acheong08/ChatGPT-Proxy)
- you can set proxy to `chatgpt_auth_proxy` in `settings.json` file
- or you can set `TELEGRAMUS_CHATGPT_AUTH_PROXY` env variable (docker: `-e TELEGRAMUS_CHATGPT_AUTH_PROXY=your_proxy`)

----------

## Telegram bot commands

- `/start` - Shows version
- `/help` - Shows list of commands
- `/queue` - Shows requests queue
- `/gpt YOUR REQUEST` - Request to ChatGPT
- `/draw YOUR REQUEST` - Request to DALLE
- Or just type your request as message without `/gpt` command

----------

## TODO

- Create `/settings` command to show and edit current settings
- Add the ability to change settings on the fly
- Add the ability to restart bot / api using command

----------

## Contribution

### Anyone can contribute! Just create a pull request

----------

## P.S. This project is under development!
