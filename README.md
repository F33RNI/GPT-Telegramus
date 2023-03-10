# GPT-Telegramus
## ChatGPT and DALLE implementation as a telegram bot
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
<div style="width:100%;text-align:center;">
    <p align="center">
        <img src="Screenshots/start.png" width="auto" height="300" alt="/start command">
        <img src="Screenshots/chatgpt.png" width="auto" height="300" alt="Screenshot of request to ChatGPT">
        <img src="Screenshots/dalle.png" width="auto" height="300" alt="Screenshot of request to DALL-E">
    </p>
</div>

----------

## Support project

Support the project by buying and listening to my music 🎵

- [Bandcamp](https://f3rni.bandcamp.com)
- [Spotify](https://open.spotify.com/artist/22PQ62alehywlYiksbtzsm)
- [Other platforms](https://distrokid.com/hyperfollow/f3rni/dysphoria) (Latest album)
- [YouTube](https://www.youtube.com/@F3RNI) (Updates rarely)
- [SoundCloud](https://soundcloud.com/f3rni) (Updates rarely)

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
4. For **API type 3** (recommended) (revChatGPT API V3, official chatGPT API):
   1. Generate API Key https://platform.openai.com/account/api-keys and paste it into `api_key` in `chatgpt_auth` in `settings.json` file
   2. Configure proxy if needed in `proxy` in `settings.json` file
5. For **API type 0** (revChatGPT API V0, Official API, more "stupid" model, uses credits):
   1. Generate API Key https://platform.openai.com/account/api-keys and paste it into `api_key` in `chatgpt_auth` in `settings.json` file
   2. Configure proxy if needed in `proxy` in `settings.json` file
6. For **API type 1** (revChatGPT API V1, free, uses same model as official website):
   1. Create account at OpenAI. Make sure you have access to https://chat.openai.com/
   2. Open https://chat.openai.com/api/auth/session
   3. Copy value of `accessToken` into `access_token` in `chatgpt_auth` in `chatgpt_api_1` in `settings.json` file
   4. Configure proxy if needed in `proxy` in `settings.json` file

7. For DALL-E, generate API Key https://platform.openai.com/account/api-keys
8. Type Generated OpenAI API Key into `open_ai_api_key` in `dalle` in `settings.json` file
9. Create bot at https://t.me/BotFather
10. Type Bot's token into `api_key` in `telegram` in `settings.json` file
11. Run main script `python main.py`

Example `settings.json`:
```json
{
  "modules": {
    "chatgpt": true,
    "chatgpt_api_type": 3,
    "dalle": true
  },

  "chatgpt_auth": {
    "api_key": "sk-XxxxxxxXXxXXXxxXXXxxXXXXXXXXXXXxxxxxxxxxxxxxxxXX",

    "engine": "",

    "email": "",
    "password": "",
    "session_token": "",
    "access_token": "",

    "base_url": ""
  },

  "proxy": {
    "enabled": false,
    "auto": true,
    "manual_proxy": "",
    "https_only": true,
    "proxy_checks_enabled": true,
    "check_interval_seconds": 600,
    "check_message": "1+1",
    "check_message_timeout": 240,
    "check_reply_must_include": "2",
    "max_number_of_processes": 5,
    "initialization_timeout": 60,
    "too_many_requests_wait_time_seconds": 600
  },

  "dalle": {
    "open_ai_api_key": "sk-XxxxxxxXXxXXXxxXXXxxXXXXXXXXXXXxxxxxxxxxxxxxxxXX",
    "image_size": "512x512",
    "use_proxy": true
  },

  "telegram": {
    "api_key": "1234567890:XXXxXxxXxxXXxxXXX-XXXXXXXxXxxxXxXxX",
    "queue_max": 5,
    "show_queue_message": true
  }
}
```

----------

## Bot messages

You can edit telegram bot messages by editing file `messages.json`. You can add new lines by adding `\\n`

Note: make shure you don't delete argumensts `{0}` in message and please restart script to apply changes

----------

## Running as service on linux

1. Install Python and pip
2. Clone repo
3. Edit `settings.json`
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
docker run -d -e TELEGRAMUS_SETTINGS_FILE="PATH_TO_settings.json" -e TELEGRAMUS_MESSAGES_FILE="PATH_TO_messages.json" -e TELEGRAMUS_CHATS_DIR="PATH_TO_chats_DIRECTORY" --name gpt-telegramus --restart on-failure telegramus
```

----------

## Proxy to bypass OpenAI's geo-blocking

It is possible to bypass geo-blocking. GPT-Telegramus includes automatic proxy-list downloading

1. Set `enabled` in `proxy` in `settings.json` to `true`
2. Restart app and hope for the best. 

GPT-Telegramus will have to download the proxy list itself and start trying various proxies (see console for logs).
Sometimes trying can take a very long time (Usually up to half of the proxies is at least one that works)

If you have proxy that definitely works you can specify it in `manual_proxy` in `proxy` in `settings.json`.
**Make sure you set `auto` to `false` when using `manual_proxy`**

`proxy` settings description:
- `enabled` - Whether proxy login is enabled.
- `auto` - Download proxies automatically. Otherwise, use `manual_proxy`
- `https_only` - Don't include http proxies in list
- `manual_proxy` - Manual proxy server. It must support HTTPS, but you need to type it in `http://IP:PORT` format
- `proxy_checks_enabled` - Enables automatic periodic proxy check by asking 1+1 question
- `check_interval_seconds` - Automatic connection check interval (in seconds)
- `check_message` - This message will be sent as a request
- `check_message_timeout` - How long should a response take?
- `check_reply_must_include` - The response message must contain this text to consider that the check was successful
- `max_number_of_processes` - How many background processes are used for checking proxy
- `initialization_timeout` - How long to wait for initialization with proxy

----------

## Telegram bot commands

- `/start` - Shows version
- `/help` - Shows list of commands
- `/queue` - Shows requests queue
- `/gpt YOUR REQUEST` - Request to ChatGPT (or just type your request as message without `/gpt` command)
- `/draw YOUR REQUEST` - Request to DALLE
- `/clears` - Clears chat history
- `/restart` - Restart chatGPT and Telegram Bot (not tested properly)
- Type any message to ask chatGPT (without `/gpt` command)

----------

## Chat history

Chat histories for each telegram chat (to prevent history collision) are stored in `chats` directory. You can specify it with env variable `TELEGRAMUS_CHATS_DIR`

- Conversation IDs will be saved into `chats.json` inside `chats` directory.
  - File `chats.json` saves `conversation_id` and `parent_id` (for API V1)
- For `"chatgpt_api_type": 3` conversation histories will be saved in `conversations` directory inside `chats` directory.
- For `"chatgpt_api_type": 0` conversation histories will be saved in `conversations.json` file inside `chats` directory.

*p.s. Might not work properly =)*

----------

## TODO

- Make whitelist for users and admin account

----------

## Contribution

### Anyone can contribute! Just create a pull request

----------

## P.S. This project is under development!
