---
name: gongzhonghao-peitu-fabu
description: Take a user-provided finished article, build visual assets, generate images, remove watermarks, and push a publish-ready draft into the WeChat Official Account draft box.
---

# 公众号配图发布

This skill is for a full execution workflow after the article text already exists:

1. Accept a finished article as the source of truth.
2. Extract visual beats and produce the visual pack.
3. Generate the cover and inline images through the local Gemini image runner.
4. Run watermark removal as a separate post-process.
5. Render Markdown with `bm-md`.
6. Upload the result to the WeChat Official Account draft box.

## Default Responsibility

Do not rewrite the article unless the user explicitly asks.
Treat the provided article as the locked input and focus on asset production plus draft delivery.

## Optional Pre-Pass

`火焰编辑部老钱` is an optional upstream pass, not part of the default pipeline. A bundled copy is included at `optional_skills/huoyan-bianjibu-laoqian/`.

Use it only when the user explicitly wants one of these:

- 去 AI 味
- 老钱终审
- 更像真人写的
- 更狠一点的口气

If invoked, use it to rewrite or re-polish the article first, then continue into the normal visual-and-publish pipeline.
If not invoked, skip it entirely.

## Workflow

### 1. Lock The Article Input

The input should already be a complete article.

If the user explicitly requests `火焰编辑部老钱` as an option, run that pass first and treat the revised article as the new locked input.

Use or create:

- `article.md`
- `prompts.json`
- `visual_pack.md`

The article should include placeholder markers like:

- `PICTUREONE`
- `PICTURETWO`
- `PICTURETHREE`
- `PICTUREFOUR`
- `PICTUREFIVE`

If there are fewer inline images than placeholders, the first placeholder may reuse the cover image to avoid empty blocks in the final draft.

### 2. Extract Visual Beats

From the input text, identify:

- the strongest cover scene
- two to five inline scenes
- the central absurdity, naming conflict, or cultural misunderstanding
- any historical or documentary cues

### 3. Build the Visual Pack

Return:

1. **Visual Style Guide**: A 3-4 bullet point definition of the design language (e.g., lighting, medium like 3D render/paper-art/cinematic, camera lens, color palette), custom-derived from the article contents and tone to ensure visual consistency.
2. `Cover Prompt`
3. `Inline Prompt 1`
4. `Inline Prompt 2`
5. `Inline Prompt 3`

Add `Inline Prompt 4/5` only if the article clearly has more visual beats.

You are expected to **freely generate a custom visual style** tailored to the content to maximize visual consistency and beauty. Do **not** restrict prompt generation to the predefined styles in [references/style-guide.md](references/style-guide.md). Use them as initial moodboard reference or inspiration and transcend them.

Persist the prompts as `prompts.json`, for example:

```json
[
  { "name": "cover.jpg", "prompt": "..." },
  { "name": "01_scene.jpg", "prompt": "..." }
]
```

### 4. Generate Images

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

Execution rule:

- Once image generation starts, do not interrupt it mid-run.
- Do not kill the process because the UI appears quiet.
- Wait for the generator to exit on its own, then verify files on disk.

### 5. Remove Watermarks

Run watermark removal as a separate stage after images are saved:

```bash
python3 scripts/remove_watermark.py /abs/path/to/image.jpg
```

Apply it to every generated inline image.

Notes:

- `remove_watermark.py` is a single-image script, so call it once per file.
- If the script reports no watermark detected, keep the original image.
- Do not embed watermark removal into `generate_images.py`; keep it as an external post-process.

### 6. Initialize WeChat Login

Before first publish on a machine:

```bash
bash scripts/bootstrap_env.sh
python3 scripts/init_wechat_login.py
```

This opens the Official Account login page and stores the persistent browser session under `assets/wechat_profile/`.

Before publishing, verify that `assets/wechat_profile/` is non-empty. If it is empty or the publish script reports missing login, run login initialization again.

### 7. Publish to WeChat Drafts

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
- The script renders HTML, copies it to the macOS clipboard, focuses the editor, then pastes into the WeChat editor.
- Inline images also use clipboard paste after selecting the matching placeholder block.
- Prefer browser-side paste (`Meta+V` in the controlled page). System-level paste helpers should only be fallback.

## Stage Checklist

### A. Article staging

- Confirm the article is already finalized.
- Confirm placeholder labels match the intended inline-image mapping.
- Save `article.md`, `prompts.json`, and `visual_pack.md` into the article folder.

### B. Image stage

- Generate `cover.jpg` first, then inline images.
- Let the generator finish naturally.
- Verify every expected file exists before moving on.

### C. Watermark stage

- Run `remove_watermark.py` once per generated image.
- Reuse the original if no watermark is detected.

### D. Publish stage

- Confirm `bm-md` returns HTML successfully.
- Confirm `assets/wechat_profile/` contains a valid persistent session.
- Map placeholders to real files, then publish.
- If a first draft was published before watermark removal, re-publish a new draft with the cleaned images.

## Pitfalls To Avoid

1. Do not add an upstream article-analysis step. This skill starts from an already-written article.
2. Do not interrupt `generate_images.py` after it starts, even if the UI enters a long silent wait.
3. Do not assume missing output from the terminal means generation failed; verify files on disk after the process exits.
4. Do not skip watermark removal just because the images already look usable.
5. Do not rely only on macOS system paste; browser-controlled paste is more reliable for WeChat draft publishing.
6. Do not publish before confirming placeholder-to-image mapping, otherwise placeholders may remain in the final draft.

## Environment Notes

- `bm-md` may be configured through environment variables. See [references/setup.md](references/setup.md).
- The image runner defaults to the local Gemini browser driver path but can be overridden.
- The skill ships its own copies of `scripts/gemini_driver.py`, `scripts/remove_watermark.py`, and watermark template assets for portable git sync.
- If WeChat is not logged in, run `scripts/init_wechat_login.py` first.
