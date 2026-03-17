# Setup

## Python

Required packages:

- `playwright`
- `requests`
- `python-dotenv`

Install Playwright browser once if needed:

```bash
playwright install chromium
```

## Bun and macOS clipboard prerequisites

The bundled publish flow uses local TypeScript helpers for rich HTML clipboard copy and real paste keystrokes.

Install Bun:

```bash
curl -fsSL https://bun.sh/install | bash
```

Install Xcode Command Line Tools if `swift` is missing:

```bash
xcode-select --install
```

On macOS, also grant Accessibility permission to the terminal app you use, otherwise the paste keystroke may fail.

## bm-md

Start your local `bm-md` service (path set in `.env` as `BM_MD_DIR`) before publishing:

```bash
cd "/path/to/your/bm-md"
npm run dev
```

The publish script resolves the render endpoint in this order:

1. `--bm-md-url`
2. `BM_MD_RENDER_URL`
3. `BM_MD_API_URL`
4. `VITE_API_URL`
5. `BM_MD_APP_URL`
6. `VITE_APP_URL`
7. fallback: `http://localhost:2663/api/markdown/render`

If you only have an app base URL, the script appends `/api/markdown/render`.

## Account login

### WeChat Login

Initialize the persistent login session:

```bash
python3 scripts/init_wechat_login.py
```

This stores the browser profile in `assets/wechat_profile/`.

### Gemini Login

Initialize the persistent driver profile session for image generation:

```bash
python3 scripts/init_gemini_login.py
```

This ensures full Google Auth for your chrome persistent profile location.

## Image driver

The image script reads `GEMINI_DRIVER_PATH` from your `.env` file (configured via `.env.example`). 

Override directly on command line:

```bash
GEMINI_DRIVER_PATH=/custom/path/gemini_driver.py python3 scripts/generate_images.py ...
```
