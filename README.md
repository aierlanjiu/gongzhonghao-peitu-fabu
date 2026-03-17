# 公众号配图发布

Open-source skill for this workflow:

1. take user-provided automotive cold-knowledge text
2. generate cover and inline image prompts
3. generate images with the local Gemini browser driver
4. render Markdown with `bm-md`
5. paste the rendered article into the WeChat Official Account draft editor

This skill is designed to be readable by an agent first and executable by a human second.

## Skill Entry

Primary skill file:

- `SKILL.md`

If an agent supports standard skill metadata, also read:

- `agents/openai.yaml`

## Folder Layout

```text
gongzhonghao-peitu-fabu/
├── SKILL.md
├── README.md
├── agents/openai.yaml
├── references/
│   ├── setup.md
│   └── style-guide.md
├── scripts/
│   ├── bootstrap_env.sh
│   ├── init_wechat_login.py
│   ├── generate_images.py
│   ├── publish_article.py
│   ├── copy-to-clipboard.ts
│   ├── paste-from-clipboard.ts
│   └── package.json
└── assets/
```

## What The Agent Should Do

When the user provides article text and wants a publishable WeChat draft:

1. Read `SKILL.md`
2. Read `references/style-guide.md` for inspiration on visual style directions or moodboard templates
3. Read `references/setup.md` if environment validation or installation is needed
4. Run `scripts/bootstrap_env.sh` before first execution on a machine
5. Run `scripts/init_wechat_login.py` if WeChat login has not been initialized
6. Use `scripts/generate_images.py` when the user wants actual image generation
7. Use `scripts/publish_article.py` to push the article into the WeChat draft editor

## Installation

### 1. Python packages

```bash
python3 -m pip install playwright requests python-dotenv
playwright install chromium
```

### 2. Bun

```bash
curl -fsSL https://bun.sh/install | bash
```

If `bun` is not on `PATH`, restart the shell.

### 3. macOS prerequisites

Install Xcode Command Line Tools if `swift` is missing:

```bash
xcode-select --install
```

Grant Accessibility permission to the terminal app that will run the scripts.
This is required for the real paste keystroke helper.

### 4. bm-md

Create a `.env` file from `.env.example` to set up your project paths.

```bash
cp .env.example .env
```

Edit the `.env` file to point to your local `bm-md` deployment:

```bash
BM_MD_DIR="/path/to/your/02_排版tools/bm-md"
```

Start your `bm-md` locally:

```bash
cd "/path/to/your/02_排版tools/bm-md"
npm run dev
```

Default render endpoint configuration:
The publish script supports these environment variables (which can also be set in `.env`):
- `BM_MD_RENDER_URL`
- `BM_MD_API_URL`
- `VITE_API_URL`
- `BM_MD_APP_URL`
- `VITE_APP_URL`

Fallback URL if not specified is `http://localhost:2663/api/markdown/render`.

### 5. Bootstrap

Run:

```bash
bash scripts/bootstrap_env.sh
```

This checks:

- Python availability
- Bun availability
- Python package availability
- local `bm-md` path
- recommended `BM_MD_RENDER_URL`

## First-Time Login

### 1. WeChat Official Account Login

Run:

```bash
python3 scripts/init_wechat_login.py
```

What happens:
1. Chrome opens the WeChat Official Account login page
2. the user scans the QR code
3. the persistent login session is stored under `assets/wechat_profile/`

### 2. Gemini Account Login (For Image Generation)

Run:

```bash
python3 scripts/init_gemini_login.py
```

What happens:
1. Chrome launches with your configuration's persistent browser context
2. You log into your Google Account so it can access https://gemini.google.com/app
3. Closing the browser window saves the profile data

## Prompt And Image Generation

The image generator expects repeated prompt arguments:

```bash
python3 scripts/generate_images.py \
  --prompt 'cover.jpg::A cinematic documentary cover scene...' \
  --prompt '01_scene.jpg::A tense retro street scene...' \
  --prompt '02_scene.jpg::A close-up of the badge and translation conflict...'
```

By default, it will attempt to read from a standard location, but it is highly recommended to set `GEMINI_DRIVER_PATH` in your `.env` file to point to your `gemini_driver.py`.

```bash
GEMINI_DRIVER_PATH="/path/to/your/scripts/gemini_driver.py"
```

Override directly on command line:

```bash
GEMINI_DRIVER_PATH=/custom/path/gemini_driver.py python3 scripts/generate_images.py ...
```

## Publishing Flow

The publishing script is intentionally clipboard-based.

It does this:

1. render Markdown to HTML through `bm-md`
2. use `scripts/copy-to-clipboard.ts` to copy rich HTML into the system clipboard
3. open the WeChat draft editor with Playwright
4. use `scripts/paste-from-clipboard.ts` to send a real paste keystroke
5. replace inline placeholders by copying each image to the clipboard and pasting it over the placeholder
6. upload the cover image through the file input
7. save the draft

Run:

```bash
python3 scripts/publish_article.py \
  --title "三菱帕杰罗命名冷知识" \
  --markdown /abs/path/article.md \
  --cover /abs/path/cover.jpg \
  --inline-image PICTUREONE=/abs/path/01.jpg \
  --inline-image PICTURETWO=/abs/path/02.jpg \
  --inline-image PICTURETHREE=/abs/path/03.jpg
```

## Assumptions

This skill currently assumes:

- macOS
- Chrome installed
- WeChat Official Account web editor
- a local `bm-md` server
- a local Gemini browser driver for image generation

## Quick Test Order

Use this order on a fresh machine:

```bash
bash scripts/bootstrap_env.sh
python3 scripts/init_wechat_login.py
python3 scripts/generate_images.py --prompt 'cover.jpg::test prompt'
python3 scripts/publish_article.py --help
```

## If The Agent Needs To Explain Failures

The most common blockers are:

- `bun` missing
- `swift` missing
- terminal Accessibility permission missing
- `bm-md` not running
- WeChat login profile not initialized
- `gemini_driver.py` path not available
