---
name: gongzhonghao-peitu-fabu
description: Turn user-provided article text into image prompts and publish-ready WeChat draft assets. Use when the user already has the text and wants illustration generation plus push-to-drafts automation.
---

# 公众号配图发布

This skill is for a complete but focused workflow:

1. Accept user-written cold knowledge text.
2. Produce a cover prompt and inline image prompts.
3. Generate images through the local Gemini image runner when requested.
4. Render Markdown with `bm-md`.
5. Upload the result to the WeChat Official Account draft box.

## Default Responsibility

This skill does not have to rewrite the article.
If the user already has the text, treat that text as the source of truth and focus on visuals plus draft delivery.

## Workflow

### 1. Extract Visual Beats

From the input text, identify:

- the strongest cover scene
- two to five inline scenes
- the central absurdity, naming conflict, or cultural misunderstanding
- any historical or documentary cues

### 2. Build the Visual Pack

Return:

1. **Visual Style Guide**: A 3-4 bullet point definition of the design language (e.g., lighting, medium like 3D render/paper-art/cinematic, camera lens, color palette), custom-derived from the article contents and tone to ensure visual consistency.
2. `Cover Prompt`
3. `Inline Prompt 1`
4. `Inline Prompt 2`
5. `Inline Prompt 3`

Add `Inline Prompt 4/5` only if the article clearly has more visual beats.

You are expected to **freely generate a custom visual style** tailored to the content to maximize visual consistency and beauty. Do **not** restrict prompt generation to the predefined styles in [references/style-guide.md](references/style-guide.md). Use them as initial moodboard reference or inspiration and transcend them.

### 3. Generate Images

If the user wants execution, use:

```bash
python3 scripts/generate_images.py --prompt-file /abs/path/prompts.json
```

Or repeat inline prompts directly:

```bash
python3 scripts/generate_images.py \
  --prompt 'cover.jpg::A cinematic retro scene...' \
  --prompt '01_scene.jpg::A documentary-style close-up...'
```

### 4. Initialize WeChat Login

Before first publish on a machine:

```bash
bash scripts/bootstrap_env.sh
python3 scripts/init_wechat_login.py
```

This opens the Official Account login page and stores the persistent browser session under `assets/wechat_profile/`.

### 5. Publish to WeChat Drafts

Render the article with `bm-md`, copy the rendered HTML to the clipboard, then paste it into the WeChat editor.

Use:

```bash
python3 scripts/publish_article.py \
  --title "标题" \
  --markdown /abs/path/article.md \
  --cover /abs/path/cover.jpg \
  --inline-image PICTUREONE=/abs/path/01.jpg \
  --inline-image PICTURETWO=/abs/path/02.jpg
```

Important:

- The publishing flow is clipboard-based for article HTML.
- The script renders HTML, copies it to the macOS clipboard, focuses the editor, then sends `Meta+V`.
- Inline images also use clipboard paste after selecting the matching placeholder block.

## Environment Notes

- `bm-md` may be configured through environment variables. See [references/setup.md](references/setup.md).
- The image runner defaults to the local Gemini browser driver path but can be overridden.
- If WeChat is not logged in, run `scripts/init_wechat_login.py` first.
